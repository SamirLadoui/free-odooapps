# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSchoolAttendance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.year = cls.env['sl.academic.year'].create({
            'name': '2026 / 2027', 'code': 'AY-ATT',
            'date_start': date(2026, 9, 1), 'date_end': date(2027, 6, 30),
        })
        cls.standard = cls.env['sl.school.standard'].create({
            'name': 'Grade 3', 'academic_year_id': cls.year.id, 'capacity': 0})
        cls.other_standard = cls.env['sl.school.standard'].create({
            'name': 'Grade 4', 'academic_year_id': cls.year.id, 'capacity': 0})
        cls.students = cls.env['sl.student']
        for name in ('Ana', 'Ben', 'Cara'):
            student = cls.env['sl.student'].create({
                'name': name, 'standard_id': cls.standard.id})
            student.action_enrol()
            cls.students |= student
        cls.applicant = cls.env['sl.student'].create({
            'name': 'Not Enrolled', 'standard_id': cls.standard.id})
        cls.day = date(2026, 10, 1)

    def _register(self, **values):
        return self.env['sl.school.attendance'].create(dict({
            'standard_id': self.standard.id, 'date': self.day}, **values))

    # -- filling the register ----------------------------------------------

    def test_load_students_takes_the_enrolled_only(self):
        register = self._register()
        register.action_load_students()
        self.assertEqual(len(register.line_ids), 3)
        self.assertNotIn(self.applicant, register.line_ids.mapped('student_id'),
                         "an application is not an enrolment")

    def test_everyone_starts_present(self):
        """Most of a class is there; the teacher marks the exceptions."""
        register = self._register()
        register.action_load_students()
        self.assertEqual(set(register.line_ids.mapped('status')), {'present'})

    def test_loading_twice_does_not_duplicate(self):
        register = self._register()
        register.action_load_students()
        register.action_load_students()
        self.assertEqual(len(register.line_ids), 3)

    def test_loading_picks_up_a_new_student(self):
        register = self._register()
        register.action_load_students()
        newcomer = self.env['sl.student'].create({
            'name': 'Late Joiner', 'standard_id': self.standard.id})
        newcomer.action_enrol()
        register.action_load_students()
        self.assertEqual(len(register.line_ids), 4)

    def test_a_class_with_nobody_enrolled_says_so(self):
        register = self._register(standard_id=self.other_standard.id)
        with self.assertRaises(UserError):
            register.action_load_students()

    def test_a_confirmed_register_cannot_be_refilled(self):
        register = self._register()
        register.action_load_students()
        register.action_confirm()
        with self.assertRaises(UserError):
            register.action_load_students()

    # -- the numbers -------------------------------------------------------

    def test_counts_and_rate(self):
        register = self._register()
        register.action_load_students()
        lines = register.line_ids
        lines[0].status = 'absent'
        lines[1].status = 'late'
        self.assertEqual(register.total_count, 3)
        self.assertEqual(register.present_count, 2, "late still counts as present")
        self.assertEqual(register.absent_count, 1)
        self.assertAlmostEqual(register.attendance_rate, 200 / 3, places=2)

    def test_excused_counts_as_absent_for_the_rate(self):
        register = self._register()
        register.action_load_students()
        register.line_ids[0].status = 'excused'
        self.assertEqual(register.absent_count, 1)

    def test_empty_register_rate_is_zero_not_an_error(self):
        self.assertEqual(self._register().attendance_rate, 0.0)

    def test_mark_all_present(self):
        register = self._register()
        register.action_load_students()
        register.line_ids[0].status = 'absent'
        register.action_mark_all_present()
        self.assertEqual(register.absent_count, 0)

    # -- guards ------------------------------------------------------------

    def test_one_register_per_class_per_day(self):
        """Two registers for one class on one day and no report can say which."""
        self._register()
        with self.assertRaises(ValidationError):
            self._register()

    def test_another_class_may_share_the_day(self):
        self._register()
        self.assertTrue(self._register(standard_id=self.other_standard.id))

    def test_the_same_class_may_have_another_day(self):
        self._register()
        self.assertTrue(self._register(date=self.day + timedelta(days=1)))

    def test_a_date_outside_the_academic_year_is_refused(self):
        with self.assertRaises(ValidationError):
            self._register(date=date(2027, 8, 1))

    def test_a_student_from_another_class_is_refused(self):
        outsider = self.env['sl.student'].create({
            'name': 'Outsider', 'standard_id': self.other_standard.id})
        outsider.action_enrol()
        register = self._register()
        with self.assertRaises(ValidationError):
            register.line_ids = [(0, 0, {'student_id': outsider.id})]

    def test_a_student_cannot_appear_twice(self):
        register = self._register()
        register.action_load_students()
        with self.assertRaises(ValidationError):
            register.line_ids = [(0, 0, {'student_id': self.students[0].id})]

    def test_confirming_an_empty_register_is_refused(self):
        with self.assertRaises(UserError):
            self._register().action_confirm()

    def test_teacher_defaults_from_the_class(self):
        teacher = self.env['sl.teacher'].create({'name': 'Class Teacher'})
        self.standard.class_teacher_id = teacher
        register = self.env['sl.school.attendance'].new({
            'standard_id': self.standard.id})
        register._onchange_standard_id()
        self.assertEqual(register.taken_by_id, teacher)

    # -- the student's own rate --------------------------------------------

    def test_student_rate_counts_confirmed_registers_only(self):
        """A draft register is not yet a fact about anybody."""
        first = self._register()
        first.action_load_students()
        first.line_ids.filtered(lambda l: l.student_id == self.students[0]).status = 'absent'
        self.assertEqual(self.students[0].attendance_rate, 0.0,
                         "nothing is confirmed yet")

        first.action_confirm()
        self.students[0].invalidate_recordset(['attendance_rate'])
        self.assertEqual(self.students[0].attendance_rate, 0.0)
        self.students[1].invalidate_recordset(['attendance_rate'])
        self.assertEqual(self.students[1].attendance_rate, 100.0)

    def test_student_rate_over_several_days(self):
        for offset in range(4):
            register = self._register(date=self.day + timedelta(days=offset))
            register.action_load_students()
            if offset == 0:
                register.line_ids.filtered(
                    lambda l: l.student_id == self.students[0]).status = 'absent'
            register.action_confirm()
        self.students[0].invalidate_recordset(['attendance_rate'])
        self.assertEqual(self.students[0].attendance_rate, 75.0)
