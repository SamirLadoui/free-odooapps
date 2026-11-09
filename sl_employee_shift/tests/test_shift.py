# -*- coding: utf-8 -*-
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date, timedelta
from threading import Barrier
from uuid import uuid4

import psycopg2
from odoo import SUPERUSER_ID, api
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestEmployeeShift(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create({'name': 'Shift Worker'})
        cls.other = cls.env['hr.employee'].create({'name': 'Second Worker'})
        cls.day = cls.env['sl.shift'].create({
            'name': 'Day', 'code': 'DAY', 'start_time': 9.0, 'end_time': 17.0})
        cls.night = cls.env['sl.shift'].create({
            'name': 'Night', 'code': 'NGT', 'start_time': 22.0, 'end_time': 6.0})
        cls.today = date(2026, 5, 1)

    def _assign(self, **values):
        return self.env['sl.shift.assignment'].create(dict({
            'employee_id': self.employee.id, 'shift_id': self.day.id,
            'date_from': self.today}, **values))

    # -- shift length ------------------------------------------------------

    def test_a_normal_shift(self):
        self.assertAlmostEqual(self.day.duration, 8.0, places=4)
        self.assertFalse(self.day.overnight)

    def test_an_overnight_shift_is_not_negative(self):
        """22:00 to 06:00 is eight hours, not minus sixteen. That mistake is
        how a night shift ends up unpaid."""
        self.assertTrue(self.night.overnight)
        self.assertAlmostEqual(self.night.duration, 8.0, places=4)

    def test_break_comes_off_the_paid_hours(self):
        self.day.break_minutes = 30
        self.assertAlmostEqual(self.day.duration, 7.5, places=4)

    def test_break_comes_off_an_overnight_shift_too(self):
        self.night.break_minutes = 45
        self.assertAlmostEqual(self.night.duration, 8.0 - 0.75, places=4)

    def test_half_hour_boundaries(self):
        shift = self.env['sl.shift'].create({
            'name': 'Half', 'start_time': 8.5, 'end_time': 16.25})
        self.assertAlmostEqual(shift.duration, 7.75, places=4)

    # -- shift guards ------------------------------------------------------

    def test_times_must_be_within_the_day(self):
        for start, end in ((25.0, 17.0), (-1.0, 8.0), (9.0, 24.0)):
            with self.assertRaises(ValidationError,
                                   msg='accepted %s-%s' % (start, end)):
                self.env['sl.shift'].create({
                    'name': 'Bad', 'start_time': start, 'end_time': end})

    def test_a_zero_length_shift_is_refused(self):
        with self.assertRaises(ValidationError):
            self.env['sl.shift'].create({
                'name': 'Instant', 'start_time': 9.0, 'end_time': 9.0})

    def test_a_break_longer_than_the_shift_is_refused(self):
        with self.assertRaises(ValidationError):
            self.day.break_minutes = 600

    def test_a_negative_break_is_refused(self):
        with self.assertRaises(ValidationError):
            self.day.break_minutes = -10

    def test_shift_codes_are_unique(self):
        with self.assertRaises(ValidationError):
            self.env['sl.shift'].create({
                'name': 'Duplicate', 'code': 'day',
                'start_time': 1.0, 'end_time': 2.0})

    # -- assignments -------------------------------------------------------

    def test_assigning_a_shift(self):
        assignment = self._assign()
        self.assertEqual(assignment.shift_id, self.day)
        self.employee.invalidate_recordset(['current_shift_id'])

    def test_overlapping_assignments_are_refused(self):
        """Two at once and no report can say which shift somebody was on."""
        self._assign(date_to=self.today + timedelta(days=30))
        with self.assertRaises(ValidationError):
            self._assign(shift_id=self.night.id,
                         date_from=self.today + timedelta(days=10))

    def test_an_archived_assignment_still_blocks_overlapping_history(self):
        archived = self._assign(date_to=self.today + timedelta(days=30))
        archived.active = False
        with self.assertRaises(ValidationError):
            self._assign(shift_id=self.night.id,
                         date_from=self.today + timedelta(days=10))

    def test_an_open_ended_assignment_blocks_later_ones(self):
        self._assign()
        with self.assertRaises(ValidationError):
            self._assign(shift_id=self.night.id,
                         date_from=self.today + timedelta(days=100))

    def test_consecutive_assignments_are_allowed(self):
        self._assign(date_to=self.today + timedelta(days=9))
        later = self._assign(shift_id=self.night.id,
                             date_from=self.today + timedelta(days=10))
        self.assertTrue(later)

    def test_another_employee_may_share_the_period(self):
        self._assign()
        self.assertTrue(self._assign(employee_id=self.other.id))

    def test_an_assignment_ending_before_it_starts_is_refused(self):
        with self.assertRaises(ValidationError):
            self._assign(date_to=self.today - timedelta(days=1))

    def test_concurrent_assignment_create_and_write_serialize(self):
        registry = self.env.registry
        token = uuid4().hex[:10]
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            employee = env['hr.employee'].create({'name': 'Synthetic race %s' % token})
            shift = env['sl.shift'].create({'name': 'Race shift %s' % token, 'start_time': 9, 'end_time': 17})
            assignment_model = env['sl.shift.assignment'].with_context(mail_notrack=True, tracking_disable=True)
            assignment_model.create({
                'employee_id': employee.id, 'shift_id': shift.id,
                'date_from': '2026-05-01', 'date_to': '2026-05-05',
            })
            moving = assignment_model.create({
                'employee_id': employee.id, 'shift_id': shift.id,
                'date_from': '2026-05-11', 'date_to': '2026-05-15',
            })
            employee_id, shift_id, moving_id = employee.id, shift.id, moving.id
            cr.commit()

        create_values = {
            'employee_id': employee_id, 'shift_id': shift_id,
            'date_from': '2026-05-06', 'date_to': '2026-05-10',
        }
        move_values = {'date_from': '2026-05-06', 'date_to': '2026-05-10'}
        barrier = Barrier(2)

        def mutate(operation):
            with registry.cursor() as cr:
                cr.execute('SELECT id FROM hr_employee WHERE id = %s', (employee_id,))
                if not cr.fetchone():
                    return 'missing-employee', None
                cr.execute('SHOW transaction_isolation')
                isolation = cr.fetchone()[0]
                barrier.wait(timeout=30)
                env = api.Environment(cr, SUPERUSER_ID, {})
                try:
                    if operation == 'create':
                        env['sl.shift.assignment'].with_context(
                            mail_notrack=True, tracking_disable=True).create(create_values)
                        outcome = 'created'
                    else:
                        env['sl.shift.assignment'].browse(moving_id).with_context(
                            mail_notrack=True, tracking_disable=True).write(move_values)
                        outcome = 'written'
                    cr.commit()
                    return outcome, isolation
                except psycopg2.errors.SerializationFailure:
                    cr.rollback()
                    return 'serialization', isolation
                except Exception as error:
                    cr.rollback()
                    return 'error:%s:%s' % (type(error).__name__, error), isolation

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = [pool.submit(mutate, operation) for operation in ('create', 'write')]
                results = [future.result(timeout=60) for future in results]
            outcomes = [outcome for outcome, _isolation in results]
            self.assertEqual({isolation for _outcome, isolation in results}, {'repeatable read'})
            self.assertEqual(sum(outcome in ('created', 'written') for outcome in outcomes), 1,
                             'Both independent transactions must not commit conflicting assignments: %r' % outcomes)
            self.assertEqual(outcomes.count('serialization'), 1,
                             'The stale REPEATABLE READ loser must be forced to retry: %r' % outcomes)

            loser = ('write' if outcomes[1] == 'serialization' else 'create')
            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                rejected = False
                try:
                    with closing(cr.savepoint()):
                        if loser == 'create':
                            env['sl.shift.assignment'].create(create_values)
                        else:
                            env['sl.shift.assignment'].browse(moving_id).write(move_values)
                except ValidationError:
                    rejected = True
                finally:
                    cr.rollback()
            self.assertTrue(rejected, 'A fresh-snapshot retry must see and reject the committed overlap')
        finally:
            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                env['sl.shift.assignment'].with_context(active_test=False).search([
                    ('employee_id', '=', employee_id),
                ]).unlink()
                env['sl.shift'].browse(shift_id).unlink()
                env['hr.employee'].browse(employee_id).unlink()
                cr.commit()

    # -- the employee's current shift --------------------------------------

    def test_current_shift_when_in_range(self):
        today = date.today()
        self._assign(date_from=today - timedelta(days=1),
                     date_to=today + timedelta(days=1))
        self.employee.invalidate_recordset(['current_shift_id'])
        self.assertEqual(self.employee.current_shift_id, self.day)

    def test_no_current_shift_before_it_starts(self):
        today = date.today()
        self._assign(date_from=today + timedelta(days=5))
        self.employee.invalidate_recordset(['current_shift_id'])
        self.assertFalse(self.employee.current_shift_id)

    def test_no_current_shift_after_it_ends(self):
        today = date.today()
        self._assign(date_from=today - timedelta(days=10),
                     date_to=today - timedelta(days=1))
        self.employee.invalidate_recordset(['current_shift_id'])
        self.assertFalse(self.employee.current_shift_id)

    def test_an_open_ended_assignment_is_current(self):
        self._assign(date_from=date.today() - timedelta(days=1))
        self.employee.invalidate_recordset(['current_shift_id'])
        self.assertEqual(self.employee.current_shift_id, self.day)
