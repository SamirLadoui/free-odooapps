# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

PRESENT_STATES = ('present', 'late')


class Attendance(models.Model):
    _name = 'sl.school.attendance'
    _description = 'Attendance Register'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'
    _rec_name = 'display_name'

    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    standard_id = fields.Many2one(
        'sl.school.standard', string='Class', required=True,
        ondelete='cascade', tracking=True)
    academic_year_id = fields.Many2one(
        related='standard_id.academic_year_id', store=True)
    taken_by_id = fields.Many2one(
        'sl.teacher', string='Taken By', tracking=True,
        help="Defaults to the class teacher.")

    state = fields.Selection(
        [('draft', 'Draft'), ('confirmed', 'Confirmed')],
        default='draft', required=True, tracking=True)

    line_ids = fields.One2many('sl.school.attendance.line', 'attendance_id', string='Register')
    present_count = fields.Integer(compute='_compute_counts', store=True)
    absent_count = fields.Integer(compute='_compute_counts', store=True)
    total_count = fields.Integer(compute='_compute_counts', store=True)
    attendance_rate = fields.Float(
        compute='_compute_counts', store=True,
        help="Percentage of the class present, counting late arrivals as present.")

    @api.depends('line_ids.status')
    def _compute_counts(self):
        for register in self:
            lines = register.line_ids
            present = lines.filtered(lambda l: l.status in PRESENT_STATES)
            register.total_count = len(lines)
            register.present_count = len(present)
            register.absent_count = len(lines) - len(present)
            register.attendance_rate = (
                (len(present) / len(lines)) * 100 if lines else 0.0)

    @api.depends('standard_id', 'date')
    def _compute_display_name(self):
        for register in self:
            register.display_name = '%s - %s' % (
                register.standard_id.display_name or '', register.date or '')

    @api.constrains('standard_id', 'date')
    def _check_one_register_per_day(self):
        """Two registers for one class on one day means one of them is wrong,
        and no report can tell you which."""
        for register in self:
            clash = self.search([
                ('id', '!=', register.id),
                ('standard_id', '=', register.standard_id.id),
                ('date', '=', register.date),
            ], limit=1)
            if clash:
                raise ValidationError(_(
                    "%(standard)s already has a register for %(date)s.") % {
                        'standard': register.standard_id.display_name,
                        'date': register.date})

    @api.constrains('date', 'standard_id')
    def _check_date_within_year(self):
        for register in self.filtered('standard_id'):
            year = register.standard_id.academic_year_id
            if year and not (year.date_start <= register.date <= year.date_end):
                raise ValidationError(_(
                    "%(date)s falls outside the academic year %(year)s.") % {
                        'date': register.date, 'year': year.name})

    @api.onchange('standard_id')
    def _onchange_standard_id(self):
        if self.standard_id and not self.taken_by_id:
            self.taken_by_id = self.standard_id.class_teacher_id

    # -- filling the register ----------------------------------------------

    def action_load_students(self):
        """Put every enrolled student on the register, marked present.

        Present by default because in a normal class most people are there;
        the teacher marks the exceptions, which is far fewer clicks.
        """
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("This register is confirmed and cannot be refilled."))
        enrolled = self.standard_id.student_ids.filtered(
            lambda s: s.state == 'enrolled')
        if not enrolled:
            raise UserError(_(
                "%s has no enrolled students.") % self.standard_id.display_name)

        existing = self.line_ids.mapped('student_id')
        self.line_ids = [(0, 0, {
            'student_id': student.id,
            'status': 'present',
        }) for student in enrolled - existing]
        return True

    def action_mark_all_present(self):
        self.ensure_one()
        self.line_ids.write({'status': 'present'})
        return True

    def action_confirm(self):
        for register in self:
            if not register.line_ids:
                raise UserError(_(
                    "%s has nobody on it.") % register.display_name)
        self.write({'state': 'confirmed'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})


class AttendanceLine(models.Model):
    _name = 'sl.school.attendance.line'
    _description = 'Attendance Line'
    _order = 'attendance_id, student_id'

    attendance_id = fields.Many2one(
        'sl.school.attendance', required=True, ondelete='cascade')
    student_id = fields.Many2one(
        'sl.student', string='Student', required=True, ondelete='cascade')
    standard_id = fields.Many2one(related='attendance_id.standard_id', store=True)
    date = fields.Date(related='attendance_id.date', store=True)
    status = fields.Selection(
        [('present', 'Present'), ('late', 'Late'),
         ('absent', 'Absent'), ('excused', 'Excused')],
        default='present', required=True)
    note = fields.Char()

    @api.constrains('student_id', 'attendance_id')
    def _check_student_in_class(self):
        """A student on another class's register makes the numbers meaningless."""
        for line in self:
            standard = line.attendance_id.standard_id
            if line.student_id.standard_id != standard:
                raise ValidationError(_(
                    "%(student)s is not in %(standard)s.") % {
                        'student': line.student_id.display_name,
                        'standard': standard.display_name})

    @api.constrains('student_id', 'attendance_id')
    def _check_student_once(self):
        for line in self:
            twin = self.search([
                ('id', '!=', line.id),
                ('attendance_id', '=', line.attendance_id.id),
                ('student_id', '=', line.student_id.id),
            ], limit=1)
            if twin:
                raise ValidationError(_(
                    "%s is on this register twice.") % line.student_id.display_name)


class Student(models.Model):
    _inherit = 'sl.student'

    attendance_line_ids = fields.One2many(
        'sl.school.attendance.line', 'student_id', string='Attendance')
    attendance_rate = fields.Float(
        compute='_compute_attendance_rate',
        help="Percentage of confirmed registers this student was present for.")

    @api.depends('attendance_line_ids.status', 'attendance_line_ids.attendance_id.state')
    def _compute_attendance_rate(self):
        for student in self:
            lines = student.attendance_line_ids.filtered(
                lambda l: l.attendance_id.state == 'confirmed')
            present = lines.filtered(lambda l: l.status in PRESENT_STATES)
            student.attendance_rate = (
                (len(present) / len(lines)) * 100 if lines else 0.0)
