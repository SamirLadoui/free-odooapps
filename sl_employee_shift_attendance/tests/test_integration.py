# SPDX-License-Identifier: LGPL-3.0-or-later
from datetime import datetime, timedelta
import json

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestShiftIntegration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create({'name': 'Synthetic Shift Integration'})
        cls.shift = cls.env['sl.shift'].create({'name': 'Synthetic 18-03', 'start_time': 18, 'end_time': 3, 'break_minutes': 60})
        cls.assignment = cls.env['sl.shift.assignment'].create({
            'employee_id': cls.employee.id, 'shift_id': cls.shift.id,
            'date_from': '2026-11-01', 'date_to': '2026-11-30', 'attendance_policy': 'shift',
            'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6', 'break_window_set': True, 'break_start': 22,
        })
        cls.approver = new_test_user(cls.env, login='slshift-approver',
                                    groups='base.group_user,hr.group_hr_user,sl_employee_shift_attendance.group_shift_approver')
        cls.self_approver = new_test_user(
            cls.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-self-approver',
            groups='base.group_user,hr.group_hr_user,sl_employee_shift_attendance.group_shift_approver',
        )
        cls.officer = new_test_user(cls.env, login='slshift-officer',
                                   groups='base.group_user,hr.group_hr_user,hr_attendance.group_hr_attendance_user')
        cls.admin = new_test_user(cls.env, login='slshift-config-admin',
                                 groups='base.group_user,hr.group_hr_manager,hr_attendance.group_hr_attendance_manager,sl_employee_shift_attendance.group_shift_approver')

    def _punch(self, start='2026-11-02 18:00:00', stop='2026-11-03 05:00:00', **values):
        return self.env['hr.attendance'].create(dict(employee_id=self.employee.id, check_in=start, check_out=stop, **values))

    def test_summary_regular_raw_approved_presence_and_native_exclusion(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        self.assertTrue(day)
        self.assertEqual((day.elapsed_hours, day.net_hours, day.regular_hours, day.raw_overtime_hours,
                          day.approved_overtime_hours, day.presence_days), (11, 10, 8, 2, 0, 1))
        self.assertFalse(self.env['hr.attendance.overtime'].search([('employee_id', '=', self.employee.id)]))
        self.assertEqual(day.expected_hours, 8)

    def test_guarded_decision_wizard_works_for_restricted_approver(self):
        from odoo.tests import Form
        day = self._punch().sl_shift_day_id.with_user(self.approver)
        action = day.action_open_decision()
        self.assertEqual(action['res_model'], 'sl.shift.decision')
        form = Form(self.env['sl.shift.decision'].with_user(self.approver).with_context(action['context']))
        form.hours = 1
        form.reason = 'Restricted-user Form approval'
        wizard = form.save()
        wizard.action_confirm()
        self.assertEqual(day.approved_overtime_hours, 1)
        self.assertEqual(day.approver_id, self.approver)
        with self.assertRaises(AccessError):
            day.with_user(self.officer).action_open_decision()

    def test_opted_template_metadata_writes_require_both_admin_roles(self):
        hr_manager = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-hr-only-metadata@example.invalid',
            login='slshift-hr-only-metadata',
            groups='base.group_user,hr.group_hr_manager',
        )
        self.assertTrue(hr_manager.has_group('hr.group_hr_manager'))
        self.assertFalse(hr_manager.has_group('hr_attendance.group_hr_attendance_manager'))

        employee = self.env['hr.employee'].create({'name': 'Synthetic metadata template owner'})
        template = self.env['sl.shift'].create({
            'name': 'Synthetic metadata template', 'code': 'META-BASE', 'color': 1,
            'start_time': 9, 'end_time': 17,
        })
        assignment = self.env['sl.shift.assignment'].create({
            'employee_id': employee.id, 'shift_id': template.id,
            'date_from': '2026-11-09', 'attendance_policy': 'shift', 'active': False,
            'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6',
        })
        self.assertEqual(assignment.attendance_policy, 'shift')
        self.assertFalse(self.env['hr.attendance'].search([('employee_id', '=', employee.id)]))
        self.assertTrue(template.with_user(hr_manager).check_access_rights(
            'write', raise_exception=False), 'Native HR Manager ACL grants shift write access')

        def persisted_template_state():
            self.env['base'].flush()
            self.env.cr.execute(
                'SELECT name, code, color, active FROM sl_shift WHERE id = %s',
                (template.id,),
            )
            return self.env.cr.fetchone()

        metadata_edits = (
            ('name', 'Synthetic renamed opted template'),
            ('code', 'META-DENIED'),
            ('color', 7),
            ('active', False),
        )
        unexpected_writes = []

        class UnexpectedWrite(Exception):
            pass

        for field_name, value in metadata_edits:
            before = persisted_template_state()
            try:
                with self.env.cr.savepoint():
                    try:
                        template.with_user(hr_manager).write({field_name: value})
                    except AccessError as error:
                        self.assertIn(
                            'Shift attendance configuration requires HR and Attendance administrator roles',
                            str(error),
                        )
                    else:
                        unexpected_writes.append(field_name)
                        raise UnexpectedWrite()
            except UnexpectedWrite:
                pass
            template.flush(['name', 'code', 'color', 'active'])
            self.assertEqual(persisted_template_state(), before,
                             'Denied %s write changed the persisted template' % field_name)

        self.assertTrue(self.admin.has_group('hr.group_hr_manager'))
        self.assertTrue(self.admin.has_group('hr_attendance.group_hr_attendance_manager'))
        dual_role_edits = (
            ('name', 'Synthetic dual-role opted template'),
            ('code', 'META-DUAL'),
            ('color', 8),
            ('active', False),
        )
        for field_name, value in dual_role_edits:
            template.with_user(self.admin).write({field_name: value})
            self.assertEqual(persisted_template_state()[
                {'name': 0, 'code': 1, 'color': 2, 'active': 3}[field_name]], value)

        unassigned_template = self.env['sl.shift'].create({
            'name': 'Synthetic unassigned metadata template', 'code': 'META-UNASSIGNED',
            'color': 2, 'start_time': 8, 'end_time': 16,
        })
        unassigned_edits = (
            ('name', 'Synthetic edited unassigned template'),
            ('code', 'META-UNASSIGNED-EDITED'),
            ('color', 5),
            ('active', False),
        )
        for field_name, value in unassigned_edits:
            unassigned_template.with_user(hr_manager).write({field_name: value})
            self.assertEqual(unassigned_template.with_user(hr_manager)[field_name], value)

        self.assertFalse(unexpected_writes,
                         'HR-only manager wrote opted-in template fields: %s' % unexpected_writes)

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
        self.assertEqual(day.approved_overtime_hours, 1)
        audit_count = len(day.audit_ids)
        day.with_user(self.approver).action_approve(1, 'One hour verified')
        self.assertEqual(len(day.audit_ids), audit_count)

    def test_employee_cannot_approve_own_shift_but_independent_approver_can(self):
        independent_day = self._punch().sl_shift_day_id
        self.assertFalse(self.employee.user_id)
        independent_day.with_user(self.approver).action_approve(1, 'Independent approver control')
        self.assertEqual(independent_day.approver_id, self.approver)

        linked_employee = self.env['hr.employee'].create({
            'name': 'Synthetic self-approver employee',
            'user_id': self.self_approver.id,
        })
        self.assertEqual(linked_employee.user_id, self.self_approver,
                         'Use Odoo 15 hr.employee.user_id linked to resource.user_id')
        self.env['sl.shift.assignment'].create({
            'employee_id': linked_employee.id,
            'shift_id': self.shift.id,
            'date_from': '2026-11-01',
            'date_to': '2026-11-30',
            'attendance_policy': 'shift',
            'schedule_tz': 'UTC',
            'workdays': '0,1,2,3,4,5,6',
            'break_window_set': True,
            'break_start': 22,
        })
        attendance = self.env['hr.attendance'].create({
            'employee_id': linked_employee.id,
            'check_in': '2026-11-04 18:00:00',
            'check_out': '2026-11-05 05:00:00',
        })
        self_day = attendance.sl_shift_day_id
        with self.assertRaises(AccessError):
            self_day.with_user(self.self_approver).action_approve(1, 'Self-approval attempt')
        self.assertEqual(self_day.state, 'pending')
        self.assertFalse(self_day.approver_id)
        self.assertFalse(self_day.audit_ids.filtered(lambda event: event.event == 'approved'))

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

    def _explicit_native_wrong_ruleset(self):
        self.env.company.write({'hr_attendance_overtime': True, 'overtime_start_date': '2026-01-01',
                                'overtime_company_threshold': 0, 'overtime_employee_threshold': 0})
        empty_calendar = self.env['resource.calendar'].create({
            'name': 'Synthetic empty native15 calendar', 'tz': 'UTC', 'attendance_ids': [(5, 0, 0)]})
        self.employee.resource_calendar_id = empty_calendar

    def test_pending_native_history_is_reconciled_to_one_authoritative_engine(self):
        self.assignment.attendance_policy = 'off'
        self._explicit_native_wrong_ruleset()
        attendance = self._punch()
        native = self.env['hr.attendance.overtime'].search([('employee_id', '=', self.employee.id)])
        self.assertTrue(native)
        self.assertEqual(sum(native.mapped('duration')), 11)
        adjustment = self.env['hr.attendance.overtime'].create({'employee_id': self.employee.id, 'date': '2026-11-02', 'duration': 0.5, 'duration_real': 0.5, 'adjustment': True})
        self.assignment.with_user(self.admin).write({'attendance_policy': 'shift'})
        self.assignment.with_user(self.admin).action_repair_attendance(False, 'Explicit historical adoption')
        self.assertFalse(native.exists())
        self.assertEqual((adjustment.exists().duration, adjustment.adjustment), (0.5, True))
        day = attendance.sl_shift_day_id
        self.assertEqual((attendance.worked_hours, day.regular_hours, day.raw_overtime_hours, day.approved_overtime_hours), (10, 8, 2, 0))
        removed = json.loads(day.audit_ids.filtered(lambda a: a.event == 'recomputed').evidence)['removed_native_lines']
        self.assertTrue(removed)
        self.assertEqual(sum(v['duration'] for v in removed), 11)

    def test_modified_native_daily_history_blocks_adoption_atomically(self):
        self.assignment.attendance_policy = 'off'
        self._explicit_native_wrong_ruleset()
        attendance = self._punch()
        native = self.env['hr.attendance.overtime'].search([('employee_id', '=', self.employee.id)])
        original_ids = native.ids
        native.write({'duration': 5})
        self.assertEqual(native.duration_real, 11)
        preview = self.assignment.with_user(self.admin).action_repair_attendance()
        self.assertTrue(preview[0]['native_decision_blocks_repair'])
        with self.env.cr.savepoint():
            try:
                self.assignment.with_user(self.admin).write({'attendance_policy': 'shift'})
            except UserError:
                pass
            else:
                self.fail('Modified native daily overtime was silently replaced')
            self.env['base'].flush()
            self.env.cr.execute('SELECT attendance_policy FROM sl_shift_assignment WHERE id = %s', (self.assignment.id,))
            self.assertEqual(self.env.cr.fetchone()[0], 'off')
            self.assertEqual(native.exists().ids, original_ids)
            self.assertFalse(attendance.sl_shift_day_id)
            self.assertEqual(attendance.worked_hours, 11)

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
        self.assertFalse(self.env['hr.attendance.overtime'].search([('employee_id', '=', self.employee.id), ('date', '=', '2026-11-06'), ('adjustment', '=', False)]))

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
        self.assertEqual((attendance.worked_hours, attendance.sl_shift_day_id.raw_overtime_hours, attendance.sl_shift_day_id.presence_days), (8, 0, 1))

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
        for values in ({'worked_hours': 99}, {'sl_elapsed_hours': 99}, {'sl_shift_day_id': False}):
            with self.assertRaises(AccessError):
                attendance.with_user(self.admin).write(values)
        with self.assertRaises(AccessError):
            self.env['hr.attendance'].with_user(self.admin).with_context(default_worked_hours=99).create({
                'employee_id': self.employee.id, 'check_in': '2026-11-03 18:00:00', 'check_out': '2026-11-04 03:00:00'})
        with self.assertRaises(AccessError):
            self.env['hr.attendance.overtime'].with_user(self.admin).create({
                'employee_id': self.employee.id, 'date': '2026-11-02', 'duration': 11, 'duration_real': 11})

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

    def test_configuration_authority_and_explicit_break_required(self):
        with self.assertRaises(AccessError):
            self.assignment.with_user(self.officer).write({'break_start': 23})
        with self.assertRaises(ValidationError):
            self.assignment.with_user(self.admin).write({'break_window_set': False})
        with self.assertRaises(ValidationError):
            self.assignment.with_user(self.admin).write({'break_start': 12})

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

    def test_assignment_overlap_writes_advance_owned_serialization_guard(self):
        employee = self.env['hr.employee'].create({'name': 'Synthetic assignment guard worker'})
        assignment = self.env['sl.shift.assignment'].create({
            'employee_id': employee.id, 'shift_id': self.shift.id,
            'date_from': '2026-11-01', 'date_to': '2026-11-30', 'attendance_policy': 'off',
        })
        self.env.cr.execute('SELECT generation FROM sl_shift_guard WHERE employee_id = %s', (employee.id,))
        created_generation = self.env.cr.fetchone()
        self.assertTrue(created_generation, 'Assignment creation did not touch its module-owned serialization row')
        assignment.write({'date_to': '2026-11-29'})
        self.env.cr.execute('SELECT generation FROM sl_shift_guard WHERE employee_id = %s', (employee.id,))
        written_generation = self.env.cr.fetchone()[0]
        self.assertGreater(written_generation, created_generation[0],
                           'Assignment period edits must advance the same overlap serialization row')

    def test_disabled_assignment_employee_remains_frozen_after_history(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        self.assignment.attendance_policy = 'off'
        self.assertEqual(day.state, 'void')
        target = self.env['hr.employee'].create({'name': 'Disabled-assignment reparent target'})
        with self.env.cr.savepoint():
            try:
                self.assignment.with_user(self.admin).write({'employee_id': target.id})
            except UserError:
                pass
            else:
                self.fail('Disabling integration bypassed historical assignment identity protection')
            self.env['base'].flush()
            self.env.cr.execute('SELECT employee_id FROM sl_shift_assignment WHERE id = %s', (self.assignment.id,))
            self.assertEqual(self.env.cr.fetchone()[0], self.employee.id)

    def test_disabled_historical_assignment_and_shift_schedule_are_frozen(self):
        self._punch()
        self.assignment.with_user(self.admin).write({'attendance_policy': 'off'})
        self.assertFalse(self.assignment.attendance_policy == 'shift')
        replacement_shift = self.env['sl.shift'].create({
            'name': 'Synthetic replacement after historical freeze', 'start_time': 9, 'end_time': 17,
        })
        self.env['base'].flush()
        self.env.cr.execute('SELECT row_to_json(a) FROM sl_shift_assignment a WHERE id = %s', (self.assignment.id,))
        assignment_before = self.env.cr.fetchone()
        self.env.cr.execute('SELECT row_to_json(s) FROM sl_shift s WHERE id = %s', (self.shift.id,))
        shift_before = self.env.cr.fetchone()

        mutations = [
            ('assignment shift', lambda: self.assignment.with_user(self.admin).write({'shift_id': replacement_shift.id})),
            ('assignment date_from', lambda: self.assignment.with_user(self.admin).write({'date_from': '2026-11-02'})),
            ('assignment date_to', lambda: self.assignment.with_user(self.admin).write({'date_to': '2026-11-29'})),
            ('assignment timezone', lambda: self.assignment.with_user(self.admin).write({'schedule_tz': 'Asia/Dubai'})),
            ('assignment workdays', lambda: self.assignment.with_user(self.admin).write({'workdays': '1,2,3,4,5'})),
            ('assignment break confirmation', lambda: self.assignment.with_user(self.admin).write({'break_window_set': False})),
            ('assignment break start', lambda: self.assignment.with_user(self.admin).write({'break_start': 21})),
            ('shared shift start', lambda: self.shift.with_user(self.admin).write({'start_time': 17})),
            ('shared shift end', lambda: self.shift.with_user(self.admin).write({'end_time': 4})),
            ('shared shift break', lambda: self.shift.with_user(self.admin).write({'break_minutes': 90})),
        ]
        for label, operation in mutations:
            with self.env.cr.savepoint():
                try:
                    operation()
                except UserError:
                    pass
                else:
                    self.fail('%s changed historical schedule after attendance policy was disabled' % label)
                self.env['base'].flush()
                self.env.cr.execute('SELECT row_to_json(a) FROM sl_shift_assignment a WHERE id = %s', (self.assignment.id,))
                self.assertEqual(self.env.cr.fetchone(), assignment_before, label)
                self.env.cr.execute('SELECT row_to_json(s) FROM sl_shift s WHERE id = %s', (self.shift.id,))
                self.assertEqual(self.env.cr.fetchone(), shift_before, label)

        control_employee = self.env['hr.employee'].create({'name': 'Synthetic no-history schedule control'})
        control_shift = self.env['sl.shift'].create({'name': 'Synthetic mutable control shift', 'start_time': 9, 'end_time': 17})
        control_assignment = self.env['sl.shift.assignment'].create({
            'employee_id': control_employee.id, 'shift_id': control_shift.id, 'date_from': '2026-11-01',
        })
        control_assignment.write({'schedule_tz': 'Asia/Dubai', 'workdays': '1,2,3,4,5', 'break_start': 12})
        control_shift.write({'start_time': 10})
        self.assertEqual((control_assignment.schedule_tz, control_assignment.workdays, control_shift.start_time),
                         ('Asia/Dubai', '1,2,3,4,5', 10))

    def test_cross_company_reparenting_rejected(self):
        attendance = self._punch()
        company = self.env['res.company'].create({'name': 'Synthetic Foreign Company'})
        foreign_employee = self.env['hr.employee'].with_company(company).create({'name': 'Foreign Synthetic Employee', 'company_id': company.id})
        with self.assertRaises(AccessError):
            self.assignment.with_user(self.admin).with_context(allowed_company_ids=[self.env.company.id]).write({'employee_id': foreign_employee.id})
        self.assertEqual(self.assignment.employee_id, self.employee)
        with self.assertRaises(AccessError):
            attendance.sl_shift_day_id.with_user(self.approver).with_context(allowed_company_ids=[company.id]).action_approve(2, 'Foreign attempt')

    def test_native15_engine_excludes_managed_employee_days_not_adjustments_or_unrelated_days(self):
        self._explicit_native_wrong_ruleset()
        managed = self._punch()
        self.assertTrue(managed.sl_shift_day_id)
        self.assertFalse(self.env['hr.attendance.overtime'].search([('employee_id', '=', self.employee.id)]))
        adjustment = self.env['hr.attendance.overtime'].create({'employee_id': self.employee.id, 'date': '2026-11-02', 'duration': 0.5, 'adjustment': True})
        adjustment.duration = 0.75
        self.assertEqual(adjustment.duration, 0.75)
        with self.assertRaises(AccessError):
            adjustment.write({'adjustment': False})
        other = self.env['hr.employee'].create({'name': 'Native15 unrelated', 'resource_calendar_id': self.employee.resource_calendar_id.id})
        self.env['hr.attendance'].create({'employee_id': other.id, 'check_in': '2026-11-02 18:00:00', 'check_out': '2026-11-03 03:00:00'})
        native = self.env['hr.attendance.overtime'].search([('employee_id', '=', other.id), ('adjustment', '=', False)])
        self.assertEqual(sum(native.mapped('duration')), 9)
        before = self.env['hr.attendance'].create({'employee_id': self.employee.id, 'check_in': '2026-10-31 18:00:00', 'check_out': '2026-11-01 03:00:00'})
        self.assertEqual(before.worked_hours, 9)
        native = self.env['hr.attendance.overtime'].search([('employee_id', '=', self.employee.id), ('date', '=', '2026-10-31'), ('adjustment', '=', False)])
        self.assertEqual(sum(native.mapped('duration')), 9)

    def test_caught_cross_company_attendance_reparent_is_atomic(self):
        attendance = self._punch()
        company = self.env['res.company'].create({'name': 'Synthetic Attendance Foreign'})
        foreign = self.env['hr.employee'].with_company(company).create({'name': 'Synthetic foreign destination', 'company_id': company.id})
        actor = attendance.with_user(self.admin).with_context(allowed_company_ids=[self.env.company.id])
        with self.env.cr.savepoint():
            try:
                actor.write({'employee_id': foreign.id})
            except AccessError:
                pass
            else:
                self.fail('Foreign employee reparent accepted')
            self.env['base'].flush()
            self.env.cr.execute('SELECT employee_id FROM hr_attendance WHERE id = %s', (attendance.id,))
            self.assertEqual(self.env.cr.fetchone()[0], self.employee.id)

    def test_foreign_summary_and_audit_reads_are_denied(self):
        day = self._punch().sl_shift_day_id
        other = self.env['res.company'].create({'name': 'Synthetic foreign viewer company'})
        foreign = new_test_user(self.env['res.users'].with_context(no_reset_password=True).env, login='slshift-foreign-viewer',
            groups='base.group_user,hr.group_hr_user,sl_employee_shift_attendance.group_shift_approver',
            company_id=other.id, company_ids=[(6, 0, [other.id])])
        with self.assertRaises(AccessError):
            day.with_user(foreign).with_context(allowed_company_ids=[other.id]).read(['net_hours'])
        with self.assertRaises(AccessError):
            day.audit_ids.with_user(foreign).with_context(allowed_company_ids=[other.id]).read(['reason'])

    def test_ordinary_hr_user_cannot_read_shift_summary_or_audit(self):
        day = self._punch().sl_shift_day_id
        ordinary_hr = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-ordinary-hr-reader',
            groups='base.group_user,hr.group_hr_user',
        )
        self.assertFalse(ordinary_hr.has_group('hr_attendance.group_hr_attendance_user'))
        with self.assertRaises(AccessError):
            day.with_user(ordinary_hr).read(['net_hours'])
        with self.assertRaises(AccessError):
            day.audit_ids.with_user(ordinary_hr).read(['reason'])

        # The shift approver is intentionally allowed in the record's company.
        self.assertTrue(day.with_user(self.approver).read(['net_hours']))
        self.assertTrue(day.audit_ids.with_user(self.approver).read(['reason']))

        other = self.env['res.company'].create({'name': 'Synthetic foreign shift reader'})
        foreign_approver = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-foreign-approver-reader',
            groups='base.group_user,hr.group_hr_user,sl_employee_shift_attendance.group_shift_approver',
            company_id=other.id, company_ids=[(6, 0, [other.id])],
        )
        with self.assertRaises(AccessError):
            day.with_user(foreign_approver).with_context(allowed_company_ids=[other.id]).read(['net_hours'])
        with self.assertRaises(AccessError):
            day.audit_ids.with_user(foreign_approver).with_context(allowed_company_ids=[other.id]).read(['reason'])

    def test_hr_only_user_cannot_opt_in_from_ir_default(self):
        hr_user = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-ir-default-attendance@example.invalid',
            login='slshift-ir-default-attendance',
            groups='base.group_user,hr.group_hr_user',
        )
        self.assertTrue(hr_user.has_group('hr.group_hr_user'))
        self.assertFalse(hr_user.has_group('hr.group_hr_manager'))
        self.assertFalse(hr_user.has_group('hr_attendance.group_hr_attendance_user'))
        assignments = self.env['sl.shift.assignment'].with_user(hr_user).with_context(
            allowed_company_ids=[hr_user.company_id.id])

        control_employee = self.env['hr.employee'].create({'name': 'Synthetic HR-only default control'})
        control = assignments.create({
            'employee_id': control_employee.id, 'shift_id': self.shift.id,
            'date_from': '2027-01-01', 'date_to': '2027-01-07', 'attendance_policy': 'off',
        })
        self.assertEqual(control.attendance_policy, 'off')

        target_employee = self.env['hr.employee'].create({'name': 'Synthetic HR-only default target'})
        defaults = self.env['ir.default'].sudo()
        defaults.set(
            'sl.shift.assignment', 'attendance_policy', 'shift',
            user_id=hr_user.id, company_id=hr_user.company_id.id,
        )
        try:
            self.assertEqual(assignments.default_get(['attendance_policy'])['attendance_policy'], 'shift')
            with self.env.cr.savepoint():
                try:
                    assignments.create({
                        'employee_id': target_employee.id, 'shift_id': self.shift.id,
                        'date_from': '2027-02-01', 'date_to': '2027-02-07',
                        'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6',
                        'break_window_set': True, 'break_start': 22,
                    })
                except AccessError as error:
                    self.assertIn('Enabling shift integration requires HR and Attendance administrator roles', str(error))
                else:
                    self.fail('An HR-only user enabled shift attendance through ir.default')
                self.env['base'].flush()
                self.env.cr.execute(
                    'SELECT COUNT(*) FROM sl_shift_assignment WHERE employee_id = %s',
                    (target_employee.id,),
                )
                self.assertEqual(self.env.cr.fetchone()[0], 0)
        finally:
            defaults.search([
                ('field_id.model', '=', 'sl.shift.assignment'),
                ('field_id.name', '=', 'attendance_policy'),
                ('user_id', '=', hr_user.id),
                ('company_id', '=', hr_user.company_id.id),
            ]).unlink()
            defaults.clear_caches()

    def test_shift_approver_cannot_access_arbitrary_native_attendance(self):
        approver = self.approver

        unrelated_employee = self.env['hr.employee'].create({'name': 'Synthetic unrelated native attendance owner'})
        native_attendance = self.env['hr.attendance'].create({
            'employee_id': unrelated_employee.id,
            'check_in': '2026-11-02 09:00:00',
            'check_out': '2026-11-02 17:00:00',
        })
        actor_attendance = native_attendance.with_user(approver).with_context(
            allowed_company_ids=[self.env.company.id])
        with self.assertRaises(AccessError):
            actor_attendance.read(['employee_id', 'check_in'])
        with self.assertRaises(AccessError):
            actor_attendance.write({'check_out': '2026-11-02 18:00:00'})
        self.assertTrue(approver.has_group('sl_employee_shift_attendance.group_shift_approver'))
        self.assertFalse(approver.has_group('hr_attendance.group_hr_attendance_user'))

        day = self._punch().sl_shift_day_id.with_user(approver)
        self.assertEqual(day.read(['net_hours'])[0]['net_hours'], 10)
        self.assertTrue(day.action_approve(1, 'Authorized custom shift decision'))
        self.assertEqual(day.read(['approved_overtime_hours'])[0]['approved_overtime_hours'], 1)
        audit_rows = day.audit_ids.read(['event', 'reason'])
        self.assertTrue(any(row['event'] == 'approved' for row in audit_rows))
