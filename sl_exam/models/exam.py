# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Boundaries are inclusive at the bottom: 80 is an A, 79.99 is a B.
GRADE_BANDS = [
    (90.0, 'A+'), (80.0, 'A'), (70.0, 'B'),
    (60.0, 'C'), (50.0, 'D'), (0.0, 'F'),
]


class Exam(models.Model):
    _name = 'sl.exam'
    _description = 'Exam'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char(string='Exam', required=True, tracking=True)
    code = fields.Char(string='Reference', copy=False, readonly=True, default='/')
    standard_id = fields.Many2one(
        'sl.school.standard', string='Class', required=True,
        ondelete='cascade', tracking=True)
    subject_id = fields.Many2one(
        'sl.subject', string='Subject', required=True, ondelete='restrict')
    academic_year_id = fields.Many2one(
        related='standard_id.academic_year_id', store=True)

    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    total_marks = fields.Float(default=100.0, required=True, tracking=True)
    passing_marks = fields.Float(default=40.0, required=True, tracking=True)

    state = fields.Selection(
        [('draft', 'Planned'), ('marking', 'Marking'),
         ('published', 'Published'), ('cancelled', 'Cancelled')],
        default='draft', required=True, tracking=True)

    result_ids = fields.One2many('sl.exam.result', 'exam_id', string='Results')
    result_count = fields.Integer(compute='_compute_stats', store=True)
    passed_count = fields.Integer(compute='_compute_stats', store=True)
    pass_rate = fields.Float(compute='_compute_stats', store=True)
    average_marks = fields.Float(compute='_compute_stats', store=True)
    highest_marks = fields.Float(compute='_compute_stats', store=True)

    @api.depends('result_ids.marks', 'result_ids.passed')
    def _compute_stats(self):
        for exam in self:
            marked = exam.result_ids.filtered(lambda r: r.marked and not r.absent)
            exam.result_count = len(marked)
            passed = marked.filtered('passed')
            exam.passed_count = len(passed)
            exam.pass_rate = (len(passed) / len(marked)) * 100 if marked else 0.0
            values = marked.mapped('marks')
            exam.average_marks = (sum(values) / len(values)) if values else 0.0
            exam.highest_marks = max(values) if values else 0.0

    @api.depends('name', 'subject_id')
    def _compute_display_name(self):
        for exam in self:
            exam.display_name = '%s - %s' % (
                exam.name or '', exam.subject_id.name or '')

    @api.constrains('total_marks', 'passing_marks')
    def _check_marks(self):
        for exam in self:
            if exam.total_marks <= 0:
                raise ValidationError(_("An exam must be worth more than zero marks."))
            if exam.passing_marks < 0:
                raise ValidationError(_("The pass mark cannot be negative."))
            if exam.passing_marks > exam.total_marks:
                raise ValidationError(_(
                    "The pass mark (%(pass)s) is above the total (%(total)s), so "
                    "nobody could pass.") % {
                        'pass': exam.passing_marks, 'total': exam.total_marks})

    @api.constrains('date', 'standard_id')
    def _check_date_within_year(self):
        for exam in self.filtered('standard_id'):
            year = exam.standard_id.academic_year_id
            if year and not (year.date_start <= exam.date <= year.date_end):
                raise ValidationError(_(
                    "%(date)s falls outside the academic year %(year)s.") % {
                        'date': exam.date, 'year': year.name})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', '/') == '/':
                vals['code'] = self.env['ir.sequence'].next_by_code('sl.exam') or '/'
        return super().create(vals_list)

    # -- workflow ----------------------------------------------------------

    def action_load_students(self):
        """Put every enrolled student on the mark sheet, unmarked."""
        self.ensure_one()
        if self.state == 'published':
            raise UserError(_("Published results cannot be refilled."))
        enrolled = self.standard_id.student_ids.filtered(
            lambda s: s.state == 'enrolled')
        if not enrolled:
            raise UserError(_(
                "%s has no enrolled students.") % self.standard_id.display_name)
        existing = self.result_ids.mapped('student_id')
        self.result_ids = [(0, 0, {'student_id': student.id})
                           for student in enrolled - existing]
        return True

    def action_start_marking(self):
        for exam in self:
            if not exam.result_ids:
                exam.action_load_students()
        self.write({'state': 'marking'})

    def action_publish(self):
        """Publishing is telling students their result, so it has to be complete."""
        for exam in self:
            unmarked = exam.result_ids.filtered(
                lambda r: not r.marked and not r.absent)
            if unmarked:
                raise ValidationError(_(
                    "%(count)s student(s) on %(exam)s are still unmarked.") % {
                        'count': len(unmarked), 'exam': exam.display_name})
            if not exam.result_ids:
                raise ValidationError(_(
                    "%s has no results to publish.") % exam.display_name)
        self.write({'state': 'published'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})


class ExamResult(models.Model):
    _name = 'sl.exam.result'
    _description = 'Exam Result'
    _order = 'exam_id, student_id'

    exam_id = fields.Many2one('sl.exam', required=True, ondelete='cascade')
    student_id = fields.Many2one(
        'sl.student', string='Student', required=True, ondelete='cascade')
    standard_id = fields.Many2one(related='exam_id.standard_id', store=True)
    subject_id = fields.Many2one(related='exam_id.subject_id', store=True)
    total_marks = fields.Float(related='exam_id.total_marks')

    marked = fields.Boolean(
        string='Marked',
        help="Ticked once the paper has been marked. A Float cannot be empty in "
             "Odoo, so this is what separates a genuine score of zero from a "
             "paper nobody has looked at yet.")
    marks = fields.Float()
    percentage = fields.Float(compute='_compute_result', store=True)
    grade = fields.Char(compute='_compute_result', store=True)
    passed = fields.Boolean(compute='_compute_result', store=True)
    absent = fields.Boolean(help="Sat no paper. Excluded from the exam averages.")
    remark = fields.Char()

    @api.depends('marks', 'marked', 'exam_id.total_marks',
                 'exam_id.passing_marks', 'absent')
    def _compute_result(self):
        for result in self:
            if result.absent or not result.marked or not result.exam_id.total_marks:
                result.percentage = 0.0
                result.grade = ''
                result.passed = False
                continue
            result.percentage = (result.marks / result.exam_id.total_marks) * 100
            result.passed = result.marks >= result.exam_id.passing_marks
            result.grade = self._grade_for(result.percentage)

    @api.model
    def _grade_for(self, percentage):
        for floor, letter in GRADE_BANDS:
            if percentage >= floor:
                return letter
        return 'F'

    @api.onchange('marks')
    def _onchange_marks(self):
        """Entering a mark is the usual way a paper becomes marked; a genuine
        zero is recorded by ticking Marked by hand."""
        if self.marks:
            self.marked = True

    @api.constrains('marks', 'exam_id')
    def _check_marks_within_total(self):
        for result in self:
            if result.marks < 0:
                raise ValidationError(_("Marks cannot be negative."))
            if result.marks > result.exam_id.total_marks:
                raise ValidationError(_(
                    "%(marks)s is more than the %(total)s this exam is worth.") % {
                        'marks': result.marks, 'total': result.exam_id.total_marks})

    @api.constrains('student_id', 'exam_id')
    def _check_student_once(self):
        for result in self:
            twin = self.search([
                ('id', '!=', result.id),
                ('exam_id', '=', result.exam_id.id),
                ('student_id', '=', result.student_id.id),
            ], limit=1)
            if twin:
                raise ValidationError(_(
                    "%s already has a result for this exam.")
                    % result.student_id.display_name)

    @api.constrains('student_id', 'exam_id')
    def _check_student_in_class(self):
        for result in self:
            if result.student_id.standard_id != result.exam_id.standard_id:
                raise ValidationError(_(
                    "%(student)s is not in %(standard)s.") % {
                        'student': result.student_id.display_name,
                        'standard': result.exam_id.standard_id.display_name})


class Student(models.Model):
    _inherit = 'sl.student'

    exam_result_ids = fields.One2many(
        'sl.exam.result', 'student_id', string='Exam Results')
    exam_average = fields.Float(
        compute='_compute_exam_average',
        help="Average percentage across published exams.")

    @api.depends('exam_result_ids.percentage', 'exam_result_ids.exam_id.state')
    def _compute_exam_average(self):
        for student in self:
            published = student.exam_result_ids.filtered(
                lambda r: r.exam_id.state == 'published' and not r.absent)
            values = published.mapped('percentage')
            student.exam_average = (sum(values) / len(values)) if values else 0.0
