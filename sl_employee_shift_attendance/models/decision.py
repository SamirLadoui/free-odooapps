# SPDX-License-Identifier: LGPL-3.0-or-later
from odoo import fields, models, _
from odoo.exceptions import AccessError


class ShiftDecision(models.TransientModel):
    _name = 'sl.shift.decision'
    _description = 'Decide Shift Overtime'

    day_id = fields.Many2one('sl.shift.day', required=True, readonly=True)
    decision = fields.Selection([('approve', 'Approve'), ('refuse', 'Refuse')], default='approve', required=True)
    hours = fields.Float(required=True)
    reason = fields.Text(required=True)

    def action_confirm(self):
        self.ensure_one()
        self.check_access_rights('read')
        self.check_access_rule('read')
        if self.decision == 'approve':
            self.day_id.action_approve(self.hours, self.reason)
        else:
            self.day_id.action_refuse(self.reason)
        return {'type': 'ir.actions.act_window_close'}


class ShiftDay(models.Model):
    _inherit = 'sl.shift.day'

    def action_open_decision(self):
        self.ensure_one()
        self.check_access_rights('read')
        self.check_access_rule('read')
        if not self.env.user.has_group('sl_employee_shift_attendance.group_shift_approver'):
            raise AccessError(_('Only a Shift Overtime Approver can decide overtime.'))
        return {'type': 'ir.actions.act_window', 'name': _('Decide Shift Overtime'),
                'res_model': 'sl.shift.decision', 'view_mode': 'form', 'target': 'new',
                'context': {'default_day_id': self.id, 'default_hours': self.raw_overtime_hours}}
