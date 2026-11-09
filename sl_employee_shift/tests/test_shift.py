# -*- coding: utf-8 -*-
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier
import uuid

import psycopg2
from odoo import SUPERUSER_ID, api
from odoo.exceptions import ValidationError
from odoo.orm.environments import Transaction
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

    def test_archived_assignments_still_block_overlapping_create_and_write(self):
        historical = self._assign(date_to=self.today + timedelta(days=30))
        historical.active = False

        with self.assertRaises(ValidationError):
            self._assign(shift_id=self.night.id,
                         date_from=self.today + timedelta(days=10))

        candidate = self._assign(shift_id=self.night.id,
                                 date_from=self.today + timedelta(days=31),
                                 date_to=self.today + timedelta(days=40))
        with self.assertRaises(ValidationError):
            candidate.write({'date_from': self.today + timedelta(days=20)})

    def test_concurrent_assignment_create_and_write_are_serialized(self):
        """Independent repeatable-read writers cannot commit an overlap."""
        registry = self.env.registry
        company_id = self.env.company.id
        token = uuid.uuid4().hex[:10]
        employee_id = None
        shift_ids = []
        created_overlap_count = None
        write_overlap = None
        race_results = []

        # A previously interrupted native run may have committed only this
        # test's independent bootstrap records. Remove those exact named rows.
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {'allowed_company_ids': [company_id]})
            stale_employees = env['hr.employee'].search([
                ('name', 'like', 'Concurrent assignment employee %'),
            ])
            for stale_employee in stale_employees:
                stale_token = stale_employee.name.rsplit(' ', 1)[-1]
                if len(stale_token) == 10 and all(char in '0123456789abcdef' for char in stale_token):
                    env['sl.shift.assignment'].with_context(active_test=False).search([
                        ('employee_id', '=', stale_employee.id),
                    ]).unlink()
                    env['sl.shift'].search([
                        ('name', 'in', [
                            'Concurrent assignment shift A ' + stale_token,
                            'Concurrent assignment shift B ' + stale_token,
                        ]),
                    ]).unlink()
                    stale_employee.unlink()
            cr.commit()

        try:
            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {'allowed_company_ids': [company_id]})
                employee = env['hr.employee'].create({
                    'name': 'Concurrent assignment employee ' + token,
                    'date_version': '2026-01-01',
                })
                shifts = env['sl.shift'].create([
                    {'name': 'Concurrent assignment shift A ' + token, 'start_time': 8, 'end_time': 16},
                    {'name': 'Concurrent assignment shift B ' + token, 'start_time': 9, 'end_time': 17},
                ])
                employee_id = employee.id
                shift_ids = shifts.ids
                cr.commit()

            def race_pair(specs, initial_count, operation):
                barrier = Barrier(2)

                def participant(spec):
                    with registry.cursor() as cr:
                        # Environment.__new__ normally calls Registry(dbname),
                        # which takes the main test thread's registry lock.
                        # The real independent transaction already knows the
                        # loaded registry, so bind it directly in each worker.
                        cr.transaction = Transaction(registry)
                        env = api.Environment(cr, SUPERUSER_ID, {'allowed_company_ids': [company_id]})
                        cr.execute('SHOW transaction_isolation')
                        isolation = cr.fetchone()[0]
                        cr.execute('SELECT count(*) FROM sl_shift_assignment WHERE employee_id = %s', (employee_id,))
                        observed_count = cr.fetchone()[0]
                        if observed_count != initial_count:
                            raise AssertionError('Race participant saw %s assignments before synchronization' % observed_count)
                        barrier.wait(timeout=20)
                        try:
                            operation(env, spec)
                            cr.commit()
                            return ('committed', isolation, None, spec)
                        except (ValidationError, psycopg2.errors.SerializationFailure) as error:
                            cr.rollback()
                            return ('rejected', isolation, type(error).__name__, spec)

                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(participant, spec) for spec in specs]
                    return [future.result(timeout=45) for future in futures]

            def assert_fresh_retry_rejects(spec, operation):
                with registry.cursor() as cr:
                    cr.transaction = Transaction(registry)
                    env = api.Environment(cr, SUPERUSER_ID, {'allowed_company_ids': [company_id]})
                    with self.assertRaises(ValidationError):
                        operation(env, spec)
                    cr.rollback()

            create_specs = [
                {'shift_id': shift_ids[0], 'date_from': '2026-11-20', 'date_to': '2026-11-25'},
                {'shift_id': shift_ids[1], 'date_from': '2026-11-20', 'date_to': '2026-11-25'},
            ]
            create_results = race_pair(
                create_specs, 0,
                lambda env, spec: env['sl.shift.assignment'].create(dict(spec, employee_id=employee_id)),
            )
            self.assertEqual({result[1] for result in create_results}, {'repeatable read'})
            rejected_create = [result for result in create_results if result[0] == 'rejected']
            self.assertEqual([result[2] for result in rejected_create], ['SerializationFailure'])
            assert_fresh_retry_rejects(
                rejected_create[0][3],
                lambda env, spec: env['sl.shift.assignment'].create(dict(spec, employee_id=employee_id)),
            )
            race_results.append(create_results)

            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {'allowed_company_ids': [company_id]})
                env['sl.shift.assignment'].with_context(active_test=False).search([
                    ('employee_id', '=', employee_id),
                ]).unlink()
                initial = env['sl.shift.assignment'].create([
                    {'employee_id': employee_id, 'shift_id': shift_ids[0],
                     'date_from': '2026-11-01', 'date_to': '2026-11-04'},
                    {'employee_id': employee_id, 'shift_id': shift_ids[1],
                     'date_from': '2026-11-07', 'date_to': '2026-11-10'},
                ])
                initial_ids = initial.ids
                cr.commit()

            write_specs = [
                (initial_ids[0], {'date_to': '2026-11-06'}),
                (initial_ids[1], {'date_from': '2026-11-05'}),
            ]
            write_results = race_pair(
                write_specs, 2,
                lambda env, spec: env['sl.shift.assignment'].browse(spec[0]).write(spec[1]),
            )
            self.assertEqual({result[1] for result in write_results}, {'repeatable read'})
            rejected_write = [result for result in write_results if result[0] == 'rejected']
            self.assertEqual([result[2] for result in rejected_write], ['SerializationFailure'])
            assert_fresh_retry_rejects(
                rejected_write[0][3],
                lambda env, spec: env['sl.shift.assignment'].browse(spec[0]).write(spec[1]),
            )
            race_results.append(write_results)

            with registry.cursor() as cr:
                cr.execute('SELECT count(*) FROM sl_shift_assignment WHERE employee_id = %s', (employee_id,))
                created_overlap_count = cr.fetchone()[0]
                env = api.Environment(cr, SUPERUSER_ID, {'allowed_company_ids': [company_id]})
                assignments = env['sl.shift.assignment'].with_context(active_test=False).search([
                    ('employee_id', '=', employee_id),
                ])
                periods = [(a.date_from, a.date_to or date.max) for a in assignments]
                write_overlap = any(
                    left_start <= right_end and right_start <= left_end
                    for index, (left_start, left_end) in enumerate(periods)
                    for right_start, right_end in periods[index + 1:]
                )

            for results in race_results:
                self.assertEqual(sorted(result[0] for result in results), ['committed', 'rejected'])
            self.assertEqual(created_overlap_count, 2, 'One create winner plus the two later write-race controls')
            self.assertFalse(write_overlap, 'Concurrent writes committed overlapping assignment periods')
        finally:
            if employee_id:
                with registry.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {'allowed_company_ids': [company_id]})
                    env['sl.shift.assignment'].with_context(active_test=False).search([
                        ('employee_id', '=', employee_id),
                    ]).unlink()
                    env['sl.shift'].browse(shift_ids).unlink()
                    env['hr.employee'].browse(employee_id).unlink()
                    cr.commit()

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
