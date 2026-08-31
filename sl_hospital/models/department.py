# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Department(models.Model):
    _name = 'sl.hospital.department'
    _description = 'Hospital Department'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    head_doctor_id = fields.Many2one('sl.hospital.doctor', string='Head of Department')
    doctor_ids = fields.One2many('sl.hospital.doctor', 'department_id', string='Doctors')
    doctor_count = fields.Integer(compute='_compute_doctor_count')
    note = fields.Text()
    active = fields.Boolean(default=True)

    @api.constrains('code')
    def _check_code_unique(self):
        """A python constraint rather than _sql_constraints: 19.0 dropped
        support for the latter and would silently create no constraint."""
        for department in self:
            if self.search_count([('id', '!=', department.id),
                                  ('code', '=', department.code)]):
                raise ValidationError(
                    _("Department code '%s' is already used.") % department.code)

    @api.depends('doctor_ids')
    def _compute_doctor_count(self):
        for department in self:
            department.doctor_count = len(department.doctor_ids)

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for department in self:
            department.display_name = '[%s] %s' % (department.code, department.name)
