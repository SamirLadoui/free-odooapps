# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class FeeStructure(models.Model):
    _name = 'sl.fee.structure'
    _description = 'Fee Structure'
    _order = 'academic_year_id desc, name'

    name = fields.Char(required=True)
    academic_year_id = fields.Many2one(
        'sl.academic.year', string='Academic Year', required=True, ondelete='cascade')
    standard_ids = fields.Many2many(
        'sl.school.standard', string='Applies To',
        help="Classes this structure covers. Leave empty for every class in the year.")
    line_ids = fields.One2many('sl.fee.structure.line', 'structure_id', string='Items')
    amount_total = fields.Monetary(compute='_compute_amount_total', store=True)
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    active = fields.Boolean(default=True)

    @api.depends('line_ids.amount')
    def _compute_amount_total(self):
        for structure in self:
            structure.amount_total = sum(structure.line_ids.mapped('amount'))

    @api.constrains('name', 'academic_year_id')
    def _check_name_unique(self):
        for structure in self:
            if self.search_count([
                ('id', '!=', structure.id),
                ('name', '=ilike', structure.name),
                ('academic_year_id', '=', structure.academic_year_id.id),
            ]):
                raise ValidationError(_(
                    "A fee structure called '%s' already exists for that year.")
                    % structure.name)

    def _covers(self, standard):
        """Empty standard_ids means the whole year, not nothing."""
        self.ensure_one()
        if not self.standard_ids:
            return standard.academic_year_id == self.academic_year_id
        return standard in self.standard_ids


class FeeStructureLine(models.Model):
    _name = 'sl.fee.structure.line'
    _description = 'Fee Item'
    _order = 'structure_id, sequence, id'

    sequence = fields.Integer(default=10)
    structure_id = fields.Many2one('sl.fee.structure', required=True, ondelete='cascade')
    name = fields.Char(string='Item', required=True)
    amount = fields.Monetary(required=True)
    currency_id = fields.Many2one(related='structure_id.currency_id')
    note = fields.Char()

    @api.constrains('amount')
    def _check_amount(self):
        for line in self:
            if line.amount < 0:
                raise ValidationError(_("A fee item cannot be negative."))


class Fee(models.Model):
    _name = 'sl.fee'
    _description = 'Student Fee'
    _inherit = ['mail.thread']
    _order = 'date_due, id'

    code = fields.Char(string='Reference', copy=False, readonly=True, default='/')
    student_id = fields.Many2one(
        'sl.student', string='Student', required=True, ondelete='restrict', tracking=True)
    standard_id = fields.Many2one(related='student_id.standard_id', store=True)
    academic_year_id = fields.Many2one(related='student_id.academic_year_id', store=True)
    structure_id = fields.Many2one(
        'sl.fee.structure', string='Fee Structure', required=True, ondelete='restrict')

    date_due = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    amount = fields.Monetary(required=True, tracking=True)
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)

    state = fields.Selection(
        [('draft', 'Draft'), ('invoiced', 'Invoiced'),
         ('paid', 'Paid'), ('cancelled', 'Cancelled')],
        default='draft', required=True, tracking=True)
    invoice_id = fields.Many2one(
        'account.move', string='Invoice', readonly=True, copy=False)
    is_overdue = fields.Boolean(compute='_compute_is_overdue', store=True)

    @api.depends('date_due', 'state')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for fee in self:
            fee.is_overdue = bool(
                fee.state in ('draft', 'invoiced') and fee.date_due
                and fee.date_due < today)

    @api.depends('code', 'student_id')
    def _compute_display_name(self):
        for fee in self:
            fee.display_name = '%s - %s' % (
                fee.code or '/', fee.student_id.name or '')

    @api.constrains('amount')
    def _check_amount(self):
        for fee in self:
            if fee.amount <= 0:
                raise ValidationError(_("A fee must be for more than zero."))

    @api.constrains('student_id', 'structure_id')
    def _check_structure_applies(self):
        """Charging a student a structure for another class is always a mistake."""
        for fee in self:
            standard = fee.student_id.standard_id
            if standard and not fee.structure_id._covers(standard):
                raise ValidationError(_(
                    "%(structure)s does not apply to %(standard)s.") % {
                        'structure': fee.structure_id.name,
                        'standard': standard.display_name})

    @api.onchange('structure_id')
    def _onchange_structure_id(self):
        if self.structure_id and not self.amount:
            self.amount = self.structure_id.amount_total

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', '/') == '/':
                vals['code'] = self.env['ir.sequence'].next_by_code('sl.fee') or '/'
        return super().create(vals_list)

    # -- invoicing ---------------------------------------------------------

    def action_create_invoice(self):
        invoices = self.env['account.move']
        for fee in self:
            if fee.state != 'draft':
                raise UserError(_(
                    "%s has already been invoiced.") % fee.display_name)
            invoices |= fee._create_invoice()
        return invoices

    def _create_invoice(self):
        self.ensure_one()
        partner = self.student_id.partner_id
        if not partner:
            raise UserError(_(
                "%s has no contact record, so there is nobody to invoice. "
                "Enrol the student first.") % self.student_id.display_name)
        journal = self.env['account.journal'].search([
            ('type', '=', 'sale'), ('company_id', '=', self.env.company.id)], limit=1)
        if not journal:
            raise UserError(_("No sales journal, so an invoice cannot be created."))

        account = self._fee_income_account(journal)
        if not account:
            raise UserError(_(
                "No income account, so an invoice line cannot be created. "
                "Set up a chart of accounts first."))

        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_date': fields.Date.context_today(self),
            'invoice_date_due': self.date_due,
            'journal_id': journal.id,
            'invoice_line_ids': [(0, 0, {
                'name': '%s - %s' % (self.structure_id.name, self.student_id.name),
                'quantity': 1.0,
                'price_unit': self.amount,
                'account_id': account.id,
            })],
        })
        self.write({'invoice_id': invoice.id, 'state': 'invoiced'})
        self.message_post(body=_("Invoice %s created.") % invoice.name)
        return invoice

    def _fee_income_account(self, journal):
        """Where a fee line posts.

        Built directly rather than through the invoice's onchanges, so nothing
        fills the account in for us and the database refuses a line without
        one.
        """
        self.ensure_one()
        if 'default_account_id' in journal._fields and journal.default_account_id:
            return journal.default_account_id
        accounts = self.env['account.account']
        domain_field = 'account_type' if 'account_type' in accounts._fields             else 'internal_group'
        return accounts.search([(domain_field, '=', 'income')], limit=1)

    def action_mark_paid(self):
        for fee in self:
            if fee.state == 'cancelled':
                raise UserError(_(
                    "%s is cancelled.") % fee.display_name)
        self.write({'state': 'paid'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})


class Student(models.Model):
    _inherit = 'sl.student'

    fee_ids = fields.One2many('sl.fee', 'student_id', string='Fees')
    fee_total = fields.Monetary(compute='_compute_fee_totals', currency_field='fee_currency_id')
    fee_outstanding = fields.Monetary(
        compute='_compute_fee_totals', currency_field='fee_currency_id',
        help="Charged but not yet paid, ignoring cancelled fees.")
    fee_currency_id = fields.Many2one(
        'res.currency', compute='_compute_fee_totals')

    @api.depends('fee_ids.amount', 'fee_ids.state')
    def _compute_fee_totals(self):
        company_currency = self.env.company.currency_id
        for student in self:
            live = student.fee_ids.filtered(lambda f: f.state != 'cancelled')
            student.fee_currency_id = company_currency
            student.fee_total = sum(live.mapped('amount'))
            student.fee_outstanding = sum(
                live.filtered(lambda f: f.state != 'paid').mapped('amount'))
