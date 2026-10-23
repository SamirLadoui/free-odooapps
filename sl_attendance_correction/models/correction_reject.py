# Copyright 2026 Samir Ladoui
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
from odoo import fields, models


class AttendanceCorrectionReject(models.TransientModel):
    _name = 'sl.attendance.correction.reject'
    _description = 'Reject Attendance Correction'

    request_id = fields.Many2one('sl.attendance.correction', required=True, readonly=True,
                                ondelete='cascade')
    reason = fields.Text(required=True)

    def action_reject(self):
        self.ensure_one()
        self.check_access_rights('read')
        self.check_access_rule('read')
        # The target action rechecks role, company, ownership, state and reason.
        self.request_id.action_reject(self.reason)
        return {'type': 'ir.actions.act_window_close'}
