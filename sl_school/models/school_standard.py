# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SchoolStandard(models.Model):
    _name = 'sl.school.standard'
    _description = 'Class'
    _inherit = ['mail.thread']
    _order = 'academic_year_id desc, sequence, name'
    _rec_names_search = ['name', 'division']

    name = fields.Char(string='Grade', required=True, tracking=True,
                       help="For example Grade 5.")
    division = fields.Char(help="For example A, B or Blue. Leave empty if the grade is not split.")
    sequence = fields.Integer(default=10)
    academic_year_id = fields.Many2one(
        'sl.academic.year', string='Academic Year', required=True,
        ondelete='cascade', tracking=True)
    class_teacher_id = fields.Many2one('sl.teacher', string='Class Teacher', tracking=True)
    subject_ids = fields.Many2many('sl.subject', string='Subjects')
    student_ids = fields.One2many('sl.student', 'standard_id', string='Students')
    student_count = fields.Integer(compute='_compute_student_count', store=True)
    capacity = fields.Integer(
        default=30, tracking=True,
        help="Maximum number of enrolled students. Zero means no limit.")
    seats_left = fields.Integer(compute='_compute_student_count', store=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_division_year_unique',
         'unique(name, division, academic_year_id)',
         'That grade and division already exists for this academic year.'),
    ]

    @api.constrains('name', 'division', 'academic_year_id')
    def _check_grade_unique(self):
        """19.0 dropped support for _sql_constraints, so it is enforced here
        as well and the rule holds on every version."""
        for record in self.filtered('academic_year_id'):
            if self.search_count([
                    ('id', '!=', record.id),
                    ('name', '=', record.name),
                    ('division', '=', record.division),
                    ('academic_year_id', '=', record.academic_year_id.id),
            ]):
                raise ValidationError(_("That grade and division already exists for this academic year."))

    @api.depends('name', 'division', 'academic_year_id.name')
    def _compute_display_name(self):
        for standard in self:
            label = '%s - %s' % (standard.name, standard.division) if standard.division else standard.name
            standard.display_name = '%s (%s)' % (label, standard.academic_year_id.name or '')

    @api.depends('student_ids', 'student_ids.state', 'capacity')
    def _compute_student_count(self):
        for standard in self:
            enrolled = standard.student_ids.filtered(lambda s: s.state == 'enrolled')
            standard.student_count = len(enrolled)
            standard.seats_left = (standard.capacity - len(enrolled)) if standard.capacity else 0

    @api.constrains('capacity')
    def _check_capacity(self):
        for standard in self:
            if standard.capacity < 0:
                raise ValidationError(_("Capacity cannot be negative. Use zero for no limit."))
            if standard.capacity and standard.student_count > standard.capacity:
                raise ValidationError(_(
                    "%(name)s already has %(count)s enrolled students, "
                    "so its capacity cannot be set to %(capacity)s.")
                    % {'name': standard.display_name, 'count': standard.student_count,
                       'capacity': standard.capacity})

    def action_view_students(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Students"),
            'res_model': 'sl.student',
            'view_mode': 'kanban,list,form',
            'domain': [('standard_id', '=', self.id)],
            'context': {'default_standard_id': self.id},
        }
