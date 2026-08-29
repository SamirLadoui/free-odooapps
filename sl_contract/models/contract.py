# -*- coding: utf-8 -*-
import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

RULE_TYPES = [
    ('daily', 'Day(s)'),
    ('weekly', 'Week(s)'),
    ('monthly', 'Month(s)'),
    ('yearly', 'Year(s)'),
]
DELTA_BY_RULE = {
    'daily': 'days',
    'weekly': 'weeks',
    'monthly': 'months',
    'yearly': 'years',
}


class Contract(models.Model):
    _name = 'sl.contract'
    _description = 'Recurring Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'next_invoice_date, id'
    _rec_names_search = ['name', 'code']

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string='Reference', copy=False, readonly=True, default='/')
    partner_id = fields.Many2one(
        'res.partner', string='Customer', required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', store=True)
    active = fields.Boolean(default=True)

    state = fields.Selection(
        [('draft', 'Draft'), ('open', 'Running'),
         ('closed', 'Closed'), ('cancelled', 'Cancelled')],
        default='draft', required=True, tracking=True)

    date_start = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    date_end = fields.Date(
        tracking=True, help="Leave empty for a contract that runs until you close it.")

    recurring_interval = fields.Integer(
        string='Every', default=1, required=True)
    recurring_rule_type = fields.Selection(
        RULE_TYPES, string='Period', default='monthly', required=True)
    recurring_invoicing_type = fields.Selection(
        [('pre-paid', 'In advance'), ('post-paid', 'In arrears')],
        default='pre-paid', required=True,
        help="In advance invoices the period that is about to start. "
             "In arrears invoices the period that has just finished.")
    next_invoice_date = fields.Date(
        string='Next Invoice', tracking=True,
        help="The next period this contract will be invoiced for.")

    # The domain deliberately does not mention company_id: 17.0 rejects a domain
    # that references a field restricted to a group in the view, and Odoo's own
    # multi-company record rules already keep other companies' journals out.
    journal_id = fields.Many2one(
        'account.journal', string='Sales Journal',
        domain="[('type', '=', 'sale')]")
    payment_term_id = fields.Many2one('account.payment.term', string='Payment Terms')

    line_ids = fields.One2many('sl.contract.line', 'contract_id', string='Lines')
    amount_total = fields.Monetary(compute='_compute_amount_total', store=True)

    invoice_ids = fields.One2many('account.move', 'sl_contract_id', string='Invoices')
    invoice_count = fields.Integer(compute='_compute_invoice_count')

    @api.depends('line_ids.price_subtotal')
    def _compute_amount_total(self):
        for contract in self:
            contract.amount_total = sum(contract.line_ids.mapped('price_subtotal'))

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for contract in self:
            contract.invoice_count = len(contract.invoice_ids)

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for contract in self:
            contract.display_name = ('[%s] %s' % (contract.code, contract.name)
                                     if contract.code and contract.code != '/'
                                     else contract.name or '')

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for contract in self:
            if contract.date_end and contract.date_end < contract.date_start:
                raise ValidationError(_("The contract ends before it starts."))

    @api.constrains('recurring_interval')
    def _check_interval(self):
        for contract in self:
            if contract.recurring_interval < 1:
                raise ValidationError(_("The recurrence interval must be at least 1."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', '/') == '/':
                vals['code'] = self.env['ir.sequence'].next_by_code('sl.contract') or '/'
            vals.setdefault('next_invoice_date', vals.get('date_start'))
        return super().create(vals_list)

    # -- the schedule ------------------------------------------------------

    def _delta(self):
        """One recurrence step as a relativedelta."""
        self.ensure_one()
        return relativedelta(**{
            DELTA_BY_RULE[self.recurring_rule_type]: self.recurring_interval})

    def _period_for(self, invoice_date):
        """The service period an invoice dated `invoice_date` covers.

        In advance: the period starting on that date.
        In arrears: the period that ended the day before it.
        """
        self.ensure_one()
        if self.recurring_invoicing_type == 'pre-paid':
            start = invoice_date
            end = invoice_date + self._delta() - relativedelta(days=1)
        else:
            end = invoice_date - relativedelta(days=1)
            start = invoice_date - self._delta()
        return start, end

    def _next_date_after(self, current):
        self.ensure_one()
        return current + self._delta()

    def _is_due(self, today=None):
        """Whether this contract should be invoiced now."""
        self.ensure_one()
        today = today or fields.Date.context_today(self)
        if self.state != 'open' or not self.next_invoice_date:
            return False
        if self.next_invoice_date > today:
            return False
        if self.date_end and self.next_invoice_date > self.date_end:
            return False
        return bool(self.line_ids)

    # -- invoicing ---------------------------------------------------------

    def _prepare_invoice_values(self, invoice_date):
        self.ensure_one()
        journal = self.journal_id or self.env['account.journal'].search([
            ('type', '=', 'sale'), ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not journal:
            raise UserError(_(
                "No sales journal for %s, so an invoice cannot be created.")
                % self.company_id.name)
        start, end = self._period_for(invoice_date)
        return {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'journal_id': journal.id,
            'invoice_date': invoice_date,
            'invoice_payment_term_id': self.payment_term_id.id or False,
            'sl_contract_id': self.id,
            'invoice_line_ids': [
                (0, 0, line._prepare_invoice_line_values(start, end))
                for line in self.line_ids.filtered(lambda l: l._covers(start, end))
            ],
        }

    def _create_invoice(self, invoice_date=None):
        """One invoice for the current period, then advance the schedule."""
        self.ensure_one()
        invoice_date = invoice_date or self.next_invoice_date
        values = self._prepare_invoice_values(invoice_date)
        if not values['invoice_line_ids']:
            raise UserError(_(
                "No contract line covers %(date)s on %(contract)s.")
                % {'date': invoice_date, 'contract': self.display_name})

        invoice = self.env['account.move'].create(values)
        self.next_invoice_date = self._next_date_after(invoice_date)
        self.message_post(body=_("Invoice %s generated.") % invoice.name)

        if self.date_end and self.next_invoice_date > self.date_end:
            self.state = 'closed'
            self.message_post(body=_("Contract closed: the end date has passed."))
        return invoice

    def action_create_invoice(self):
        """Invoice the current period now, from the button."""
        invoices = self.env['account.move']
        for contract in self:
            if contract.state != 'open':
                raise UserError(_(
                    "%s is not running, so it cannot be invoiced.")
                    % contract.display_name)
            invoices |= contract._create_invoice()
        return invoices

    @api.model
    def _cron_recurring_invoices(self):
        """One bad contract must not stop the rest of the run."""
        today = fields.Date.context_today(self)
        failures = []
        for contract in self.search([('state', '=', 'open')]):
            if not contract._is_due(today):
                continue
            try:
                with self.env.cr.savepoint():
                    contract._create_invoice()
            except Exception as err:
                failures.append('%s: %s' % (contract.display_name, err))
        if failures:
            _logger.warning("Recurring invoicing failed:\n%s", '\n'.join(failures))
        return True

    # -- workflow ----------------------------------------------------------

    def action_start(self):
        for contract in self:
            if not contract.line_ids:
                raise UserError(_(
                    "%s has no lines, so there is nothing to invoice.")
                    % contract.display_name)
            if not contract.next_invoice_date:
                contract.next_invoice_date = contract.date_start
        self.write({'state': 'open'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Invoices"),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('sl_contract_id', '=', self.id)],
            'context': {'default_move_type': 'out_invoice'},
        }


class ContractLine(models.Model):
    _name = 'sl.contract.line'
    _description = 'Contract Line'
    _order = 'contract_id, sequence, id'

    sequence = fields.Integer(default=10)
    contract_id = fields.Many2one('sl.contract', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product')
    name = fields.Char(string='Description', required=True)
    quantity = fields.Float(default=1.0, required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit')
    price_unit = fields.Float(string='Unit Price', required=True)
    discount = fields.Float(string='Discount (%)', default=0.0)
    price_subtotal = fields.Monetary(compute='_compute_price_subtotal', store=True)
    currency_id = fields.Many2one(related='contract_id.currency_id', store=True)

    date_start = fields.Date(
        help="Leave empty to follow the contract. Set to add a line part-way through.")
    date_end = fields.Date(
        help="Leave empty to follow the contract. Set to stop billing this line early.")

    @api.depends('quantity', 'price_unit', 'discount')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = (
                line.quantity * line.price_unit * (1 - (line.discount or 0.0) / 100.0))

    @api.constrains('quantity', 'price_unit', 'discount')
    def _check_amounts(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_("A contract line must have a positive quantity."))
            if line.price_unit < 0:
                raise ValidationError(_("A unit price cannot be negative."))
            if not 0 <= line.discount <= 100:
                raise ValidationError(_("A discount must be between 0 and 100 percent."))

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for line in self:
            if line.date_start and line.date_end and line.date_end < line.date_start:
                raise ValidationError(_("'%s' ends before it starts.") % line.name)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.display_name
            self.price_unit = self.product_id.list_price
            self.uom_id = self.product_id.uom_id

    def _covers(self, start, end):
        """Whether this line should appear on an invoice for [start, end]."""
        self.ensure_one()
        if self.date_start and self.date_start > end:
            return False
        if self.date_end and self.date_end < start:
            return False
        return True

    def _prepare_invoice_line_values(self, start, end):
        self.ensure_one()
        description = '%s\n%s - %s' % (self.name, start, end)
        values = {
            'name': description,
            'quantity': self.quantity,
            'price_unit': self.price_unit,
            'discount': self.discount,
        }
        if self.product_id:
            values['product_id'] = self.product_id.id
        if self.uom_id:
            values['product_uom_id'] = self.uom_id.id
        return values


class AccountMove(models.Model):
    _inherit = 'account.move'

    sl_contract_id = fields.Many2one(
        'sl.contract', string='Contract', readonly=True, copy=False, index=True)
