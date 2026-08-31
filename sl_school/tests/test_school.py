# -*- coding: utf-8 -*-
from datetime import date, timedelta

import psycopg2

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo import fields

# Up to 18.0 a duplicate trips the database constraint; 19.0 dropped support
# for _sql_constraints, so the python constraint raises instead. Both mean the
# same thing: the duplicate was refused.
UNIQUE_ERRORS = (psycopg2.IntegrityError, ValidationError)
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestSchool(TransactionCase):

    def setUp(self):
        # 14.0 has no class-level env: setUpClass cannot build fixtures.
        super().setUp()
        self.year = self.env['sl.academic.year'].create({
            'name': '2025 / 2026', 'code': 'AY-2526',
            'date_start': date(2025, 9, 1), 'date_end': date(2026, 6, 30),
        })
        self.teacher = self.env['sl.teacher'].create({'name': 'Ada Lovelace'})
        self.standard = self.env['sl.school.standard'].create({
            'name': 'Grade 5', 'division': 'A',
            'academic_year_id': self.year.id,
            'class_teacher_id': self.teacher.id,
            'capacity': 2,
        })

    def _student(self, name, **values):
        return self.env['sl.student'].create(dict(
            {'name': name, 'standard_id': self.standard.id}, **values))

    # -- academic year -----------------------------------------------------

    def test_year_must_end_after_it_starts(self):
        with self.assertRaises(ValidationError):
            self.env['sl.academic.year'].create({
                'name': 'Backwards', 'code': 'BAD',
                'date_start': date(2026, 1, 1), 'date_end': date(2025, 1, 1),
            })

    def test_only_one_running_year_at_a_time(self):
        self.year.action_open()
        overlapping = self.env['sl.academic.year'].create({
            'name': '2025 / 2027', 'code': 'AY-2527',
            'date_start': date(2026, 1, 1), 'date_end': date(2027, 6, 30),
        })
        with self.assertRaises(ValidationError):
            overlapping.action_open()

    def test_non_overlapping_years_can_both_open(self):
        self.year.action_open()
        later = self.env['sl.academic.year'].create({
            'name': '2026 / 2027', 'code': 'AY-2627',
            'date_start': date(2026, 9, 1), 'date_end': date(2027, 6, 30),
        })
        later.action_open()
        self.assertEqual(later.state, 'open')

    # -- numbering ---------------------------------------------------------

    def test_students_and_teachers_get_numbers(self):
        student = self._student('Grace Hopper')
        self.assertTrue(student.code.startswith('STU/'), student.code)
        self.assertTrue(self.teacher.code.startswith('TCH/'), self.teacher.code)

    @mute_logger('odoo.sql_db')
    def test_roll_number_unique_per_class(self):
        self._student('First', roll_number=1)
        try:
            with self.cr.savepoint():
                self._student('Second', roll_number=1)
        except UNIQUE_ERRORS:
            pass
        else:
            self.fail('the duplicate was accepted')

    def test_same_roll_number_allowed_in_another_class(self):
        other = self.env['sl.school.standard'].create({
            'name': 'Grade 6', 'academic_year_id': self.year.id})
        self._student('First', roll_number=1)
        second = self._student('Second', roll_number=1, standard_id=other.id)
        self.assertEqual(second.roll_number, 1)

    # -- student rules -----------------------------------------------------

    def test_age_is_computed_from_birth_date(self):
        born = date.today() - timedelta(days=365 * 12 + 3)
        student = self._student('Alan Turing', birth_date=born)
        self.assertEqual(student.age, 12)

    def test_age_is_zero_without_a_birth_date(self):
        self.assertEqual(self._student('Unknown').age, 0)

    def test_birth_date_cannot_be_in_the_future(self):
        with self.assertRaises(ValidationError):
            self._student('Time Traveller', birth_date=fields.Date.context_today(self.env.user) + timedelta(days=1))

    def test_enrolling_requires_a_class(self):
        student = self.env['sl.student'].create({'name': 'No Class'})
        with self.assertRaises(ValidationError):
            student.action_enrol()

    def test_enrolling_creates_a_contact(self):
        student = self._student('Katherine Johnson', email='kj@example.com')
        self.assertFalse(student.partner_id)
        student.action_enrol()
        self.assertEqual(student.state, 'enrolled')
        self.assertTrue(student.partner_id)
        self.assertEqual(student.partner_id.email, 'kj@example.com')

    def test_class_capacity_is_enforced(self):
        """Capacity is 2; the third enrolment must be refused."""
        for name in ('One', 'Two'):
            self._student(name).action_enrol()
        self.assertEqual(self.standard.student_count, 2)
        self.assertEqual(self.standard.seats_left, 0)
        with self.assertRaises(ValidationError):
            self._student('Three').action_enrol()

    def test_applications_do_not_consume_seats(self):
        for name in ('One', 'Two', 'Three'):
            self._student(name)
        self.assertEqual(self.standard.student_count, 0,
                         "only enrolled students take up a seat")

    def test_capacity_cannot_drop_below_enrolment(self):
        for name in ('One', 'Two'):
            self._student(name).action_enrol()
        with self.assertRaises(ValidationError):
            self.standard.capacity = 1

    def test_zero_capacity_means_no_limit(self):
        self.standard.capacity = 0
        for name in ('One', 'Two', 'Three', 'Four'):
            self._student(name).action_enrol()
        self.assertEqual(self.standard.student_count, 4)

    def test_leaving_frees_a_seat(self):
        first = self._student('One')
        first.action_enrol()
        self._student('Two').action_enrol()
        self.assertEqual(self.standard.seats_left, 0)
        first.action_set_left()
        self.assertEqual(self.standard.seats_left, 1)
        self._student('Three').action_enrol()

    def test_academic_year_follows_the_class(self):
        student = self._student('Follower')
        self.assertEqual(student.academic_year_id, self.year)

    # -- subjects ----------------------------------------------------------

    def test_subject_credits_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self.env['sl.subject'].create({'name': 'Nothing', 'code': 'NIL', 'credits': 0})

    def test_subject_display_name_includes_the_code(self):
        subject = self.env['sl.subject'].create({'name': 'Mathematics', 'code': 'MATH'})
        self.assertEqual(subject.display_name, '[MATH] Mathematics')

    def test_teacher_email_is_checked(self):
        with self.assertRaises(ValidationError):
            self.env['sl.teacher'].create({'name': 'Bad Email', 'email': 'not-an-email'})
