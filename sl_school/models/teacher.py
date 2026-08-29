# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Teacher(models.Model):
    _name = 'sl.teacher'
    _description = 'Teacher'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string='Staff Number', copy=False, readonly=True, default='/')
    active = fields.Boolean(default=True)
    image = fields.Image(max_width=1024, max_height=1024)

    email = fields.Char(tracking=True)
    phone = fields.Char()
    user_id = fields.Many2one(
        'res.users', string='Odoo User', ondelete='set null',
        help="Link the teacher to a login so they can see their own classes.")

    subject_ids = fields.Many2many('sl.subject', string='Subjects')
    standard_ids = fields.One2many('sl.school.standard', 'class_teacher_id',
                                   string='Classes Managed')
    standard_count = fields.Integer(compute='_compute_standard_count')

    joining_date = fields.Date()
    qualification = fields.Char()

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'That staff number is already used.'),
    ]

    @api.depends('standard_ids')
    def _compute_standard_count(self):
        for teacher in self:
            teacher.standard_count = len(teacher.standard_ids)

    @api.constrains('email')
    def _check_email(self):
        for teacher in self:
            if teacher.email and '@' not in teacher.email:
                raise ValidationError(_("'%s' does not look like an email address.") % teacher.email)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', '/') == '/':
                vals['code'] = self.env['ir.sequence'].next_by_code('sl.teacher') or '/'
        return super().create(vals_list)
