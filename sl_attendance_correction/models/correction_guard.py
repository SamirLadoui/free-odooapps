# Copyright 2026 Samir Ladoui
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
from odoo import fields, models


class AttendanceCorrectionGuard(models.Model):
    _name = 'sl.attendance.correction.guard'
    _description = 'Attendance Correction Transaction Guard'
    _rec_name = 'employee_id'

    employee_id = fields.Many2one('hr.employee', required=True, readonly=True, ondelete='cascade')
    revision = fields.Integer(readonly=True)

    _sql_constraints = [  # noqa: RUF012 -- native Odoo SQL constraint declaration.
        ('employee_unique', 'UNIQUE(employee_id)', 'One transaction guard per employee.'),
    ]
