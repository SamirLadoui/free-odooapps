# SPDX-License-Identifier: LGPL-3.0-or-later
import threading
from datetime import datetime, timedelta

from odoo import SUPERUSER_ID, api
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestShiftIntegration(TransactionCase):
    def setUp(self):
        super().setUp()
        self.employee = self.env['hr.employee'].create({'name': 'Synthetic Shift Integration'})
        self.shift = self.env['sl.shift'].create({'name': 'Synthetic 18-03', 'start_time': 18, 'end_time': 3, 'break_minutes': 60})
        self.assignment = self.env['sl.shift.assignment'].create({
            'employee_id': self.employee.id, 'shift_id': self.shift.id,
            'date_from': '2026-11-01', 'date_to': '2026-11-30', 'attendance_policy': 'shift',
            'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6', 'break_window_set': True, 'break_start': 22,
        })
        self.approver = new_test_user(self.env['res.users'].with_context(no_reset_password=True).env, email='synthetic-shift@example.invalid', login='slshift-approver',
                                    groups='base.group_user,hr.group_hr_user,sl_employee_shift_attendance.group_shift_approver')
        self.officer = new_test_user(self.env['res.users'].with_context(no_reset_password=True).env, email='synthetic-shift@example.invalid', login='slshift-officer',
                                   groups='base.group_user,hr.group_hr_user,hr_attendance.group_hr_attendance_user')
        self.admin = new_test_user(self.env['res.users'].with_context(no_reset_password=True).env, email='synthetic-shift@example.invalid', login='slshift-config-admin',
                                 groups='base.group_user,hr.group_hr_manager,hr_attendance.group_hr_attendance_manager,sl_employee_shift_attendance.group_shift_approver')
        # Native14 assertRaises clears pending recomputes, not a savepoint.
        # Persist stored related company before exercising expected denials.
        self.assignment.flush()

    def _punch(self, start='2026-11-02 18:00:00', stop='2026-11-03 05:00:00', **values):
        return self.env['hr.attendance'].create(dict(employee_id=self.employee.id, check_in=start, check_out=stop, **values))

    def test_summary_regular_raw_approved_presence_and_native_exclusion(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        self.assertTrue(day)
        self.assertEqual((day.elapsed_hours, day.net_hours, day.regular_hours, day.raw_overtime_hours,
                          day.approved_overtime_hours, day.presence_days), (11, 10, 8, 2, 0, 1))
        self.assertNotIn('hr.attendance.overtime', self.env.registry)
        self.assertNotIn('overtime_hours', attendance._fields)
        self.assertEqual(attendance.sl_regular_hours, 8)

    def test_guarded_decision_wizard_works_for_restricted_approver(self):
        from odoo.tests import Form
        day = self._punch().sl_shift_day_id.with_user(self.approver)
        action = day.action_open_decision()
        self.assertEqual(action['res_model'], 'sl.shift.decision')
        with Form(self.env['sl.shift.decision'].with_user(self.approver).with_context(action['context'])) as form:
            form.hours = 1
            form.reason = 'Restricted-user Form approval'
        wizard = form.save()
        wizard.action_confirm()
        self.assertEqual(day.approved_overtime_hours, 1)
        self.assertEqual(day.approver_id, self.approver)
        with self.assertRaises(AccessError):
            day.with_user(self.officer).action_open_decision()

    def test_restricted_approver_can_approve_without_attendance_mutation_rights(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        other_employee = self.env['hr.employee'].create({'name': 'Synthetic unrelated attendance owner'})
        native = self.env['hr.attendance'].create({
            'employee_id': other_employee.id, 'check_in': '2026-11-04 09:00:00',
            'check_out': '2026-11-04 10:00:00',
        })
        restricted = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-shift@example.invalid', login='slshift-restricted-approver',
            groups='base.group_user,sl_employee_shift_attendance.group_shift_approver',
        )
        actor_day = day.with_user(restricted).with_context(allowed_company_ids=[self.env.company.id])
        actor_day.action_approve(1, 'Restricted approval without attendance officer rights')
        self.assertEqual(actor_day.approved_overtime_hours, 1)
        self.assertTrue(actor_day.audit_ids.read(['event']))
        self.assertFalse(restricted.has_group('hr_attendance.group_hr_attendance_user'))
        with self.assertRaises(AccessError):
            self.env['hr.attendance'].with_user(restricted).with_context(
                allowed_company_ids=[self.env.company.id]).create({
                    'employee_id': other_employee.id, 'check_in': '2026-11-05 09:00:00',
                    'check_out': '2026-11-05 10:00:00',
                })
        with self.assertRaises(AccessError):
            native.with_user(restricted).with_context(allowed_company_ids=[self.env.company.id]).write(
                {'check_out': '2026-11-04 11:00:00'})
        with self.assertRaises(AccessError):
            native.with_user(restricted).with_context(allowed_company_ids=[self.env.company.id]).unlink()

    def test_shift_approver_reads_managed_but_not_unrelated_same_company_attendance(self):
        managed = self._punch()
        unrelated_employee = self.env['hr.employee'].create({
            'name': 'Synthetic same-company unrelated attendance owner',
        })
        unrelated = self.env['hr.attendance'].create({
            'employee_id': unrelated_employee.id,
            'check_in': '2026-12-01 09:00:00',
            'check_out': '2026-12-01 10:00:00',
        })
        self.assertTrue(managed.sl_shift_day_id)
        self.assertFalse(unrelated.sl_shift_day_id)
        restricted = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-shift@example.invalid', login='slshift-managed-attendance-reader',
            groups='base.group_user,sl_employee_shift_attendance.group_shift_approver',
        )
        approver_employee = self.env['hr.employee'].create({
            'name': 'Synthetic approver own attendance owner', 'user_id': restricted.id,
        })
        own_unmanaged = self.env['hr.attendance'].create({
            'employee_id': approver_employee.id,
            'check_in': '2026-12-02 09:00:00',
            'check_out': '2026-12-02 10:00:00',
        })
        self.assertFalse(own_unmanaged.sl_shift_day_id)
        actor_context = {'allowed_company_ids': [self.env.company.id]}
        managed_read = managed.with_user(restricted).with_context(**actor_context).read(['check_in'])
        self.assertEqual(managed_read[0]['id'], managed.id)
        with self.assertRaises(AccessError):
            own_unmanaged.with_user(restricted).with_context(**actor_context).read(['check_in'])
        with self.assertRaises(AccessError):
            unrelated.with_user(restricted).with_context(**actor_context).read(['check_in'])

        ordinary = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-shift@example.invalid', login='slshift-ordinary-attendance-reader',
            groups='base.group_user',
        )
        ordinary_employee = self.env['hr.employee'].create({
            'name': 'Synthetic ordinary user own attendance owner', 'user_id': ordinary.id,
        })
        ordinary_own = self.env['hr.attendance'].create({
            'employee_id': ordinary_employee.id,
            'check_in': '2026-12-03 09:00:00',
            'check_out': '2026-12-03 10:00:00',
        })
        ordinary_context = {'allowed_company_ids': [self.env.company.id]}
        ordinary_read = ordinary_own.with_user(ordinary).with_context(**ordinary_context).read(['check_in'])
        self.assertEqual(ordinary_read[0]['id'], ordinary_own.id)
        with self.assertRaises(AccessError):
            unrelated.with_user(ordinary).with_context(**ordinary_context).read(['check_in'])

    def test_shift_approver_read_access_is_company_scoped(self):
        company = self.env['res.company'].create({'name': 'Synthetic restricted summary company'})
        employee = self.env['hr.employee'].with_company(company).create({
            'name': 'Synthetic foreign summary employee', 'company_id': company.id,
        })
        assignment = self.env['sl.shift.assignment'].with_company(company).create({
            'employee_id': employee.id, 'shift_id': self.shift.id,
            'date_from': '2026-11-01', 'date_to': '2026-11-30',
            'attendance_policy': 'shift', 'schedule_tz': 'UTC',
            'workdays': '0,1,2,3,4,5,6', 'break_window_set': True, 'break_start': 22,
        })
        foreign = self.env['hr.attendance'].with_company(company).create({
            'employee_id': employee.id, 'check_in': '2026-11-02 18:00:00',
            'check_out': '2026-11-03 03:00:00',
        })
        self.assertTrue(assignment and foreign.sl_shift_day_id)
        restricted = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-shift@example.invalid', login='slshift-company-approver',
            groups='base.group_user,sl_employee_shift_attendance.group_shift_approver',
        )
        actor_context = {'allowed_company_ids': [self.env.company.id]}
        with self.assertRaises(AccessError):
            foreign.sl_shift_day_id.with_user(restricted).with_context(**actor_context).read(['state'])
        with self.assertRaises(AccessError):
            foreign.with_user(restricted).with_context(**actor_context).read(['check_in', 'check_out'])

    def test_ordinary_hr_cannot_read_private_shift_summary_or_audit(self):
        day = self._punch().sl_shift_day_id
        audit = day.audit_ids[:1]
        ordinary_hr = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-shift@example.invalid', login='slshift-ordinary-hr',
            groups='base.group_user,hr.group_hr_user',
        )
        with self.assertRaises(AccessError):
            day.with_user(ordinary_hr).read(['state', 'regular_hours', 'raw_overtime_hours'])
        with self.assertRaises(AccessError):
            audit.with_user(ordinary_hr).read(['event', 'reason', 'evidence'])

    def test_archived_assignment_still_blocks_overlapping_historical_period(self):
        self.assignment.active = False
        resolved, window = self.env['sl.shift.assignment']._sl_resolve(
            self.employee, '2026-11-02 18:00:00')
        self.assertEqual(resolved, self.assignment)
        self.assertEqual(str(window['date']), '2026-11-02')
        replacement_shift = self.env['sl.shift'].create({
            'name': 'Synthetic archived overlap replacement', 'start_time': 9, 'end_time': 17,
        })
        with self.assertRaises(ValidationError):
            self.env['sl.shift.assignment'].create({
                'employee_id': self.employee.id, 'shift_id': replacement_shift.id,
                'date_from': '2026-11-02', 'date_to': '2026-11-10',
            })

    def test_concurrent_missing_assignment_creates_serialize_by_employee(self):
        registry = self.env.registry
        fixture = {}
        with api.Environment.manage():
            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                employee = env['hr.employee'].create({'name': 'Synthetic concurrent overlap employee'})
                shift = env['sl.shift'].create({
                    'name': 'Synthetic concurrent overlap shift', 'start_time': 9, 'end_time': 17,
                })
                fixture.update(employee_id=employee.id, shift_id=shift.id)
                cr.commit()

        barrier = threading.Barrier(2)
        result_lock = threading.Lock()
        outcomes = []

        def create_competing_assignment():
            outcome = {'status': 'unexpected'}
            try:
                with api.Environment.manage():
                    with registry.cursor() as cr:
                        env = api.Environment(cr, SUPERUSER_ID, {})
                        cr.execute('SHOW transaction_isolation')
                        outcome['isolation'] = cr.fetchone()[0]
                        existing = env['sl.shift.assignment'].with_context(active_test=False).search_count([
                            ('employee_id', '=', fixture['employee_id']),
                            ('date_from', '<=', '2026-11-10'),
                            '|', ('date_to', '=', False), ('date_to', '>=', '2026-11-01'),
                        ])
                        outcome['initial_matches'] = existing
                        barrier.wait(timeout=20)
                        assignment = env['sl.shift.assignment'].create({
                            'employee_id': fixture['employee_id'], 'shift_id': fixture['shift_id'],
                            'date_from': '2026-11-01', 'date_to': '2026-11-10',
                        })
                        cr.commit()
                        outcome.update(status='created', assignment_id=assignment.id)
            except Exception as error:
                outcome.update(status='error', error_type=type(error).__name__,
                               sqlstate=getattr(error, 'pgcode', None), message=str(error))
            with result_lock:
                outcomes.append(outcome)

        threads = [threading.Thread(target=create_competing_assignment) for unused in range(2)]
        try:
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
            self.assertFalse(any(thread.is_alive() for thread in threads), 'Concurrent assignment transactions hung')
            self.assertEqual(len(outcomes), 2, outcomes)
            self.assertTrue(all(item.get('isolation') == 'repeatable read' for item in outcomes), outcomes)
            self.assertTrue(all(item.get('initial_matches') == 0 for item in outcomes), outcomes)
            self.assertEqual([item['status'] for item in outcomes].count('created'), 1, outcomes)
            self.assertEqual([item.get('sqlstate') for item in outcomes].count('40001'), 1, outcomes)
            with api.Environment.manage():
                with registry.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    assignments = env['sl.shift.assignment'].with_context(active_test=False).search([
                        ('employee_id', '=', fixture['employee_id']),
                    ])
                    self.assertEqual(len(assignments), 1)
                    with self.assertRaises(ValidationError):
                        env['sl.shift.assignment'].create({
                            'employee_id': fixture['employee_id'], 'shift_id': fixture['shift_id'],
                            'date_from': '2026-11-01', 'date_to': '2026-11-10',
                        })
                    cr.rollback()
        finally:
            with api.Environment.manage():
                with registry.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    env['sl.shift.assignment'].with_context(active_test=False).search([
                        ('employee_id', '=', fixture['employee_id']),
                    ]).unlink()
                    env['hr.employee'].browse(fixture['employee_id']).unlink()
                    env['sl.shift'].browse(fixture['shift_id']).unlink()
                    cr.commit()

    def test_concurrent_assignment_writes_serialize_same_period(self):
        registry = self.env.registry
        fixture = {}
        with api.Environment.manage():
            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                employee = env['hr.employee'].create({'name': 'Synthetic concurrent assignment writer'})
                shift = env['sl.shift'].create({
                    'name': 'Synthetic concurrent assignment writer shift', 'start_time': 9, 'end_time': 17,
                })
                first = env['sl.shift.assignment'].create({
                    'employee_id': employee.id, 'shift_id': shift.id,
                    'date_from': '2026-10-01', 'date_to': '2026-10-05',
                })
                second = env['sl.shift.assignment'].create({
                    'employee_id': employee.id, 'shift_id': shift.id,
                    'date_from': '2026-10-10', 'date_to': '2026-10-15',
                })
                fixture.update(employee_id=employee.id, shift_id=shift.id,
                               assignment_ids=[first.id, second.id])
                cr.commit()

        barrier = threading.Barrier(2)
        result_lock = threading.Lock()
        outcomes = []

        def move_competing_assignment(assignment_id):
            outcome = {'status': 'unexpected'}
            try:
                with api.Environment.manage():
                    with registry.cursor() as cr:
                        env = api.Environment(cr, SUPERUSER_ID, {})
                        cr.execute('SHOW transaction_isolation')
                        outcome['isolation'] = cr.fetchone()[0]
                        existing = env['sl.shift.assignment'].with_context(active_test=False).search_count([
                            ('employee_id', '=', fixture['employee_id']),
                            ('date_from', '<=', '2026-11-20'),
                            '|', ('date_to', '=', False), ('date_to', '>=', '2026-11-11'),
                        ])
                        outcome['initial_matches'] = existing
                        barrier.wait(timeout=20)
                        env['sl.shift.assignment'].browse(assignment_id).write({
                            'date_from': '2026-11-11', 'date_to': '2026-11-20',
                        })
                        cr.commit()
                        outcome.update(status='written', assignment_id=assignment_id)
            except Exception as error:
                outcome.update(status='error', error_type=type(error).__name__,
                               sqlstate=getattr(error, 'pgcode', None), message=str(error))
            with result_lock:
                outcomes.append(outcome)

        threads = [threading.Thread(target=move_competing_assignment, args=(assignment_id,))
                   for assignment_id in fixture['assignment_ids']]
        try:
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
            self.assertFalse(any(thread.is_alive() for thread in threads), 'Concurrent assignment writes hung')
            self.assertEqual(len(outcomes), 2, outcomes)
            self.assertTrue(all(item.get('isolation') == 'repeatable read' for item in outcomes), outcomes)
            self.assertTrue(all(item.get('initial_matches') == 0 for item in outcomes), outcomes)
            self.assertEqual([item['status'] for item in outcomes].count('written'), 1, outcomes)
            self.assertEqual([item.get('sqlstate') for item in outcomes].count('40001'), 1, outcomes)
            with api.Environment.manage():
                with registry.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    moved = env['sl.shift.assignment'].with_context(active_test=False).search([
                        ('employee_id', '=', fixture['employee_id']),
                        ('date_from', '=', '2026-11-11'), ('date_to', '=', '2026-11-20'),
                    ])
                    self.assertEqual(len(moved), 1)
                    loser_id = next(iter(set(fixture['assignment_ids']) - set(moved.ids)))
                    with self.assertRaises(ValidationError):
                        env['sl.shift.assignment'].browse(loser_id).write({
                            'date_from': '2026-11-11', 'date_to': '2026-11-20',
                        })
                    cr.rollback()
        finally:
            with api.Environment.manage():
                with registry.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    env['sl.shift.assignment'].with_context(active_test=False).search([
                        ('employee_id', '=', fixture['employee_id']),
                    ]).unlink()
                    env['hr.employee'].browse(fixture['employee_id']).unlink()
                    env['sl.shift'].browse(fixture['shift_id']).unlink()
                    cr.commit()

    def test_historical_template_cannot_be_unfrozen_by_disabling_policy(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        original_digest = day.digest
        with self.assertRaises(UserError):
            self.assignment.write({'attendance_policy': 'off'})
        self.assertEqual(self.assignment.attendance_policy, 'shift')
        self.assertEqual(day.digest, original_digest)

        # Simulate a historical row already disabled before this guard existed.
        self.env.cr.execute(
            "UPDATE sl_shift_assignment SET attendance_policy='off' WHERE id=%s",
            (self.assignment.id,),
        )
        self.assignment.invalidate_cache()
        with self.assertRaises(UserError):
            self.shift.write({'end_time': 5})
        self.assertEqual(self.shift.end_time, 3)
        self.assertEqual(day.digest, original_digest)

    def test_partial_approval_requires_role_and_reason(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        with self.assertRaises(AccessError):
            day.with_user(self.officer).action_approve(2, 'Unauthorized direct RPC')
        with self.assertRaises(ValidationError):
            day.with_user(self.approver).action_approve(3, 'Too many')
        with self.assertRaises(ValidationError):
            day.with_user(self.approver).action_approve(1, '')
        day.with_user(self.approver).action_approve(1, 'One hour verified')
        self.assertEqual(day.approved_overtime_hours, 1)
        self.assertEqual(day.approver_id, self.approver)
        self.assertEqual(attendance.sl_approved_overtime_hours, 1)
        audit_count = len(day.audit_ids)
        day.with_user(self.approver).action_approve(1, 'One hour verified')
        self.assertEqual(len(day.audit_ids), audit_count)

    def test_employee_cannot_approve_own_shift_day(self):
        self.employee.user_id = self.approver
        day = self._punch().sl_shift_day_id

        with self.assertRaises(AccessError):
            day.with_user(self.approver).action_approve(1, 'Employee self-approval must be denied')

        self.assertEqual(day.state, 'pending')
        self.assertFalse(day.approver_id)
        self.assertFalse(day.audit_ids.filtered(lambda audit: audit.event in ('approved', 'refused')))

    def test_another_authorized_approver_can_decide_employee_shift_day(self):
        self.employee.user_id = self.admin
        day = self._punch().sl_shift_day_id

        day.with_user(self.approver).action_approve(1, 'Independent authorized approval')

        self.assertEqual(day.state, 'approved')
        self.assertEqual(day.approver_id, self.approver)
        self.assertEqual(day.approved_overtime_hours, 1)

    def test_correction_revokes_approval_and_reuses_presence_anchor(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        day.with_user(self.approver).action_approve(2, 'Verified')
        attendance.with_user(self.officer).write({'check_out': '2026-11-03 04:00:00'})
        self.assertEqual(attendance.sl_shift_day_id, day)
        self.assertEqual((day.regular_hours, day.raw_overtime_hours, day.approved_overtime_hours, day.presence_days), (8, 1, 0, 1))
        self.assertEqual(day.state, 'pending')
        self.assertFalse(day.approver_id)
        self.assertTrue(day.audit_ids.filtered(lambda a: a.event == 'approved'))

    def test_verified_separate_break_punches_are_not_deducted_twice(self):
        punches = self.env['hr.attendance'].create([
            {'employee_id': self.employee.id, 'check_in': '2026-11-02 23:00:00', 'check_out': '2026-11-03 03:00:00'},
            {'employee_id': self.employee.id, 'check_in': '2026-11-02 18:00:00', 'check_out': '2026-11-02 22:00:00'},
        ])
        day = punches.sl_shift_day_id
        self.assertEqual(len(day), 1)
        self.assertEqual((sum(punches.mapped('worked_hours')), day.net_hours, day.raw_overtime_hours, day.presence_days), (8, 8, 0, 1))

    def test_unexplained_gap_is_not_lunch(self):
        punches = self.env['hr.attendance'].create([
            {'employee_id': self.employee.id, 'check_in': '2026-11-02 18:00:00', 'check_out': '2026-11-02 20:00:00'},
            {'employee_id': self.employee.id, 'check_in': '2026-11-02 21:00:00', 'check_out': '2026-11-03 03:00:00'},
        ])
        self.assertEqual(punches.sl_shift_day_id.net_hours, 7)
        self.assertEqual(punches.sl_shift_day_id.raw_overtime_hours, 0)

    def test_open_then_closed_has_no_payable_result_until_closed(self):
        attendance = self._punch(stop=False)
        day = attendance.sl_shift_day_id
        self.assertEqual((day.state, day.net_hours, day.presence_days), ('open', 0, 0))
        with self.assertRaises(ValidationError):
            day.with_user(self.approver).action_approve(0, 'Incomplete')
        attendance.check_out = '2026-11-03 03:00:00'
        self.assertEqual(attendance.sl_shift_day_id, day)
        self.assertEqual((day.state, day.net_hours, day.presence_days), ('pending', 8, 1))




    def test_dry_run_can_preview_unmanaged_history_before_opt_in(self):
        self.assignment.attendance_policy = 'off'
        attendance = self._punch(stop='2026-11-03 03:00:00')
        self.assertEqual(attendance.worked_hours, 9)
        preview = self.assignment.with_user(self.admin).action_repair_attendance()
        self.assertTrue(preview, 'Dry-run must show proposed correction before opt-in')
        self.assertEqual(preview[0]['proposed_net_hours'], 8)
        self.assertEqual(preview[0]['proposed_raw_overtime_hours'], 0)
        self.assertFalse(attendance.sl_shift_day_id)
        self.assertEqual(attendance.worked_hours, 9)

    def test_weekend_carryover_uses_start_workday(self):
        self.assignment.workdays = '0,1,2,3,4'
        friday = self._punch('2026-11-06 18:00:00', '2026-11-07 03:00:00')
        self.assertEqual((friday.sl_shift_day_id.net_hours, friday.sl_shift_day_id.presence_days), (8, 1))
        saturday = self._punch('2026-11-07 18:00:00', '2026-11-08 03:00:00')
        self.assertFalse(saturday.sl_shift_day_id)
        self.assertEqual(saturday.worked_hours, 9)
        self.assertEqual(friday.sl_raw_overtime_hours, 0)

    def test_past_assignment_does_not_use_todays_current_shift(self):
        self.assignment.write({'date_from': '2026-10-01', 'date_to': '2026-10-31'})
        day_shift = self.env['sl.shift'].create({'name': 'Current day control', 'start_time': 9, 'end_time': 17})
        self.env['sl.shift.assignment'].create({'employee_id': self.employee.id, 'shift_id': day_shift.id,
                                                'date_from': '2026-11-01', 'attendance_policy': 'off'})
        attendance = self._punch('2026-10-31 18:00:00', '2026-11-01 03:00:00')
        self.assertEqual(attendance.sl_shift_day_id.assignment_id, self.assignment)
        self.assertEqual(attendance.worked_hours, 8)

    def test_opted_in_day_shift_uses_its_own_explicit_break(self):
        day_shift = self.env['sl.shift'].create({'name': 'Explicit day control', 'start_time': 9, 'end_time': 18, 'break_minutes': 60})
        self.assignment.write({'shift_id': day_shift.id, 'break_start': 13})
        attendance = self._punch('2026-11-02 09:00:00', '2026-11-02 18:00:00')
        self.assertEqual((attendance.worked_hours, attendance.sl_raw_overtime_hours, attendance.sl_shift_day_id.presence_days), (8, 0, 1))

    def test_dst_ambiguous_break_is_rejected_not_guessed(self):
        with self.assertRaises(ValidationError):
            self.assignment.write({'date_from': '2026-10-24', 'date_to': '2026-10-31',
                                   'schedule_tz': 'Europe/Berlin', 'break_start': 2})

    def test_dry_run_is_read_only_and_repair_idempotent(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        old = day.read(['digest', 'write_date', 'approved_overtime_hours'])
        preview = self.assignment.with_user(self.admin).action_repair_attendance()
        self.assertEqual(preview[0]['proposed_net_hours'], 10)
        self.assertEqual(old, day.read(['digest', 'write_date', 'approved_overtime_hours']))
        self.assignment.with_user(self.admin).action_repair_attendance(False, 'Synthetic repair')
        self.assignment.with_user(self.admin).action_repair_attendance(False, 'Repeated synthetic repair')
        self.assertEqual(len(attendance.sl_shift_day_id), 1)
        self.assertEqual((day.net_hours, day.raw_overtime_hours, day.presence_days), (10, 2, 1))
        self.assertEqual(old[0]['digest'], day.digest)

    def test_authoritative_summary_crud_defaults_and_context_spoofing_refused(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        before = day.read(['digest', 'state', 'approved_overtime_hours'])
        for values in ({'net_hours': 99}, {'state': 'approved'}, {'approved_overtime_hours': 99}, {'assignment_id': False}):
            with self.assertRaises(AccessError):
                day.with_user(self.admin).with_context(_sl_shift_capability=True).write(values)
        with self.assertRaises(AccessError):
            self.env['sl.shift.day'].with_user(self.admin).with_context(default_state='approved').create({})
        with self.assertRaises(AccessError):
            day.with_user(self.admin).unlink()
        with self.assertRaises(AccessError):
            day.audit_ids.with_user(self.admin).write({'reason': 'Forged'})
        self.assertEqual(before, day.read(['digest', 'state', 'approved_overtime_hours']))

    def test_authoritative_attendance_fields_and_context_defaults_refused(self):
        attendance = self._punch()
        for values in ({'worked_hours': 99}, {'sl_regular_hours': 99}, {'sl_approved_overtime_hours': 99},
                       {'sl_shift_day_id': False}, {'sl_raw_overtime_hours': 99}):
            with self.assertRaises(AccessError):
                attendance.with_user(self.admin).write(values)
        with self.assertRaises(AccessError):
            self.env['hr.attendance'].with_user(self.admin).with_context(default_worked_hours=99).create({
                'employee_id': self.employee.id, 'check_in': '2026-11-03 18:00:00', 'check_out': '2026-11-04 03:00:00'})

    def test_historical_timezone_and_month_boundary_use_shift_start_presence(self):
        self.assignment.schedule_tz = 'Asia/Dubai'
        attendance = self._punch('2026-11-30 14:00:00', '2026-12-01 01:00:00')
        day = attendance.sl_shift_day_id
        self.assertEqual(str(day.shift_date), '2026-11-30')
        self.assertEqual((day.net_hours, day.regular_hours, day.raw_overtime_hours, day.presence_days), (10, 8, 2, 1))
        self.assertEqual(str(attendance.check_out), '2026-12-01 01:00:00')

    def test_synthetic_25_shift_month_not_client_totals(self):
        values = []
        for index in range(25):
            start = datetime(2026, 11, 1, 18) + timedelta(days=index)
            stop = start + timedelta(hours=11 if index == 24 else 9)
            values.append({'employee_id': self.employee.id, 'check_in': start, 'check_out': stop})
        attendances = self.env['hr.attendance'].create(values)
        days = attendances.sl_shift_day_id
        self.assertEqual(len(days), 25)
        self.assertEqual((sum(days.mapped('regular_hours')), sum(days.mapped('raw_overtime_hours')), sum(days.mapped('presence_days'))), (200, 2, 25))

    def test_unmanaged_native_day_shift_unchanged(self):
        employee = self.env['hr.employee'].create({'name': 'Unmanaged control'})
        self.env['sl.shift.assignment'].create({'employee_id': employee.id, 'shift_id': self.shift.id, 'date_from': '2026-11-01'})
        attendance = self.env['hr.attendance'].create({'employee_id': employee.id, 'check_in': '2026-11-02 18:00:00', 'check_out': '2026-11-03 03:00:00'})
        self.assertEqual(attendance.worked_hours, 9)
        self.assertFalse(attendance.sl_shift_day_id)

    def test_reassignment_recomputes_old_and_new_day(self):
        attendance = self._punch()
        old_day = attendance.sl_shift_day_id
        attendance.write({'check_in': '2026-11-03 18:00:00', 'check_out': '2026-11-04 03:00:00'})
        self.assertEqual((old_day.state, old_day.net_hours, old_day.presence_days), ('void', 0, 0))
        self.assertNotEqual(attendance.sl_shift_day_id, old_day)
        self.assertEqual(attendance.sl_shift_day_id.net_hours, 8)

    def test_hr_manager_cannot_edit_archived_opted_in_shift_metadata(self):
        hr_only = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-shift@example.invalid', login='slshift-hr-only-template',
            groups='base.group_user,hr.group_hr_manager',
        )
        self.assertTrue(hr_only.has_group('hr.group_hr_manager'))
        self.assertFalse(hr_only.has_group('hr_attendance.group_hr_attendance_manager'))
        self.assignment.active = False
        linked = self.env['sl.shift.assignment'].sudo().with_context(active_test=False).search([
            ('shift_id', '=', self.shift.id), ('attendance_policy', '=', 'shift'),
        ])
        self.assertEqual(linked, self.assignment)

        original = (self.shift.name, self.shift.code, self.shift.color, self.shift.active)
        actor_shift = self.shift.with_user(hr_only).with_context(allowed_company_ids=[self.env.company.id])
        changes = {
            'name': 'HR-only changed referenced shift',
            'code': 'HRONLY-REFERENCED-SHIFT',
            'color': 7,
            'active': False,
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                with self.assertRaises(AccessError):
                    actor_shift.write({field: value})
                self.shift.flush()
                self.env.cr.execute(
                    'SELECT name, code, color, active FROM sl_shift WHERE id=%s',
                    (self.shift.id,),
                )
                row = self.env.cr.fetchone()
                self.assertEqual((row[0], row[1] or False, row[2] or 0, row[3]), original)

    def test_dual_role_user_can_edit_opted_in_shift_metadata(self):
        dual_role = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-shift@example.invalid', login='slshift-dual-role-template',
            groups='base.group_user,hr.group_hr_manager,hr_attendance.group_hr_attendance_manager',
        )
        values = {
            'name': 'Dual-role authorized shift',
            'code': 'DUAL-ROLE-REFERENCED-SHIFT',
            'color': 8,
            'active': False,
        }
        self.shift.with_user(dual_role).with_context(
            allowed_company_ids=[self.env.company.id]).write(values)
        self.assertEqual(
            (self.shift.name, self.shift.code, self.shift.color, self.shift.active),
            (values['name'], values['code'], values['color'], values['active']),
        )

    def test_hr_manager_can_edit_unassigned_shift_metadata(self):
        hr_only = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-shift@example.invalid', login='slshift-hr-only-unassigned',
            groups='base.group_user,hr.group_hr_manager',
        )
        unassigned = self.env['sl.shift'].create({
            'name': 'Unassigned shift control', 'start_time': 9, 'end_time': 17,
        })
        self.assertFalse(self.env['sl.shift.assignment'].sudo().with_context(active_test=False).search([
            ('shift_id', '=', unassigned.id), ('attendance_policy', '=', 'shift'),
        ]))
        values = {
            'name': 'HR-only editable unassigned shift',
            'code': 'HRONLY-UNASSIGNED-SHIFT',
            'color': 9,
            'active': False,
        }
        unassigned.with_user(hr_only).with_context(
            allowed_company_ids=[self.env.company.id]).write(values)
        self.assertEqual(
            (unassigned.name, unassigned.code, unassigned.color, unassigned.active),
            (values['name'], values['code'], values['color'], values['active']),
        )

    def test_configuration_authority_and_explicit_break_required(self):
        with self.assertRaises(AccessError):
            self.assignment.with_user(self.officer).write({'break_start': 23})
        with self.assertRaises(ValidationError):
            self.assignment.with_user(self.admin).write({'break_window_set': False})
        with self.assertRaises(ValidationError):
            self.assignment.with_user(self.admin).write({'break_start': 12})

    def test_hr_manager_cannot_unlink_opted_in_assignment_then_edit_shift(self):
        hr_only = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-shift@example.invalid', login='slshift-hr-only-unlink',
            groups='base.group_user,hr.group_hr_manager',
        )
        self.assertTrue(hr_only.has_group('hr.group_hr_manager'))
        self.assertFalse(hr_only.has_group('hr_attendance.group_hr_attendance_manager'))
        self.assignment.active = False
        self.assignment.flush()
        actor_assignment = self.assignment.with_user(hr_only).with_context(
            allowed_company_ids=[self.env.company.id])
        actor_shift = self.shift.with_user(hr_only).with_context(
            allowed_company_ids=[self.env.company.id])

        self.env.cr.execute(
            'SELECT id, employee_id, shift_id, attendance_policy, active '
            'FROM sl_shift_assignment WHERE id=%s', (self.assignment.id,),
        )
        assignment_before = self.env.cr.fetchone()
        self.env.cr.execute(
            'SELECT name, start_time, end_time, break_minutes, active '
            'FROM sl_shift WHERE id=%s', (self.shift.id,),
        )
        shift_before = self.env.cr.fetchone()

        unlink_denied = False
        try:
            actor_assignment.unlink()
        except AccessError:
            unlink_denied = True
        edit_denied = False
        try:
            actor_shift.write({'name': 'HR-only removed assignment bypass'})
        except AccessError:
            edit_denied = True

        self.env.cr.execute(
            'SELECT id, employee_id, shift_id, attendance_policy, active '
            'FROM sl_shift_assignment WHERE id=%s', (self.assignment.id,),
        )
        assignment_after = self.env.cr.fetchone()
        self.env.cr.execute(
            'SELECT name, start_time, end_time, break_minutes, active '
            'FROM sl_shift WHERE id=%s', (self.shift.id,),
        )
        shift_after = self.env.cr.fetchone()
        self.assertTrue(unlink_denied, 'HR Manager without Attendance Administrator unlinked an opted-in assignment')
        self.assertTrue(edit_denied, 'HR Manager without Attendance Administrator edited the formerly referenced shift')
        self.assertEqual(assignment_after, assignment_before)
        self.assertEqual(shift_after, shift_before)

    def test_dual_role_user_can_unlink_opted_in_assignment_without_history(self):
        dual_role = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-shift@example.invalid', login='slshift-dual-role-unlink',
            groups='base.group_user,hr.group_hr_manager,hr_attendance.group_hr_attendance_manager',
        )
        self.assignment.active = False
        self.assignment.with_user(dual_role).with_context(
            allowed_company_ids=[self.env.company.id]).unlink()
        self.env.cr.execute(
            'SELECT count(*) FROM sl_shift_assignment WHERE id=%s', (self.assignment.id,),
        )
        self.assertEqual(self.env.cr.fetchone()[0], 0)

    def test_hr_manager_cannot_delete_employee_to_remove_opted_in_assignment(self):
        hr_only = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-shift@example.invalid', login='slshift-hr-only-employee-unlink',
            groups='base.group_user,hr.group_hr_manager',
        )
        employee = self.env['hr.employee'].create({'name': 'Synthetic cascade-delete employee'})
        shift = self.env['sl.shift'].create({
            'name': 'Synthetic cascade-delete shift', 'start_time': 9, 'end_time': 17,
        })
        assignment = self.env['sl.shift.assignment'].create({
            'employee_id': employee.id, 'shift_id': shift.id,
            'date_from': '2026-11-01', 'attendance_policy': 'shift',
            'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6',
            'break_window_set': True, 'break_start': 12,
        })
        assignment.active = False
        assignment.flush()
        actor_employee = employee.with_user(hr_only).with_context(
            allowed_company_ids=[self.env.company.id])
        actor_shift = shift.with_user(hr_only).with_context(
            allowed_company_ids=[self.env.company.id])

        self.env.cr.execute('SELECT id, name FROM hr_employee WHERE id=%s', (employee.id,))
        employee_before = self.env.cr.fetchone()
        self.env.cr.execute(
            'SELECT id, employee_id, shift_id, attendance_policy, active '
            'FROM sl_shift_assignment WHERE id=%s', (assignment.id,),
        )
        assignment_before = self.env.cr.fetchone()
        self.env.cr.execute(
            'SELECT name, start_time, end_time, break_minutes, active '
            'FROM sl_shift WHERE id=%s', (shift.id,),
        )
        shift_before = self.env.cr.fetchone()

        employee_delete_denied = False
        try:
            actor_employee.unlink()
        except AccessError:
            employee_delete_denied = True
        shift_edit_denied = False
        try:
            actor_shift.write({'name': 'HR-only cascaded assignment bypass'})
        except AccessError:
            shift_edit_denied = True

        self.env.cr.execute('SELECT id, name FROM hr_employee WHERE id=%s', (employee.id,))
        employee_after = self.env.cr.fetchone()
        self.env.cr.execute(
            'SELECT id, employee_id, shift_id, attendance_policy, active '
            'FROM sl_shift_assignment WHERE id=%s', (assignment.id,),
        )
        assignment_after = self.env.cr.fetchone()
        self.env.cr.execute(
            'SELECT name, start_time, end_time, break_minutes, active '
            'FROM sl_shift WHERE id=%s', (shift.id,),
        )
        shift_after = self.env.cr.fetchone()
        self.assertTrue(employee_delete_denied, 'Employee deletion bypassed the assignment unlink guard')
        self.assertTrue(shift_edit_denied, 'Employee cascade removal exposed the shift to unauthorized editing')
        self.assertEqual(employee_after, employee_before)
        self.assertEqual(assignment_after, assignment_before)
        self.assertEqual(shift_after, shift_before)

    def test_employee_delete_preserves_history_evidence_refusal(self):
        self._punch()
        employee_before = self.employee.id
        assignment_before = self.assignment.id
        deletion_error = None
        try:
            with self.env.cr.savepoint():
                self.employee.with_user(self.admin).with_context(
                    allowed_company_ids=[self.env.company.id]).unlink()
        except Exception as error:
            deletion_error = error
        self.assertIsInstance(
            deletion_error, UserError,
            'Deleting an employee with shift evidence must retain the assignment history refusal; got %s'
            % (type(deletion_error).__name__ if deletion_error else 'no error'),
        )
        self.env.cr.execute('SELECT id FROM hr_employee WHERE id=%s', (employee_before,))
        self.assertEqual(self.env.cr.fetchone()[0], employee_before)
        self.env.cr.execute(
            'SELECT id FROM sl_shift_assignment WHERE id=%s', (assignment_before,),
        )
        self.assertEqual(self.env.cr.fetchone()[0], assignment_before)

    def test_archive_keeps_historical_integration_and_unlink_keeps_evidence(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        self.assignment.active = False
        attendance.check_out = '2026-11-03 04:00:00'
        self.assertEqual(attendance.sl_shift_day_id, day)
        self.assertEqual(day.raw_overtime_hours, 1)
        with self.assertRaises(UserError):
            self.assignment.unlink()

    def test_employee_company_is_frozen_with_attendance_only_evidence(self):
        self._punch()
        company = self.env['res.company'].create({'name': 'Synthetic Company Move'})
        with self.assertRaises(UserError):
            self.employee.with_user(self.admin).with_context(allowed_company_ids=[self.env.company.id, company.id]).write({'company_id': company.id})
        self.assertEqual(self.employee.company_id, self.env.company)

    def test_assignment_employee_is_not_reparented_after_history_exists(self):
        attendance = self._punch()
        other = self.env['hr.employee'].create({'name': 'Synthetic same-company target'})
        with self.assertRaises(UserError):
            self.assignment.with_user(self.admin).write({'employee_id': other.id})
        self.assertEqual(attendance.sl_shift_day_id.employee_id, self.employee)
        self.assertEqual(self.assignment.employee_id, self.employee)

    def test_cross_company_reparenting_rejected(self):
        attendance = self._punch()
        company = self.env['res.company'].create({'name': 'Synthetic Foreign Company'})
        foreign_employee = self.env['hr.employee'].with_company(company).create({'name': 'Foreign Synthetic Employee', 'company_id': company.id})
        with self.assertRaises(AccessError):
            self.assignment.with_user(self.admin).with_context(allowed_company_ids=[self.env.company.id]).write({'employee_id': foreign_employee.id})
        self.assertEqual(self.assignment.employee_id, self.employee)
        with self.assertRaises(AccessError):
            attendance.sl_shift_day_id.with_user(self.approver).with_context(allowed_company_ids=[company.id]).action_approve(2, 'Foreign attempt')
