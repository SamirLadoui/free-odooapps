# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    appraisal_ids = fields.One2many('sl.appraisal', 'employee_id')
    appraisal_count = fields.Integer(compute='_compute_appraisal_count')
    last_appraisal_score = fields.Float(compute='_compute_appraisal_count')

    @api.depends('appraisal_ids', 'appraisal_ids.state', 'appraisal_ids.score')
    def _compute_appraisal_count(self):
        for employee in self:
            employee.appraisal_count = len(employee.appraisal_ids)
            done = employee.appraisal_ids.filtered(lambda a: a.state == 'done')
            employee.last_appraisal_score = done[0].score if done else 0.0

    def action_view_appraisals(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Appraisals"),
            'res_model': 'sl.appraisal',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
