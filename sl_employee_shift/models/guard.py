# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class ShiftGuard(models.Model):
    _name = 'sl.shift.guard'
    _description = 'Shift Mutation Coordination'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade', index=True)
    generation = fields.Integer(default=0)
    _sql_constraints = [('employee_unique', 'UNIQUE(employee_id)', 'One coordination row per employee.')]

    @api.model
    def _sl_lock(self, employee_ids):
        # Updating our own coordination row forces stale REPEATABLE READ writers
        # to serialize/retry, unlike SELECT FOR UPDATE on an unchanged HR row.
        for employee_id in sorted(set(employee_ids)):
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
