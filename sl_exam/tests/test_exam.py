# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestExam(TransactionCase):

    def setUp(self):
        # 14.0 has no class-level env: setUpClass cannot build fixtures.
        super().setUp()
        self.year = self.env['sl.academic.year'].create({
            'name': '2026 / 2027', 'code': 'AY-EXM',
            'date_start': date(2026, 9, 1), 'date_end': date(2027, 6, 30)})
        self.standard = self.env['sl.school.standard'].create({
            'name': 'Grade 6', 'academic_year_id': self.year.id, 'capacity': 0})
        self.other_standard = self.env['sl.school.standard'].create({
            'name': 'Grade 7', 'academic_year_id': self.year.id, 'capacity': 0})
        self.subject = self.env['sl.subject'].create({
            'name': 'Mathematics', 'code': 'MATH-EX'})
        self.students = self.env['sl.student']
        for name in ('Ana', 'Ben', 'Cara'):
            student = self.env['sl.student'].create({
                'name': name, 'standard_id': self.standard.id})
            student.action_enrol()
            self.students |= student

    def _exam(self, **values):
        return self.env['sl.exam'].create(dict({
            'name': 'Mid-term', 'standard_id': self.standard.id,
            'subject_id': self.subject.id, 'date': date(2026, 11, 1),
            'total_marks': 100.0, 'passing_marks': 40.0}, **values))

    def _mark(self, exam, student, marks):
        line = exam.result_ids.filtered(lambda r: r.student_id == student)
        line.write({'marks': marks, 'marked': True})
        return line

    # -- grading -----------------------------------------------------------

    def test_grade_bands(self):
        Result = self.env['sl.exam.result']
        for percentage, expected in (
            (100, 'A+'), (90, 'A+'), (89.99, 'A'), (80, 'A'),
            (79.9, 'B'), (70, 'B'), (69, 'C'), (60, 'C'),
            (59, 'D'), (50, 'D'), (49, 'F'), (0, 'F'),
        ):
            self.assertEqual(Result._grade_for(percentage), expected,
                             'wrong grade for %s%%' % percentage)

    def test_percentage_and_pass(self):
        exam = self._exam()
        exam.action_start_marking()
        line = self._mark(exam, self.students[0], 75)
        self.assertAlmostEqual(line.percentage, 75.0, places=2)
        self.assertEqual(line.grade, 'B')
        self.assertTrue(line.passed)

    def test_exactly_the_pass_mark_passes(self):
        exam = self._exam()
        exam.action_start_marking()
        self.assertTrue(self._mark(exam, self.students[0], 40).passed)

    def test_just_below_the_pass_mark_fails(self):
        exam = self._exam()
        exam.action_start_marking()
        self.assertFalse(self._mark(exam, self.students[0], 39.9).passed)

    def test_percentage_uses_the_exam_total(self):
        exam = self._exam(total_marks=50.0, passing_marks=20.0)
        exam.action_start_marking()
        line = self._mark(exam, self.students[0], 25)
        self.assertAlmostEqual(line.percentage, 50.0, places=2)

    def test_an_unmarked_paper_is_not_a_fail(self):
        """Empty is not zero: nobody has looked at it yet."""
        exam = self._exam()
        exam.action_start_marking()
        line = exam.result_ids[0]
        self.assertFalse(line.passed)
        self.assertEqual(line.grade, '')
        self.assertEqual(line.percentage, 0.0)

    def test_a_genuine_zero_is_not_an_unmarked_paper(self):
        """Scoring nothing and not being marked are different facts."""
        exam = self._exam()
        exam.action_start_marking()
        line = self._mark(exam, self.students[0], 0)
        self.assertTrue(line.marked)
        self.assertEqual(line.grade, 'F')
        self.assertFalse(line.passed)
        self.assertEqual(exam.result_count, 1, "a real zero counts in the stats")

    def test_entering_a_mark_ticks_marked(self):
        exam = self._exam()
        exam.action_start_marking()
        line = exam.result_ids[0]
        line.marks = 55
        line._onchange_marks()
        self.assertTrue(line.marked)

    def test_an_absent_student_gets_no_grade(self):
        exam = self._exam()
        exam.action_start_marking()
        line = exam.result_ids[0]
        line.write({'absent': True, 'marks': 0, 'marked': True})
        self.assertEqual(line.grade, '')
        self.assertFalse(line.passed)

    # -- exam statistics ---------------------------------------------------

    def test_statistics(self):
        exam = self._exam()
        exam.action_start_marking()
        self._mark(exam, self.students[0], 80)
        self._mark(exam, self.students[1], 60)
        self._mark(exam, self.students[2], 20)
        self.assertEqual(exam.result_count, 3)
        self.assertEqual(exam.passed_count, 2)
        self.assertAlmostEqual(exam.pass_rate, 200 / 3, places=2)
        self.assertAlmostEqual(exam.average_marks, 160 / 3, places=2)
        self.assertEqual(exam.highest_marks, 80)

    def test_statistics_ignore_unmarked_papers(self):
        exam = self._exam()
        exam.action_start_marking()
        self._mark(exam, self.students[0], 80)
        self.assertEqual(exam.result_count, 1, "only marked papers count")
        self.assertEqual(exam.average_marks, 80)

    # -- guards ------------------------------------------------------------

    def test_marks_above_the_total_are_refused(self):
        exam = self._exam()
        exam.action_start_marking()
        with self.assertRaises(ValidationError):
            self._mark(exam, self.students[0], 101)

    def test_negative_marks_are_refused(self):
        exam = self._exam()
        exam.action_start_marking()
        with self.assertRaises(ValidationError):
            self._mark(exam, self.students[0], -1)

    def test_a_pass_mark_above_the_total_is_refused(self):
        """Nobody could pass, so it is always a mistake."""
        with self.assertRaises(ValidationError):
            self._exam(total_marks=50.0, passing_marks=60.0)

    def test_zero_total_marks_is_refused(self):
        with self.assertRaises(ValidationError):
            self._exam(total_marks=0)

    def test_a_date_outside_the_academic_year_is_refused(self):
        with self.assertRaises(ValidationError):
            self._exam(date=date(2027, 8, 15))

    def test_a_student_from_another_class_is_refused(self):
        outsider = self.env['sl.student'].create({
            'name': 'Outsider', 'standard_id': self.other_standard.id})
        outsider.action_enrol()
        exam = self._exam()
        with self.assertRaises(ValidationError):
            exam.result_ids = [(0, 0, {'student_id': outsider.id})]

    def test_a_student_cannot_appear_twice(self):
        exam = self._exam()
        exam.action_start_marking()
        with self.assertRaises(ValidationError):
            exam.result_ids = [(0, 0, {'student_id': self.students[0].id})]

    # -- workflow ----------------------------------------------------------

    def test_start_marking_loads_enrolled_students(self):
        applicant = self.env['sl.student'].create({
            'name': 'Applicant', 'standard_id': self.standard.id})
        exam = self._exam()
        exam.action_start_marking()
        self.assertEqual(len(exam.result_ids), 3)
        self.assertNotIn(applicant, exam.result_ids.mapped('student_id'))

    def test_loading_twice_does_not_duplicate(self):
        exam = self._exam()
        exam.action_start_marking()
        exam.action_load_students()
        self.assertEqual(len(exam.result_ids), 3)

    def test_publishing_needs_every_paper_marked(self):
        """Publishing tells students their result, so it has to be complete."""
        exam = self._exam()
        exam.action_start_marking()
        self._mark(exam, self.students[0], 70)
        with self.assertRaises(ValidationError):
            exam.action_publish()

    def test_an_absence_does_not_block_publishing(self):
        exam = self._exam()
        exam.action_start_marking()
        self._mark(exam, self.students[0], 70)
        self._mark(exam, self.students[1], 50)
        exam.result_ids.filtered(
            lambda r: r.student_id == self.students[2]).absent = True
        exam.action_publish()
        self.assertEqual(exam.state, 'published')

    def test_publishing_once_everything_is_marked(self):
        exam = self._exam()
        exam.action_start_marking()
        for student in self.students:
            self._mark(exam, student, 70)
        exam.action_publish()
        self.assertEqual(exam.state, 'published')

    def test_reference_is_generated(self):
        self.assertTrue(self._exam().code.startswith('EXM/'))

    # -- the student's average ---------------------------------------------

    def test_student_average_counts_published_exams_only(self):
        exam = self._exam()
        exam.action_start_marking()
        for student in self.students:
            self._mark(exam, student, 80)
        self.students[0].invalidate_cache(['exam_average'])
        self.assertEqual(self.students[0].exam_average, 0.0,
                         "nothing is published yet")

        exam.action_publish()
        self.students[0].invalidate_cache(['exam_average'])
        self.assertAlmostEqual(self.students[0].exam_average, 80.0, places=2)

    def test_student_average_excludes_absences(self):
        exam = self._exam()
        exam.action_start_marking()
        for student in self.students:
            self._mark(exam, student, 60)
        line = exam.result_ids.filtered(lambda r: r.student_id == self.students[0])
        line.absent = True
        exam.action_publish()
        self.students[0].invalidate_cache(['exam_average'])
        self.assertEqual(self.students[0].exam_average, 0.0,
                         "an absence is not a zero score")
