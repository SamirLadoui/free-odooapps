# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    sl_device_user_id = fields.Char(
        string='Biometric ID',
        help="The user number this employee is enrolled under on the device.")

    @api.constrains('sl_device_user_id')
    def _check_device_user_unique(self):
        """Two employees on one device id would silently mix their hours."""
        for employee in self.filtered('sl_device_user_id'):
            clash = self.search([
                ('id', '!=', employee.id),
                ('sl_device_user_id', '=', employee.sl_device_user_id),
            ], limit=1)
            if clash:
                raise ValidationError(_(
                    "Biometric ID '%(id)s' is already used by %(name)s.")
                    % {'id': employee.sl_device_user_id, 'name': clash.name})
