# -*- coding: utf-8 -*-
"""Independent-transaction regressions for core roster serialization."""
from concurrent.futures import ThreadPoolExecutor
import threading

from odoo import SUPERUSER_ID, api, tools
from odoo.modules.registry import Registry
from odoo.tests import BaseCase, tagged


@tagged('post_install', '-at_install')
class TestAssignmentOverlapConcurrency(BaseCase):
    """Use committed fixtures and independent REPEATABLE READ transactions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.registry = Registry(tools.config['db_name'])

    def _open_environment(self, cr):
        cr.transaction = api.Transaction(self.registry)
        env = api.Environment(cr, SUPERUSER_ID, {})
        cr.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        cr.execute("SET LOCAL lock_timeout = '4s'")
        cr.execute("SET LOCAL statement_timeout = '12s'")
        return env

    def _seed_create_race(self):
        with self.registry.cursor() as cr:
            env = self._open_environment(cr)
            employee = env['hr.employee'].create({'name': 'Synthetic create-race employee'})
            shift = env['sl.shift'].create({
                'name': 'Synthetic create-race shift', 'start_time': 9, 'end_time': 17,
            })
            cr.commit()
        fixture = {'employee_id': employee.id, 'shift_id': shift.id}
        self.addCleanup(self._cleanup_fixture, [employee.id], [shift.id])
        return fixture

    def _cleanup_fixture(self, employee_ids, shift_ids):
        with self.registry.cursor() as cr:
            env = self._open_environment(cr)
            assignments = env['sl.shift.assignment'].with_context(active_test=False).search([
                ('employee_id', 'in', employee_ids),
            ])
            assignments.unlink()
            env['hr.employee'].browse(employee_ids).unlink()
            env['sl.shift'].browse(shift_ids).unlink()
            cr.commit()

    def _create_in_independent_transaction(self, fixture, barrier, snapshots, snapshots_lock):
        with self.registry.cursor() as cr:
            try:
                env = self._open_environment(cr)
                cr.execute('SHOW transaction_isolation')
                isolation = cr.fetchone()[0]
                cr.execute('SELECT txid_current_snapshot()')
                snapshot = cr.fetchone()[0]
                cr.execute('SELECT id FROM sl_shift_assignment WHERE employee_id = %s',
                           (fixture['employee_id'],))
                visible_assignments = cr.fetchall()
                with snapshots_lock:
                    snapshots.append((isolation, snapshot, visible_assignments))
                barrier.wait(timeout=5)
                env['sl.shift.assignment'].create({
                    'employee_id': fixture['employee_id'],
                    'shift_id': fixture['shift_id'],
                    'date_from': '2026-11-01',
                    'date_to': '2026-11-30',
                })
                cr.commit()
                return {'status': 'committed', 'sqlstate': None}
            except Exception as exc:
                return {
                    'status': 'serialization_failure' if getattr(exc, 'pgcode', None) == '40001' else 'error',
                    'sqlstate': getattr(exc, 'pgcode', None),
                    'error': '%s: %s' % (type(exc).__name__, exc),
                }

    def _fresh_create_retry(self, fixture):
        with self.registry.cursor() as cr:
            env = self._open_environment(cr)
            try:
                env['sl.shift.assignment'].create({
                    'employee_id': fixture['employee_id'],
                    'shift_id': fixture['shift_id'],
                    'date_from': '2026-11-02',
                    'date_to': '2026-11-20',
                })
            except Exception as exc:
                rejected = type(exc).__name__ == 'ValidationError'
            else:
                rejected = False
            overlap_count = env['sl.shift.assignment'].with_context(active_test=False).search_count([
                ('employee_id', '=', fixture['employee_id']),
            ])
            return rejected, overlap_count

    def test_concurrent_overlapping_creates_serialize_and_fresh_retry_rejects(self):
        fixture = self._seed_create_race()
        barrier = threading.Barrier(2, timeout=5)
        snapshots = []
        snapshots_lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix='slshift-create-race') as pool:
            futures = [pool.submit(self._create_in_independent_transaction,
                                   fixture, barrier, snapshots, snapshots_lock)
                       for _ in range(2)]
            outcomes = [future.result(timeout=20) for future in futures]

        retry_rejected, overlap_count = self._fresh_create_retry(fixture)
        self.assertEqual(
            sorted(result['status'] for result in outcomes),
            ['committed', 'serialization_failure'],
            'Expected one committed create and one PostgreSQL serialization failure; got %r' % outcomes,
        )
        self.assertEqual([row[0] for row in snapshots], ['repeatable read', 'repeatable read'])
        self.assertTrue(all(not row[2] for row in snapshots),
                        'Both transactions must snapshot the same empty assignment set')
        self.assertTrue(retry_rejected, 'A fresh transaction must reject the now-overlapping retry')
        self.assertEqual(overlap_count, 1, 'Exactly one overlapping assignment may persist')

    def _seed_write_race(self):
        with self.registry.cursor() as cr:
            env = self._open_environment(cr)
            target = env['hr.employee'].create({'name': 'Synthetic write-race target'})
            first = env['hr.employee'].create({'name': 'Synthetic write-race source one'})
            second = env['hr.employee'].create({'name': 'Synthetic write-race source two'})
            retry_employee = env['hr.employee'].create({'name': 'Synthetic write-race retry source'})
            shift = env['sl.shift'].create({
                'name': 'Synthetic write-race shift', 'start_time': 9, 'end_time': 17,
            })
            assignments = env['sl.shift.assignment'].create([
                {'employee_id': first.id, 'shift_id': shift.id,
                 'date_from': '2026-11-01', 'date_to': '2026-11-30'},
                {'employee_id': second.id, 'shift_id': shift.id,
                 'date_from': '2026-11-01', 'date_to': '2026-11-30'},
                {'employee_id': retry_employee.id, 'shift_id': shift.id,
                 'date_from': '2026-11-01', 'date_to': '2026-11-30'},
            ])
            cr.commit()
        fixture = {
            'employee_id': target.id,
            'shift_id': shift.id,
            'assignment_ids': assignments[:2].ids,
            'retry_assignment_id': assignments[2].id,
        }
        self.addCleanup(self._cleanup_fixture,
                        [target.id, first.id, second.id, retry_employee.id], [shift.id])
        return fixture

    def _write_in_independent_transaction(self, fixture, assignment_id, barrier,
                                          snapshots, snapshots_lock):
        with self.registry.cursor() as cr:
            try:
                env = self._open_environment(cr)
                cr.execute('SHOW transaction_isolation')
                isolation = cr.fetchone()[0]
                cr.execute('SELECT txid_current_snapshot()')
                snapshot = cr.fetchone()[0]
                cr.execute('SELECT employee_id FROM sl_shift_assignment WHERE id = %s',
                           (assignment_id,))
                source_employee = cr.fetchone()[0]
                cr.execute('SELECT id FROM sl_shift_assignment WHERE employee_id = %s',
                           (fixture['employee_id'],))
                target_assignments = cr.fetchall()
                with snapshots_lock:
                    snapshots.append((isolation, snapshot, source_employee, target_assignments))
                barrier.wait(timeout=5)
                env['sl.shift.assignment'].browse(assignment_id).write({
                    'employee_id': fixture['employee_id'],
                })
                cr.commit()
                return {'status': 'committed', 'sqlstate': None}
            except Exception as exc:
                return {
                    'status': 'serialization_failure' if getattr(exc, 'pgcode', None) == '40001' else 'error',
                    'sqlstate': getattr(exc, 'pgcode', None),
                    'error': '%s: %s' % (type(exc).__name__, exc),
                }

    def _fresh_write_retry(self, fixture):
        with self.registry.cursor() as cr:
            env = self._open_environment(cr)
            assignments = env['sl.shift.assignment'].with_context(active_test=False)
            retry = assignments.browse(fixture['retry_assignment_id'])
            try:
                retry.write({'employee_id': fixture['employee_id']})
            except Exception as exc:
                rejected = type(exc).__name__ == 'ValidationError'
            else:
                rejected = False
            overlap_count = assignments.search_count([('employee_id', '=', fixture['employee_id'])])
            return rejected, overlap_count

    def test_concurrent_overlapping_writes_serialize_and_fresh_retry_rejects(self):
        fixture = self._seed_write_race()
        barrier = threading.Barrier(2, timeout=5)
        snapshots = []
        snapshots_lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix='slshift-write-race') as pool:
            futures = [pool.submit(self._write_in_independent_transaction,
                                   fixture, assignment_id, barrier, snapshots, snapshots_lock)
                       for assignment_id in fixture['assignment_ids']]
            outcomes = [future.result(timeout=20) for future in futures]

        retry_rejected, overlap_count = self._fresh_write_retry(fixture)
        self.assertEqual(
            sorted(result['status'] for result in outcomes),
            ['committed', 'serialization_failure'],
            'Expected one committed write and one PostgreSQL serialization failure; got %r' % outcomes,
        )
        self.assertEqual([row[0] for row in snapshots], ['repeatable read', 'repeatable read'])
        self.assertTrue(all(not row[3] for row in snapshots),
                        'Both transactions must snapshot an empty target assignment set')
        self.assertTrue(retry_rejected, 'A fresh transaction must reject the now-overlapping reparent')
        self.assertEqual(overlap_count, 1, 'Exactly one assignment may move to the target employee')
