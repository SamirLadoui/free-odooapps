# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Student(models.Model):
    _name = 'sl.student'
    _description = 'Student'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'standard_id, roll_number, name'
    _rec_names_search = ['name', 'code', 'roll_number']

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string='Student Number', copy=False, readonly=True, default='/')
    roll_number = fields.Integer(tracking=True, help="Position in the class register.")
    active = fields.Boolean(default=True)
    image = fields.Image(max_width=1024, max_height=1024)

    state = fields.Selection(
        [('draft', 'Application'), ('enrolled', 'Enrolled'),
         ('alumni', 'Alumni'), ('left', 'Left')],
        default='draft', required=True, tracking=True)

    standard_id = fields.Many2one('sl.school.standard', string='Class', tracking=True)
    academic_year_id = fields.Many2one(
        related='standard_id.academic_year_id', string='Academic Year', store=True)
    elective_subject_ids = fields.Many2many(
        'sl.subject', string='Elective Subjects',
        domain="[('is_elective', '=', True)]")

    birth_date = fields.Date(tracking=True)
    age = fields.Integer(compute='_compute_age')
    gender = fields.Selection(
        [('male', 'Male'), ('female', 'Female'), ('other', 'Other')])
    blood_group = fields.Selection(
        [('a+', 'A+'), ('a-', 'A-'), ('b+', 'B+'), ('b-', 'B-'),
         ('ab+', 'AB+'), ('ab-', 'AB-'), ('o+', 'O+'), ('o-', 'O-')])

    email = fields.Char()
    phone = fields.Char()
    street = fields.Char()
    city = fields.Char()
    zip = fields.Char(string='ZIP')
    country_id = fields.Many2one('res.country', string='Country')

    guardian_name = fields.Char(tracking=True)
    guardian_phone = fields.Char()
    guardian_email = fields.Char()
    guardian_relation = fields.Selection(
        [('mother', 'Mother'), ('father', 'Father'), ('other', 'Other')])

    admission_date = fields.Date(default=fields.Date.context_today, tracking=True)
    partner_id = fields.Many2one(
        'res.partner', string='Contact', ondelete='set null', copy=False,
        help="Created on enrolment so the student can be invoiced or emailed.")

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'That student number is already used.'),
        ('roll_number_unique', 'unique(standard_id, roll_number)',
         'That roll number is already taken in this class.'),
    ]

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for student in self:
            student.display_name = ('%s (%s)' % (student.name, student.code)
                                    if student.code and student.code != '/' else student.name)

    @api.depends('birth_date')
    def _compute_age(self):
        today = fields.Date.context_today(self)
        for student in self:
            student.age = (relativedelta(today, student.birth_date).years
                           if student.birth_date else 0)

    @api.constrains('birth_date')
    def _check_birth_date(self):
        today = fields.Date.context_today(self)
        for student in self.filtered('birth_date'):
            if student.birth_date > today:
                raise ValidationError(_("A student cannot be born in the future."))

    @api.constrains('roll_number')
    def _check_roll_number(self):
        for student in self:
            if student.roll_number < 0:
                raise ValidationError(_("A roll number cannot be negative."))

    @api.constrains('state', 'standard_id')
    def _check_class_capacity(self):
        """Enrolling past capacity is the mistake this module exists to catch."""
        for student in self.filtered(lambda s: s.state == 'enrolled' and s.standard_id):
            standard = student.standard_id
            if standard.capacity and standard.student_count > standard.capacity:
                raise ValidationError(_(
                    "%(standard)s is full: %(capacity)s of %(capacity)s seats taken.")
                    % {'standard': standard.display_name, 'capacity': standard.capacity})

    @api.constrains('state', 'standard_id')
    def _check_enrolled_has_class(self):
        for student in self:
            if student.state == 'enrolled' and not student.standard_id:
                raise ValidationError(_(
                    "%s cannot be enrolled without a class.") % student.name)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', '/') == '/':
                vals['code'] = self.env['ir.sequence'].next_by_code('sl.student') or '/'
        return super().create(vals_list)

    # -- workflow ----------------------------------------------------------

    def action_enrol(self):
        for student in self:
            if not student.standard_id:
                raise ValidationError(_(
                    "Choose a class for %s before enrolling them.") % student.name)
            if not student.partner_id:
                student.partner_id = student._create_partner()
        self.write({'state': 'enrolled'})

    def action_set_alumni(self):
        self.write({'state': 'alumni'})

    def action_set_left(self):
        self.write({'state': 'left'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    def _create_partner(self):
        self.ensure_one()
        return self.env['res.partner'].create({
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'street': self.street,
            'city': self.city,
            'zip': self.zip,
            'country_id': self.country_id.id,
        })
