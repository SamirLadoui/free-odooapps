# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Subject(models.Model):
    _name = 'sl.subject'
    _description = 'Subject'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    subject_type = fields.Selection(
        [('theory', 'Theory'), ('practical', 'Practical'), ('both', 'Theory and Practical')],
        default='theory', required=True)
    credits = fields.Float(default=1.0)
    is_elective = fields.Boolean(
        string='Elective',
        help="Elective subjects are chosen by the student rather than assigned to the class.")
    teacher_ids = fields.Many2many('sl.teacher', string='Teachers')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'That subject code is already used.'),
    ]

    @api.constrains('credits')
    def _check_credits(self):
        for subject in self:
            if subject.credits <= 0:
                raise ValidationError(_("A subject must be worth more than zero credits."))

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for subject in self:
            subject.display_name = '[%s] %s' % (subject.code, subject.name)
