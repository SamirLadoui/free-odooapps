# SPDX-License-Identifier: LGPL-3.0-or-later
from concurrent.futures import ThreadPoolExecutor
import threading
import uuid

import odoo
from odoo import SUPERUSER_ID, api
from odoo.exceptions import ValidationError
from odoo.tests import BaseCase, tagged
from odoo.tests.common import get_db_name


@tagged('post_install', '-at_install')
class TestAssignmentConcurrency(BaseCase):
    """Exercise assignment overlap with independent PostgreSQL transactions."""

    def setUp(self):
        super().setUp()
        self.registry = odoo.registry(get_db_name())
        self.addCleanup(self.registry.reset_changes)
        self.addCleanup(self.registry.clear_caches)

    @staticmethod
    def _set_timeouts(cr):
        cr.execute("SET LOCAL lock_timeout = '5s'")
        cr.execute("SET LOCAL statement_timeout = '20s'")

    def _fixture(self, mode):
        token = uuid.uuid4().hex[:10]
        fixture = {}
        with api.Environment.manage():
            with self.registry.cursor() as cr:
                self._set_timeouts(cr)
                env = api.Environment(cr, SUPERUSER_ID, {})
                employee = env['hr.employee'].create({
                    'name': 'Synthetic core-only concurrency ' + token,
                })
                shift = env['sl.shift'].create({
                    'name': 'Synthetic core-only concurrency ' + token,
                    'start_time': 9, 'end_time': 17,
                })
                fixture.update(employee_id=employee.id, shift_id=shift.id, token=token)
                if mode == 'write':
                    first = env['sl.shift.assignment'].create({
                        'employee_id': employee.id, 'shift_id': shift.id,
                        'date_from': '2026-10-01', 'date_to': '2026-10-05',
                    })
                    second = env['sl.shift.assignment'].create({
                        'employee_id': employee.id, 'shift_id': shift.id,
                        'date_from': '2026-10-10', 'date_to': '2026-10-15',
                    })
                    fixture['assignment_ids'] = [first.id, second.id]
                cr.commit()
        return fixture

    def _compete(self, mode, fixture):
        barrier = threading.Barrier(2)
        target_from, target_to = '2026-11-11', '2026-11-20'

        def worker(participant):
            outcome = {'participant': participant}
            try:
                with api.Environment.manage():
                    with self.registry.cursor() as cr:
                        self._set_timeouts(cr)
                        env = api.Environment(cr, SUPERUSER_ID, {})
                        cr.execute('SHOW transaction_isolation')
                        outcome['isolation'] = cr.fetchone()[0]
                        domain = [
                            ('employee_id', '=', fixture['employee_id']),
                            ('date_from', '<=', target_to),
                            '|', ('date_to', '=', False),
                                 ('date_to', '>=', target_from),
                        ]
                        outcome['initial_matches'] = env['sl.shift.assignment'].with_context(
                            active_test=False).search_count(domain)
                        # The ORM query above establishes this transaction's
                        # REPEATABLE READ snapshot before either writer proceeds.
                        outcome['snapshot_before_barrier'] = True
                        barrier.wait(timeout=10)
                        if mode == 'create':
                            assignment = env['sl.shift.assignment'].create({
                                'employee_id': fixture['employee_id'],
                                'shift_id': fixture['shift_id'],
                                'date_from': target_from, 'date_to': target_to,
                            })
                        else:
                            assignment_id = fixture['assignment_ids'][participant]
                            assignment = env['sl.shift.assignment'].browse(assignment_id)
                            assignment.write({'date_from': target_from, 'date_to': target_to})
                        cr.commit()
                        outcome.update(status='winner', assignment_id=assignment.id)
            except Exception as error:
                if getattr(error, 'pgcode', None) != '40001':
                    raise
                outcome.update(status='serialization_conflict', sqlstate=error.pgcode,
                               error_type=type(error).__name__)
            return outcome

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker, index) for index in range(2)]
            outcomes = [future.result(timeout=35) for future in futures]
        return outcomes

    def _retry_is_rejected(self, mode, fixture):
        with api.Environment.manage():
            with self.registry.cursor() as cr:
                self._set_timeouts(cr)
                env = api.Environment(cr, SUPERUSER_ID, {})
                try:
                    if mode == 'create':
                        env['sl.shift.assignment'].create({
                            'employee_id': fixture['employee_id'],
                            'shift_id': fixture['shift_id'],
                            'date_from': '2026-11-11', 'date_to': '2026-11-20',
                        })
                    else:
                        outcomes = env['sl.shift.assignment'].with_context(active_test=False).search([
                            ('employee_id', '=', fixture['employee_id']),
                            ('date_from', '=', '2026-11-11'),
                            ('date_to', '=', '2026-11-20'),
                        ])
                        winner_ids = set(outcomes.ids)
                        remaining_ids = set(fixture['assignment_ids']) - winner_ids
                        loser_id = next(iter(remaining_ids or fixture['assignment_ids']))
                        env['sl.shift.assignment'].browse(loser_id).write({
                            'date_from': '2026-11-11', 'date_to': '2026-11-20',
                        })
                except ValidationError as error:
                    cr.rollback()
                    return 'overlapping' in str(error).lower()
                cr.rollback()
                return False

    def _target_rows(self, fixture):
        with api.Environment.manage():
            with self.registry.cursor() as cr:
                self._set_timeouts(cr)
                env = api.Environment(cr, SUPERUSER_ID, {})
                rows = env['sl.shift.assignment'].with_context(active_test=False).search([
                    ('employee_id', '=', fixture['employee_id']),
                    ('date_from', '=', '2026-11-11'),
                    ('date_to', '=', '2026-11-20'),
                ])
                return rows.ids

    def _cleanup(self, fixture):
        with api.Environment.manage():
            with self.registry.cursor() as cr:
                self._set_timeouts(cr)
                env = api.Environment(cr, SUPERUSER_ID, {})
                env['sl.shift.assignment'].with_context(active_test=False).search([
                    ('employee_id', '=', fixture['employee_id']),
                ]).unlink()
                env['hr.employee'].browse(fixture['employee_id']).unlink()
                env['sl.shift'].browse(fixture['shift_id']).unlink()
                cr.commit()

    def test_concurrent_overlapping_assignment_create_and_write_serialize(self):
        results = {}
        fixtures = {}
        try:
            for mode in ('create', 'write'):
                fixture = fixtures[mode] = self._fixture(mode)
                results[mode] = self._compete(mode, fixture)
                results[mode + '_retry_rejected'] = self._retry_is_rejected(mode, fixture)
                results[mode + '_target_ids'] = self._target_rows(fixture)

            for mode in ('create', 'write'):
                outcomes = results[mode]
                with self.subTest(operation=mode):
                    self.assertTrue(all(item['isolation'] == 'repeatable read' for item in outcomes), outcomes)
                    self.assertTrue(all(item['initial_matches'] == 0 for item in outcomes), outcomes)
                    self.assertTrue(all(item['snapshot_before_barrier'] for item in outcomes), outcomes)
                    self.assertEqual([item['status'] for item in outcomes].count('winner'), 1, outcomes)
                    conflicts = [item for item in outcomes if item['status'] == 'serialization_conflict']
                    self.assertEqual(len(conflicts), 1, outcomes)
                    self.assertEqual(conflicts[0]['sqlstate'], '40001', outcomes)
                    self.assertTrue(results[mode + '_retry_rejected'], results)
                    self.assertEqual(len(results[mode + '_target_ids']), 1, results)
        finally:
            for fixture in fixtures.values():
                self._cleanup(fixture)
