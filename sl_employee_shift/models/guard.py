# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class ShiftGuard(models.Model):
    """Core-owned serialization row for roster changes by employee."""
    _name = 'sl.shift.guard'
    _description = 'Shift Mutation Coordination'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade', index=True)
    generation = fields.Integer(default=0)

    _sql_constraints = [
        ('employee_unique', 'UNIQUE(employee_id)', 'One coordination row per employee.'),
    ]

    @api.model
    def _sl_lock(self, employee_ids):
        """Advance each employee row so stale REPEATABLE READ writers conflict."""
        for employee_id in sorted(set(employee_ids) - {False, None}):
            self.env.cr.execute('''
                INSERT INTO sl_shift_guard (employee_id, generation)
                VALUES (%s, 1)
                ON CONFLICT (employee_id) DO UPDATE
                SET generation = sl_shift_guard.generation + 1
                RETURNING id
            ''', (employee_id,))
            self.env.cr.fetchone()

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Coordination rows are maintained internally.'))

    def write(self, vals):
        raise AccessError(_('Coordination rows are maintained internally.'))

    def unlink(self):
        raise AccessError(_('Coordination rows are maintained internally.'))
