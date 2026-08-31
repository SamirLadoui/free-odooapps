# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

OPEN_ACTION_STATES = ('open',)


class Nonconformity(models.Model):
    _name = 'sl.quality.nonconformity'
    _description = 'Non-Conformity'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_reported desc, id desc'
    _rec_names_search = ['code', 'name']

    code = fields.Char(string='Reference', copy=False, readonly=True, default='/')
    name = fields.Char(string='Title', required=True, tracking=True)
    description = fields.Text(string='What Happened', required=True)

    origin = fields.Selection(
        [('internal', 'Found internally'), ('customer', 'Customer complaint'),
         ('supplier', 'Supplier'), ('audit', 'Audit finding')],
        default='internal', required=True, tracking=True)
    severity = fields.Selection(
        [('minor', 'Minor'), ('major', 'Major'), ('critical', 'Critical')],
        default='minor', required=True, tracking=True)

    partner_id = fields.Many2one('res.partner', string='Customer / Supplier')
    reported_by_id = fields.Many2one(
        'res.users', string='Reported By', default=lambda self: self.env.user)
    responsible_id = fields.Many2one(
        'res.users', string='Responsible', required=True, tracking=True,
        default=lambda self: self.env.user)

    date_reported = fields.Date(required=True, default=fields.Date.context_today)
    date_closed = fields.Date(readonly=True, copy=False)

    state = fields.Selection(
        [('draft', 'Reported'), ('analysis', 'Under Analysis'),
         ('action', 'Actions In Progress'), ('closed', 'Closed'),
         ('cancelled', 'Cancelled')],
        default='draft', required=True, tracking=True)

    immediate_action = fields.Text(
        string='Immediate Containment',
        help="What was done straight away to limit the damage.")
    root_cause = fields.Text(
        string='Root Cause',
        help="Why it happened. Required before the non-conformity can be closed.")

    action_ids = fields.One2many(
        'sl.quality.action', 'nonconformity_id', string='Actions')
    action_count = fields.Integer(compute='_compute_action_counts')
    open_action_count = fields.Integer(compute='_compute_action_counts')
    overdue_action_count = fields.Integer(compute='_compute_action_counts')

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    @api.depends('action_ids', 'action_ids.state', 'action_ids.is_overdue')
    def _compute_action_counts(self):
        for record in self:
            actions = record.action_ids
            record.action_count = len(actions)
            record.open_action_count = len(
                actions.filtered(lambda a: a.state in OPEN_ACTION_STATES))
            record.overdue_action_count = len(actions.filtered('is_overdue'))

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = ('[%s] %s' % (record.code, record.name)
                                   if record.code and record.code != '/'
                                   else record.name or '')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', '/') == '/':
                vals['code'] = self.env['ir.sequence'].next_by_code(
                    'sl.quality.nonconformity') or '/'
        return super().create(vals_list)

    # -- workflow ----------------------------------------------------------

    def action_start_analysis(self):
        self.write({'state': 'analysis'})

    def action_start_actions(self):
        for record in self:
            if not record.root_cause:
                raise ValidationError(_(
                    "Record the root cause of %s before raising actions: an "
                    "action without a cause is a guess.") % record.display_name)
            if not record.action_ids:
                raise ValidationError(_(
                    "Add at least one action for %s.") % record.display_name)
        self.write({'state': 'action'})

    def action_close(self):
        """Closing is the claim that this will not happen again, so it has to
        be earned: a cause, and no action still outstanding."""
        for record in self:
            if not record.root_cause:
                raise ValidationError(_(
                    "%s cannot be closed without a root cause.") % record.display_name)
            outstanding = record.action_ids.filtered(
                lambda a: a.state in OPEN_ACTION_STATES)
            if outstanding:
                raise ValidationError(_(
                    "%(count)s action(s) on %(name)s are still open.") % {
                        'count': len(outstanding), 'name': record.display_name})
        self.write({'state': 'closed', 'date_closed': fields.Date.context_today(self)})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft', 'date_closed': False})

    def action_view_actions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Actions"),
            'res_model': 'sl.quality.action',
            'view_mode': 'list,form',
            'domain': [('nonconformity_id', '=', self.id)],
            'context': {'default_nonconformity_id': self.id},
        }


class QualityAction(models.Model):
    _name = 'sl.quality.action'
    _description = 'Quality Action'
    _inherit = ['mail.thread']
    _order = 'deadline, id'

    name = fields.Char(string='Action', required=True, tracking=True)
    nonconformity_id = fields.Many2one(
        'sl.quality.nonconformity', string='Non-Conformity',
        required=True, ondelete='cascade')
    action_type = fields.Selection(
        [('corrective', 'Corrective'), ('preventive', 'Preventive')],
        default='corrective', required=True,
        help="Corrective fixes what went wrong. Preventive stops it happening "
             "somewhere it has not yet.")
    responsible_id = fields.Many2one(
        'res.users', string='Responsible', required=True, tracking=True,
        default=lambda self: self.env.user)
    deadline = fields.Date(tracking=True)
    state = fields.Selection(
        [('open', 'Open'), ('done', 'Done'), ('cancelled', 'Cancelled')],
        default='open', required=True, tracking=True)
    date_done = fields.Date(readonly=True, copy=False)
    is_overdue = fields.Boolean(compute='_compute_is_overdue', store=True)
    note = fields.Text()

    @api.depends('deadline', 'state')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for action in self:
            action.is_overdue = bool(
                action.state == 'open' and action.deadline and action.deadline < today)

    @api.constrains('deadline', 'nonconformity_id')
    def _check_deadline(self):
        for action in self.filtered('deadline'):
            reported = action.nonconformity_id.date_reported
            if reported and action.deadline < reported:
                raise ValidationError(_(
                    "'%s' is due before the non-conformity was even reported.")
                    % action.name)

    def action_done(self):
        self.write({'state': 'done', 'date_done': fields.Date.context_today(self)})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reopen(self):
        self.write({'state': 'open', 'date_done': False})

    @api.model
    def _cron_refresh_overdue(self):
        """is_overdue is stored so it can be searched and used to colour rows,
        but it depends on today's date, so it goes stale overnight. Recompute
        the open ones each morning."""
        pending = self.search([('state', '=', 'open'), ('deadline', '!=', False)])
        pending.invalidate_recordset(['is_overdue'])
        pending._compute_is_overdue()
        return True
