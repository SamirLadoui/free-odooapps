# Copyright 2026 Samir Ladoui
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
import hashlib

from markupsafe import Markup
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class AttendanceCorrection(models.Model):
    _name = 'sl.attendance.correction'
    _description = 'Attendance Correction Request'
    _inherit = ['mail.thread']  # noqa: RUF012 -- Odoo model registration metadata.
    _order = 'id desc'
    _rec_name = 'employee_id'

    _EDITABLE = frozenset({'attendance_id', 'proposed_check_in', 'proposed_check_out', 'reason'})
    _AUDIT = frozenset({'original_check_in', 'original_check_out', 'original_write_date', 'original_fingerprint',
                       'submitted_at', 'decided_by', 'decided_at', 'decision_reason'})

    employee_id = fields.Many2one('hr.employee', required=True, readonly=True, ondelete='restrict',
                                 default=lambda self: self._own_employee())
    requester_id = fields.Many2one('res.users', required=True, readonly=True, ondelete='restrict',
                                  default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', required=True, readonly=True, ondelete='restrict',
                                default=lambda self: self.env.company)
    attendance_id = fields.Many2one('hr.attendance', string='Existing Attendance', ondelete='restrict',
                                   help='Leave empty only for a genuinely missing attendance.')
    proposed_check_in = fields.Datetime(required=True)
    proposed_check_out = fields.Datetime(required=True)
    reason = fields.Text(required=True)
    state = fields.Selection([('draft', 'Draft'), ('submitted', 'Submitted'), ('approved', 'Approved'),
                              ('rejected', 'Rejected'), ('cancelled', 'Cancelled')],
                             default='draft', required=True, readonly=True, index=True, copy=False)
    original_check_in = fields.Datetime(readonly=True, copy=False)
    original_check_out = fields.Datetime(readonly=True, copy=False)
    original_write_date = fields.Datetime(readonly=True, copy=False)
    original_fingerprint = fields.Char(readonly=True, copy=False,
                                       help='SHA-256 of the locked native stored row at submission.')
    submitted_at = fields.Datetime(readonly=True, copy=False)
    decided_by = fields.Many2one('res.users', readonly=True, ondelete='restrict', copy=False)
    decided_at = fields.Datetime(readonly=True, copy=False)
    decision_reason = fields.Text(readonly=True, copy=False)

    is_requester = fields.Boolean(compute='_compute_permissions')
    can_decide = fields.Boolean(compute='_compute_permissions')

    @api.depends('state', 'requester_id', 'employee_id')
    @api.depends_context('uid', 'allowed_company_ids')
    def _compute_permissions(self):
        officer = self.env.user.has_group('hr_attendance.group_hr_attendance_user')
        for record in self:
            record.is_requester = record.requester_id.id == self.env.uid
            record.can_decide = (record.state == 'submitted' and not record.is_requester
                                 and officer and record.company_id in self.env.companies)

    @api.model
    def _safe_context(self):
        # Never use a client-supplied context flag to bypass an invariant. In
        # particular, ORM default_* values must not populate audit/state fields.
        context = {key: value for key, value in self.env.context.items()
                   if not key.startswith('default_') or key[8:] in self._EDITABLE}
        context.update(tracking_disable=True, mail_create_nosubscribe=True,
                       mail_notify_force_send=False)
        return context

    @api.model
    def _own_employee(self):
        # Narrow elevated READ only: regular employees cannot read private HR
        # fields. No access rights on hr.employee or hr.attendance are granted.
        if not self.env.user.has_group('base.group_user'):
            raise AccessError(_('Only internal employees can request a correction.'))
        return self.env['hr.employee'].sudo().search([
            ('user_id', '=', self.env.uid), ('company_id', '=', self.env.company.id),
        ], limit=1)

    @api.model
    def default_get(self, fields_list):
        clean = self.with_context(self._safe_context())
        defaults = super(AttendanceCorrection, clean).default_get(fields_list)
        authoritative = dict.fromkeys(self._AUDIT, False)
        authoritative.update(employee_id=self._own_employee().id, requester_id=self.env.uid,
                             company_id=self.env.company.id, state='draft')
        defaults.update({key: value for key, value in authoritative.items() if key in fields_list})
        return defaults

    @api.model_create_multi
    def create(self, vals_list):
        employee = self._own_employee()
        if not employee:
            raise AccessError(_('Link your user to an active employee in the current company first.'))
        prepared = []
        for vals in vals_list:
            if set(vals) - (self._EDITABLE | {'employee_id'}):
                raise AccessError(_('Only proposal fields may be supplied when creating a request.'))
            if 'employee_id' in vals and vals['employee_id'] != employee.id:
                raise AccessError(_('You can only request corrections for your own employee.'))
            prepared.append(dict(vals, employee_id=employee.id, requester_id=self.env.uid,
                                 company_id=employee.company_id.id, state='draft'))
        clean = self.with_context(self._safe_context())
        return super(AttendanceCorrection, clean).create(prepared)

    def _validate_identity(self):
        self.ensure_one()
        employee = self.employee_id.sudo()
        employee.flush(['user_id', 'company_id'])
        employee.invalidate_cache(['user_id', 'company_id'], employee.ids)
        if (employee.user_id != self.requester_id or employee.company_id != self.company_id
                or self.company_id not in self.env.companies):
            raise AccessError(_('Employee ownership or company changed. Create a fresh request.'))

    @api.constrains('employee_id', 'requester_id', 'company_id', 'attendance_id',
                    'reason', 'proposed_check_in', 'proposed_check_out')
    def _check_proposal(self):
        for record in self:
            record._validate_identity()
            if not (record.reason or '').strip():
                raise ValidationError(_('A correction reason is required.'))
            if (not record.proposed_check_in or not record.proposed_check_out
                    or record.proposed_check_out <= record.proposed_check_in):
                raise ValidationError(_('Proposed check-out must be later than check-in.'))
            if record.attendance_id:
                record.attendance_id.check_access_rights('read')
                record.attendance_id.check_access_rule('read')
                if record.attendance_id.employee_id != record.employee_id:
                    raise AccessError(_('The attendance must belong to the requesting employee.'))

    def _lock(self):
        self.ensure_one()
        self.check_access_rights('write')
        self.check_access_rule('write')
        self.flush()
        self.env.cr.execute('SELECT id FROM sl_attendance_correction WHERE id = %s FOR UPDATE', [self.id])
        if not self.env.cr.fetchone():
            raise UserError(_('This request no longer exists.'))
        self.invalidate_cache(ids=self.ids)
        self.check_access_rights('write')
        self.check_access_rule('write')

    def _internal_write(self, vals):
        # Private helpers cannot be called through Odoo RPC. No context bypass.
        clean = self.with_context(self._safe_context())
        return super(AttendanceCorrection, clean).write(vals)

    def write(self, vals):
        if set(vals) - self._EDITABLE:
            raise AccessError(_('Identity, state and audit fields cannot be edited directly.'))
        for record in self.sorted('id'):
            record._lock()
            if record.state != 'draft':
                raise UserError(_('Only draft proposals can be edited. Cancel and create a fresh request.'))
            if record.requester_id.id != self.env.uid:
                raise AccessError(_('Only the requester can edit a draft.'))
            record._validate_identity()
        return self._internal_write(vals)

    def unlink(self):
        for record in self.sorted('id'):
            record._lock()
            if record.state != 'draft':
                raise UserError(_('Submitted and audit records cannot be deleted.'))
            if record.requester_id.id != self.env.uid:
                raise AccessError(_('Only the requester can delete a draft.'))
        return super().unlink()

    def _lock_employee(self):
        # Serialize this app's decisions for different requests for one employee,
        # including missing-attendance creates. This does not change HR rights.
        employee = self.employee_id.sudo()
        employee.flush()
        self.env.cr.execute('SELECT id FROM hr_employee WHERE id = %s FOR UPDATE', [employee.id])
        if not self.env.cr.fetchone():
            raise UserError(_('The employee no longer exists.'))
        employee.invalidate_cache(ids=employee.ids)
        self._validate_identity()

    def _serialize_employee_decision(self):
        # A SELECT FOR UPDATE alone cannot refresh a PostgreSQL REPEATABLE READ
        # snapshot. Two different missing requests could otherwise both see no
        # attendance, even after waiting for the employee lock. Update a private,
        # module-owned row so a concurrent stale snapshot gets SerializationFailure
        # and Odoo's normal request retry starts with fresh data. Never mutate an
        # HR employee merely to obtain this transaction-version conflict.
        self.env.cr.execute("""
            INSERT INTO sl_attendance_correction_guard
                (employee_id, revision, create_uid, write_uid, create_date, write_date)
            VALUES (%s, 1, %s, %s, timezone('UTC', now()), timezone('UTC', now()))
            ON CONFLICT (employee_id) DO UPDATE
                SET revision = sl_attendance_correction_guard.revision + 1,
                    write_uid = EXCLUDED.write_uid, write_date = EXCLUDED.write_date
            RETURNING id
        """, [self.employee_id.id, self.env.uid, self.env.uid])
        self.env.cr.fetchone()

    def _lock_attendance(self):
        attendance = self.attendance_id
        fingerprint = False
        if attendance:
            attendance.check_access_rights('read')
            attendance.check_access_rule('read')
            attendance.flush()
            self.env.cr.execute(
                'SELECT to_jsonb(a)::text FROM hr_attendance a WHERE id = %s FOR UPDATE',
                [attendance.id],
            )
            row = self.env.cr.fetchone()
            if not row:
                raise UserError(_('The attendance no longer exists.'))
            # cr.now()/write_date can be identical for several ORM writes in one
            # transaction. Hash every native stored value as well, without copying
            # private row contents into the request or trusting client metadata.
            fingerprint = hashlib.sha256(row[0].encode()).hexdigest()
            attendance.invalidate_cache(ids=attendance.ids)
            attendance.check_access_rights('read')
            attendance.check_access_rule('read')
        return attendance, fingerprint

    def _check_no_overlap(self):
        # Also catch an earlier open attendance. Odoo's own create/write
        # constraints still run, with exactly the approver's native ORM rights.
        overlap = self.env['hr.attendance'].search([
            ('employee_id', '=', self.employee_id.id), ('id', '!=', self.attendance_id.id or 0),
            ('check_in', '<', self.proposed_check_out),
            '|', ('check_out', '=', False), ('check_out', '>', self.proposed_check_in),
        ], limit=1)
        if overlap:
            raise ValidationError(_('The proposed period overlaps an existing or open attendance.'))

    def _check_decider(self):
        self.ensure_one()
        self.check_access_rights('write')
        self.check_access_rule('write')
        self._validate_identity()
        if self.requester_id.id == self.env.uid:
            raise AccessError(_('You cannot approve or reject your own correction request.'))
        # On this release the native Officer role has all permitted-company
        # attendance rights; Administrator implies Officer. No assignment field.
        if not self.env.user.has_group('hr_attendance.group_hr_attendance_user'):
            raise AccessError(_('Only a native attendance officer or administrator can decide.'))
        if self.state != 'submitted':
            raise UserError(_('Only a submitted request can be decided.'))

    def _audit_note(self, outcome, detail, applied=False):
        # Log only: _message_log does not notify followers or send email.
        # Values are escaped by Markup interpolation; all timestamps are UTC.
        body = Markup('<p><strong>%s</strong></p><p>%s</p>') % (outcome, detail)
        if self.submitted_at:
            body += Markup('<p>Original at submission (UTC): %s → %s</p>') % (
                fields.Datetime.to_string(self.original_check_in) or _('No attendance'),
                fields.Datetime.to_string(self.original_check_out) or _('Open / not present'),
            )
        else:
            body += Markup('<p>%s</p>') % _('No submission snapshot was captured: this draft was cancelled.')
        body += Markup('<p>Requested (UTC): %s → %s<br/>Reason: %s</p>') % (
            fields.Datetime.to_string(self.proposed_check_in),
            fields.Datetime.to_string(self.proposed_check_out), self.reason,
        )
        if applied:
            body += Markup('<p>Applied attendance #%s (UTC): %s → %s</p>') % (
                self.attendance_id.id, fields.Datetime.to_string(self.attendance_id.check_in),
                fields.Datetime.to_string(self.attendance_id.check_out),
            )
        self.with_context(self._safe_context())._message_log(body=body)

    def action_submit(self):
        with self.env.cr.savepoint():
            self._lock()
            if self.state != 'draft':
                raise UserError(_('Only a draft can be submitted.'))
            if self.requester_id.id != self.env.uid:
                raise AccessError(_('Only the requester can submit.'))
            self._lock_employee()
            attendance, fingerprint = self._lock_attendance()
            self._check_proposal()
            self._check_no_overlap()
            self._internal_write({
                'state': 'submitted', 'submitted_at': fields.Datetime.now(),
                'original_check_in': attendance.check_in,
                'original_check_out': attendance.check_out,
                'original_write_date': attendance.write_date,
                'original_fingerprint': fingerprint,
            })
            self._audit_note(_('Submitted'), _('Proposal frozen; no attendance has been changed.'))
        return True

    def action_approve(self):
        with self.env.cr.savepoint():
            self._lock()
            self._lock_employee()
            self._check_decider()
            self._serialize_employee_decision()
            attendance, fingerprint = self._lock_attendance()
            self._check_proposal()
            if attendance and (
                attendance.check_in != self.original_check_in
                or attendance.check_out != self.original_check_out
                or attendance.write_date != self.original_write_date
                or fingerprint != self.original_fingerprint
            ):
                raise UserError(_('Attendance changed since submission. Cancel and submit a fresh request.'))
            self._check_no_overlap()
            values = {'check_in': self.proposed_check_in, 'check_out': self.proposed_check_out}
            # IMPORTANT: never sudo attendance mutations. Native ACLs, record
            # rules, constraints and attendance/overtime computations all apply.
            native = self.env['hr.attendance'].with_context(self._safe_context())
            if attendance:
                native.browse(attendance.id).write(values)
            else:
                attendance = native.create(dict(values, employee_id=self.employee_id.id))
            self._internal_write({
                'state': 'approved', 'attendance_id': attendance.id,
                'decided_by': self.env.uid, 'decided_at': fields.Datetime.now(),
                'decision_reason': _('Approved as requested.'),
            })
            self._audit_note(_('Approved'), self.decision_reason, applied=True)
        return True

    def action_open_reject(self):
        self.ensure_one()
        self._check_decider()
        return {
            'type': 'ir.actions.act_window', 'name': _('Reject Attendance Correction'),
            'res_model': 'sl.attendance.correction.reject', 'view_mode': 'form',
            'view_id': self.env.ref('sl_attendance_correction.view_correction_reject_form').id,
            'target': 'new', 'context': {'default_request_id': self.id},
        }

    def action_reject(self, reason):
        with self.env.cr.savepoint():
            self._lock()
            self._lock_employee()
            self._check_decider()
            if not isinstance(reason, str) or not reason.strip():
                raise ValidationError(_('A rejection reason is required.'))
            self._internal_write({
                'state': 'rejected', 'decided_by': self.env.uid,
                'decided_at': fields.Datetime.now(), 'decision_reason': reason.strip(),
            })
            self._audit_note(_('Rejected'), _('%s No attendance was changed by this decision.', reason.strip()))
        return True

    def action_cancel(self):
        with self.env.cr.savepoint():
            self._lock()
            if self.state not in ('draft', 'submitted'):
                raise UserError(_('Only a draft or submitted request can be cancelled.'))
            if self.requester_id.id != self.env.uid:
                raise AccessError(_('Only the requester can cancel.'))
            self._internal_write({
                'state': 'cancelled', 'decided_by': self.env.uid,
                'decided_at': fields.Datetime.now(), 'decision_reason': _('Cancelled by requester.'),
            })
            self._audit_note(_('Cancelled'), _('No attendance was changed by this cancellation.'))
        return True
