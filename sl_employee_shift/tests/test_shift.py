# -*- coding: utf-8 -*-
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier

from psycopg2.errors import SerializationFailure

from odoo import SUPERUSER_ID, api
from odoo.exceptions import ValidationError
from odoo.modules.registry import Registry
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import BaseCase, get_db_name


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

    def test_archived_assignment_still_blocks_an_overlapping_assignment(self):
        archived = self._assign(date_to=self.today + timedelta(days=30))
        archived.active = False

        with self.assertRaises(ValidationError):
            self._assign(shift_id=self.night.id,
                         date_from=self.today + timedelta(days=10))

        later = self._assign(shift_id=self.night.id,
                             date_from=self.today + timedelta(days=31))
        self.assertTrue(later)

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


@tagged('post_install', '-at_install')
class TestConcurrentShiftAssignment(BaseCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.registry = Registry(get_db_name())

    def test_concurrent_assignment_creation_serializes_overlapping_periods(self):
        registry = self.registry
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            employee = env['hr.employee'].search([], order='id', limit=1)
            self.assertTrue(employee, 'The disposable Odoo database must have its native employee fixture')
            shift = env['sl.shift'].with_context(
                mail_create_nolog=True, mail_notrack=True, mail_create_nosubscribe=True,
            ).create({'name': 'Synthetic concurrent shift', 'start_time': 9, 'end_time': 17})
            employee_id, shift_id = employee.id, shift.id
            cr.commit()

        barrier = Barrier(2)

        def create_assignment():
            with registry.cursor() as cr:
                # These workers share the already-loaded registry but own
                # independent PostgreSQL transactions; avoid a second global
                # Registry lookup while the native test runner is active.
                cr.transaction = api.Transaction(registry)
                env = api.Environment(cr, SUPERUSER_ID, {})
                cr.execute("SET LOCAL lock_timeout = '10s'")
                cr.execute("SET LOCAL statement_timeout = '20s'")
                cr.execute('SHOW transaction_isolation')
                isolation = cr.fetchone()[0]
                env['hr.employee'].browse(employee_id).read(['name'])
                barrier.wait(timeout=5)
                try:
                    assignment = env['sl.shift.assignment'].with_context(
                        mail_create_nolog=True, mail_notrack=True, mail_create_nosubscribe=True,
                    ).create({
                        'employee_id': employee_id, 'shift_id': shift_id,
                        'date_from': '2026-11-01', 'date_to': '2026-11-30',
                    })
                    cr.commit()
                    return ('created', assignment.id, isolation)
                except SerializationFailure:
                    cr.rollback()
                    return ('serialization', False, isolation)
                except Exception as error:
                    cr.rollback()
                    return ('error', '%s: %s' % (type(error).__name__, error), isolation)

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(lambda _index: create_assignment(), range(2)))

            kinds = [outcome[0] for outcome in outcomes]
            self.assertEqual({outcome[2] for outcome in outcomes}, {'repeatable read'})
            self.assertEqual(kinds.count('created'), 1, outcomes)
            self.assertEqual(kinds.count('serialization'), 1, outcomes)

            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                try:
                    env['sl.shift.assignment'].with_context(
                        mail_create_nolog=True, mail_notrack=True, mail_create_nosubscribe=True,
                    ).create({
                        'employee_id': employee_id, 'shift_id': shift_id,
                        'date_from': '2026-11-01', 'date_to': '2026-11-30',
                    })
                except ValidationError:
                    cr.rollback()
                else:
                    cr.rollback()
                    self.fail('A fresh retry accepted an overlapping assignment')
        finally:
            with registry.cursor() as cr:
                cr.execute('DELETE FROM sl_shift_assignment WHERE employee_id = %s AND shift_id = %s',
                           (employee_id, shift_id))
                cr.execute('DELETE FROM sl_shift WHERE id = %s', (shift_id,))
                cr.commit()

    def test_concurrent_assignment_write_serializes_overlapping_periods(self):
        registry = self.registry
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            employee = env['hr.employee'].search([], order='id', limit=1)
            self.assertTrue(employee, 'The disposable Odoo database must have its native employee fixture')
            shift = env['sl.shift'].with_context(
                mail_create_nolog=True, mail_notrack=True, mail_create_nosubscribe=True,
            ).create({'name': 'Synthetic concurrent write shift', 'start_time': 9, 'end_time': 17})
            assignments = env['sl.shift.assignment'].with_context(
                mail_create_nolog=True, mail_notrack=True, mail_create_nosubscribe=True,
            ).create([
                {'employee_id': employee.id, 'shift_id': shift.id,
                 'date_from': '2026-11-01', 'date_to': '2026-11-04'},
                {'employee_id': employee.id, 'shift_id': shift.id,
                 'date_from': '2026-11-05', 'date_to': '2026-11-09'},
            ])
            employee_id, shift_id = employee.id, shift.id
            first_id, second_id = assignments.ids
            cr.commit()

        proposed = {
            first_id: {'date_from': '2026-11-10', 'date_to': '2026-11-12'},
            second_id: {'date_from': '2026-11-06', 'date_to': '2026-11-11'},
        }
        barrier = Barrier(2)

        def write_assignment(assignment_id):
            with registry.cursor() as cr:
                cr.transaction = api.Transaction(registry)
                env = api.Environment(cr, SUPERUSER_ID, {})
                cr.execute("SET LOCAL lock_timeout = '10s'")
                cr.execute("SET LOCAL statement_timeout = '20s'")
                cr.execute('SHOW transaction_isolation')
                isolation = cr.fetchone()[0]
                env['sl.shift.assignment'].browse([first_id, second_id]).read(['date_from', 'date_to'])
                barrier.wait(timeout=5)
                try:
                    env['sl.shift.assignment'].browse(assignment_id).with_context(
                        mail_notrack=True,
                    ).write(proposed[assignment_id])
                    cr.commit()
                    return ('written', assignment_id, isolation)
                except SerializationFailure:
                    cr.rollback()
                    return ('serialization', assignment_id, isolation)
                except ValidationError:
                    cr.rollback()
                    return ('overlap', assignment_id, isolation)
                except Exception as error:
                    cr.rollback()
                    return ('error', '%s: %s' % (type(error).__name__, error), isolation)

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(write_assignment, (first_id, second_id)))

            kinds = [outcome[0] for outcome in outcomes]
            self.assertEqual({outcome[2] for outcome in outcomes}, {'repeatable read'})
            self.assertEqual(kinds.count('written'), 1, outcomes)
            self.assertEqual(kinds.count('serialization'), 1, outcomes)
            loser_id = next(outcome[1] for outcome in outcomes if outcome[0] == 'serialization')

            with registry.cursor() as cr:
                cr.transaction = api.Transaction(registry)
                env = api.Environment(cr, SUPERUSER_ID, {})
                try:
                    env['sl.shift.assignment'].browse(loser_id).with_context(
                        mail_notrack=True,
                    ).write(proposed[loser_id])
                except ValidationError:
                    cr.rollback()
                else:
                    cr.rollback()
                    self.fail('A fresh retry accepted an overlapping assignment write')
        finally:
            with registry.cursor() as cr:
                cr.execute('DELETE FROM sl_shift_assignment WHERE employee_id = %s AND shift_id = %s',
                           (employee_id, shift_id))
                cr.execute('DELETE FROM sl_shift WHERE id = %s', (shift_id,))
                cr.commit()
