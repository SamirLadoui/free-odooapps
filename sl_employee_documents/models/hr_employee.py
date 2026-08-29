# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    document_ids = fields.One2many('sl.employee.document', 'employee_id')
    document_count = fields.Integer(compute='_compute_document_counts')
    expiring_document_count = fields.Integer(compute='_compute_document_counts')

    @api.depends('document_ids', 'document_ids.state')
    def _compute_document_counts(self):
        for employee in self:
            documents = employee.document_ids
            employee.document_count = len(documents)
            employee.expiring_document_count = len(
                documents.filtered(lambda d: d.state in ('expiring', 'expired')))

    def action_view_documents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Documents"),
            'res_model': 'sl.employee.document',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
