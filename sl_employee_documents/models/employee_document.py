# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class EmployeeDocumentType(models.Model):
    _name = 'sl.employee.document.type'
    _description = 'Employee Document Type'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Char()
    expires = fields.Boolean(
        string='Has An Expiry Date', default=True,
        help="Turn off for documents that never expire, such as a diploma.")
    reminder_days = fields.Integer(
        string='Warn This Many Days Ahead', default=30,
        help="How long before expiry a document starts counting as expiring.")
    active = fields.Boolean(default=True)
    document_ids = fields.One2many('sl.employee.document', 'type_id')

    @api.constrains('reminder_days')
    def _check_reminder_days(self):
        for record in self:
            if record.reminder_days < 0:
                raise ValidationError(_("The warning window cannot be negative."))

    @api.constrains('name')
    def _check_name_unique(self):
        for record in self:
            if self.search_count([('id', '!=', record.id), ('name', '=ilike', record.name)]):
                raise ValidationError(
                    _("A document type called '%s' already exists.") % record.name)


class EmployeeDocument(models.Model):
    _name = 'sl.employee.document'
    _description = 'Employee Document'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'expiry_date, id'

    name = fields.Char(string='Document', required=True, tracking=True)
    employee_id = fields.Many2one(
        'hr.employee', required=True, ondelete='cascade', tracking=True)
    type_id = fields.Many2one(
        'sl.employee.document.type', string='Type', required=True, tracking=True)
    number = fields.Char(string='Reference Number', tracking=True)

    issue_date = fields.Date(tracking=True)
    expiry_date = fields.Date(tracking=True)
    days_to_expiry = fields.Integer(compute='_compute_state', store=True)
    state = fields.Selection(
        [('valid', 'Valid'), ('expiring', 'Expiring Soon'),
         ('expired', 'Expired'), ('no_expiry', 'No Expiry')],
        compute='_compute_state', store=True, tracking=True)

    responsible_id = fields.Many2one(
        'res.users', string='Responsible',
        help="Gets the activity when this document is about to expire.")
    note = fields.Text()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', related='employee_id.company_id', store=True)
    last_reminder_on = fields.Date(readonly=True, copy=False)

    @api.depends('expiry_date', 'type_id.expires', 'type_id.reminder_days')
    def _compute_state(self):
        """The whole point of the module: is this document about to bite us?"""
        today = fields.Date.context_today(self)
        for document in self:
            if not document.type_id.expires or not document.expiry_date:
                document.state = 'no_expiry'
                document.days_to_expiry = 0
                continue
            remaining = (document.expiry_date - today).days
            document.days_to_expiry = remaining
            window = document.type_id.reminder_days or 0
            if remaining < 0:
                document.state = 'expired'
            elif remaining <= window:
                document.state = 'expiring'
            else:
                document.state = 'valid'

    @api.constrains('issue_date', 'expiry_date')
    def _check_dates(self):
        for document in self:
            if (document.issue_date and document.expiry_date
                    and document.expiry_date < document.issue_date):
                raise ValidationError(_(
                    "%s expires before it was issued.") % document.name)

    @api.onchange('type_id')
    def _onchange_type_id(self):
        if self.type_id and not self.type_id.expires:
            self.expiry_date = False

    @api.depends('name', 'employee_id')
    def _compute_display_name(self):
        for document in self:
            document.display_name = '%s - %s' % (
                document.employee_id.name or '', document.name or '')

    # -- reminders ---------------------------------------------------------

    @api.model
    def _documents_needing_reminder(self, today=None):
        """Documents that are expiring or already expired and have not been
        chased today. Kept separate from the cron so it can be tested."""
        today = today or fields.Date.context_today(self)
        return self.search([
            ('state', 'in', ('expiring', 'expired')),
            '|', ('last_reminder_on', '=', False), ('last_reminder_on', '<', today),
        ])

    def _notify_expiry(self):
        """Log on the document and raise an activity for whoever owns it."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        body = (_("%(name)s expired on %(date)s.")
                if self.state == 'expired'
                else _("%(name)s expires on %(date)s.")) % {
            'name': self.name, 'date': self.expiry_date}
        self.message_post(body=body)

        user = self.responsible_id or self.employee_id.parent_id.user_id
        if user:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=user.id,
                summary=_("Employee document expiring: %s") % self.display_name,
                note=body)
        self.last_reminder_on = today

    @api.model
    def _cron_notify_expiring(self):
        """One bad document must not stop the rest of the run."""
        failures = []
        for document in self._documents_needing_reminder():
            # A savepoint rather than a commit: it gives the same per-record
            # isolation, and 19.0 refuses a commit from inside a test.
            try:
                with self.env.cr.savepoint():
                    document._notify_expiry()
            except Exception as err:
                failures.append('%s: %s' % (document.display_name, err))
        if failures:
            _logger.warning("Document reminders failed:\n%s", '\n'.join(failures))
        return True
