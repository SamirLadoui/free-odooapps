# SPDX-License-Identifier: LGPL-3.0-or-later
from datetime import datetime, timedelta

from odoo import Command
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
        cls.officer = new_test_user(cls.env, login='slshift-officer',
                                   groups='base.group_user,hr.group_hr_user,hr_attendance.group_hr_attendance_officer')
        cls.employee.attendance_manager_id = cls.officer
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
        self.assertEqual(day.regular_hours, 8)

    def test_guarded_decision_wizard_works_for_restricted_approver(self):
        from odoo.tests import Form
        day = self._punch().sl_shift_day_id.with_user(self.approver)
        action = day.action_open_decision()
        self.assertEqual(action['res_model'], 'sl.shift.decision')
        with Form(self.env['sl.shift.decision'].with_user(self.approver).with_context(action['context'])) as form:
            form.hours = 1
            form.reason = 'Restricted-user Form approval'
        wizard = form.record
        wizard.action_confirm()
        self.assertEqual(day.approved_overtime_hours, 1)
        self.assertEqual(day.approver_id, self.approver)
        with self.assertRaises(AccessError):
            day.with_user(self.officer).action_open_decision()

    def test_employee_linked_shift_approver_cannot_approve_or_refuse_own_shift_day(self):
        self.employee.user_id = self.approver
        attendance = self._punch()
        day = attendance.sl_shift_day_id.with_user(self.approver)

        with self.assertRaises(AccessError):
            day.action_open_decision()
        with self.assertRaises(AccessError):
            day.action_approve(2, 'Self approval')
        with self.assertRaises(AccessError):
            day.action_refuse('Self refusal')

        self.assertEqual(day.state, 'pending')
        self.assertEqual(day.approved_overtime_hours, 0)
        self.assertFalse(day.approver_id)

    def test_original_punches_require_native_attendance_read_authority(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        view_id = self.env.ref('sl_employee_shift_attendance.view_shift_day_form').id

        restricted_arch = day.with_user(self.approver).get_views([(view_id, 'form')])['views']['form']['arch']
        officer_arch = day.with_user(self.officer).get_views([(view_id, 'form')])['views']['form']['arch']
        self.assertNotIn('Original Punches', restricted_arch)
        self.assertIn('Original Punches', officer_arch)

        with self.assertRaises(AccessError):
            day.with_user(self.approver).read(['attendance_ids'])
        self.assertTrue(day.with_user(self.officer).read(['attendance_ids'])[0]['attendance_ids'])

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
        self.assertEqual(attendance.sl_shift_day_id.approved_overtime_hours, 1)
        audit_count = len(day.audit_ids)
        day.with_user(self.approver).action_approve(1, 'One hour verified')
        self.assertEqual(len(day.audit_ids), audit_count)

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
        # A real empty calendar makes all elapsed time native daily overtime.
        # Only this synthetic employee is changed, never the company calendar.
        calendar = self.env['resource.calendar'].create({
            'name': 'Synthetic empty native daily calendar', 'tz': 'UTC',
            'attendance_ids': [Command.clear()],
        })
        self.employee.resource_calendar_id = calendar
        self.env.company.write({'hr_attendance_overtime': True, 'overtime_start_date': '2026-01-01'})

    def test_native_history_without_approval_provenance_blocks_adoption(self):
        self.assignment.attendance_policy = 'off'
        self._explicit_native_wrong_ruleset()
        attendance = self._punch()
        native = self.env['hr.attendance.overtime'].search([('employee_id', '=', self.employee.id), ('adjustment', '=', False)])
        self.assertTrue(native)
        self.assertEqual(native.duration, 11)
        preview = self.assignment.with_user(self.admin).action_repair_attendance()
        self.assertTrue(preview[0]['native_decision_blocks_repair'])
        with self.env.cr.savepoint():
            try:
                self.assignment.with_user(self.admin).write({'attendance_policy': 'shift'})
            except UserError:
                pass
            else:
                self.fail('Unknown native17 decision provenance was silently discarded')
            self.env.flush_all()
            self.env.cr.execute('SELECT attendance_policy FROM sl_shift_assignment WHERE id=%s', (self.assignment.id,))
            self.assertEqual(self.env.cr.fetchone()[0], 'off')
            self.assertEqual(native.exists().duration, 11)
            self.assertFalse(attendance.sl_shift_day_id)
            self.assertEqual(attendance.worked_hours, 11)

    def test_manual_native_adjustment_survives_explicit_history_repair(self):
        self.assignment.attendance_policy = 'off'
        attendance = self._punch()
        adjustment = self.env['hr.attendance.overtime'].create({
            'employee_id': self.employee.id, 'date': '2026-11-02',
            'duration': 3, 'duration_real': 3, 'adjustment': True,
        })
        self.assignment.with_user(self.admin).write({'attendance_policy': 'shift'})
        self.assignment.with_user(self.admin).action_repair_attendance(False, 'Explicit adoption preserving independent adjustment')
        self.assertEqual((attendance.worked_hours, attendance.sl_shift_day_id.raw_overtime_hours), (10, 2))
        self.assertTrue(adjustment.exists())
        self.assertEqual(adjustment.duration, 3)
        self.assertFalse(self.env['hr.attendance.overtime'].search([
            ('employee_id', '=', self.employee.id), ('adjustment', '=', False),
        ]))

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
        self.assertFalse(self.env['hr.attendance.overtime'].search([('employee_id', '=', self.employee.id), ('date', '=', friday.check_in.date()), ('adjustment', '=', False)]))

    def test_pre_shift_punch_is_not_carried_from_the_previous_shift_window(self):
        attendance = self._punch('2026-11-02 16:00:00', '2026-11-02 17:00:00')
        self.assertFalse(attendance.sl_shift_day_id)
        self.assertEqual(attendance.worked_hours, 1)

    def test_post_stop_punch_is_not_carried_from_the_previous_shift_window(self):
        attendance = self._punch('2026-11-03 04:00:00', '2026-11-03 05:00:00')
        self.assertFalse(attendance.sl_shift_day_id)
        self.assertEqual(attendance.worked_hours, 1)

    def test_overnight_carryover_inside_scheduled_window_is_retained(self):
        attendance = self._punch('2026-11-02 23:00:00', '2026-11-03 02:00:00')
        self.assertEqual(attendance.sl_shift_day_id.assignment_id, self.assignment)
        self.assertEqual(str(attendance.sl_shift_day_id.shift_date), '2026-11-02')
        self.assertEqual((attendance.worked_hours, attendance.sl_shift_day_id.presence_days), (3, 1))

    def test_adjacent_assignment_owns_punch_after_previous_shift_stops(self):
        self.assignment.write({'date_to': '2026-11-02'})
        next_shift = self.env['sl.shift'].create({
            'name': 'Synthetic adjacent 16-23', 'start_time': 16, 'end_time': 23,
        })
        next_assignment = self.env['sl.shift.assignment'].create({
            'employee_id': self.employee.id, 'shift_id': next_shift.id,
            'date_from': '2026-11-03', 'date_to': '2026-11-30',
            'attendance_policy': 'shift', 'schedule_tz': 'UTC',
            'workdays': '0,1,2,3,4,5,6',
        })
        attendance = self._punch('2026-11-03 16:00:00', '2026-11-03 17:00:00')
        self.assertEqual(attendance.sl_shift_day_id.assignment_id, next_assignment)
        self.assertEqual(str(attendance.sl_shift_day_id.shift_date), '2026-11-03')

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
        self.assertEqual((attendance.worked_hours, attendance.overtime_hours, attendance.sl_shift_day_id.presence_days), (8, 0, 1))

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
        for values in ({'worked_hours': 99}, {'overtime_status': 'approved'}, {'validated_overtime_hours': 99},
                       {'sl_shift_day_id': False}, {'linked_overtime_ids': [Command.clear()]}):
            with self.assertRaises(AccessError):
                attendance.with_user(self.admin).write(values)
        with self.assertRaises(AccessError):
            self.env['hr.attendance'].with_user(self.admin).with_context(default_worked_hours=99).create({
                'employee_id': self.employee.id, 'check_in': '2026-11-03 18:00:00', 'check_out': '2026-11-04 03:00:00'})
        with self.assertRaises(AccessError):
            self.env['hr.attendance.overtime'].with_user(self.admin).create({
                'employee_id': self.employee.id, 'date': '2026-11-02', 'duration': 11, 'duration_real': 11, 'adjustment': False})

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

    def test_hr_only_cannot_edit_metadata_of_opted_in_shift(self):
        hr_manager = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-hr-only-template-metadata@example.invalid',
            login='slshift-hr-only-template-metadata',
            groups='base.group_user,hr.group_hr_manager',
        )
        self.assertTrue(hr_manager.has_group('hr.group_hr_manager'))
        self.assertFalse(hr_manager.has_group('hr_attendance.group_hr_attendance_manager'))
        self.assertTrue(self.shift.with_user(hr_manager).check_access_rights('write', raise_exception=False))
        self.assertEqual(self.assignment.attendance_policy, 'shift')

        metadata_edits = (
            ('name', 'Synthetic renamed opted-in shift'),
            ('code', 'HR-ONLY-OPTED-SHIFT'),
            ('color', 7),
            ('active', False),
        )
        for field_name, value in metadata_edits:
            self.env.flush_all()
            self.env.cr.execute(
                'SELECT name, code, color, active FROM sl_shift WHERE id = %s',
                (self.shift.id,),
            )
            before = self.env.cr.fetchone()
            with self.env.cr.savepoint():
                try:
                    self.shift.with_user(hr_manager).write({field_name: value})
                except AccessError as error:
                    self.assertIn(
                        'Shift attendance configuration requires HR and Attendance administrator roles',
                        str(error),
                    )
                else:
                    self.fail('HR-only manager edited opted-in shift field %s' % field_name)
                self.env.flush_all()
                self.env.cr.execute(
                    'SELECT name, code, color, active FROM sl_shift WHERE id = %s',
                    (self.shift.id,),
                )
                self.assertEqual(self.env.cr.fetchone(), before,
                                 'Denied %s write changed the persisted shift' % field_name)

        # Archived opted-in assignments still reference their historical shift.
        self.assignment.active = False
        with self.env.cr.savepoint():
            try:
                self.shift.with_user(hr_manager).write({'color': 8})
            except AccessError:
                pass
            else:
                self.fail('HR-only manager edited a shift referenced by an archived opted-in assignment')

        self.assertTrue(self.admin.has_group('hr.group_hr_manager'))
        self.assertTrue(self.admin.has_group('hr_attendance.group_hr_attendance_manager'))
        dual_role_edits = (
            ('name', 'Synthetic dual-role opted-in shift'),
            ('code', 'DUAL-ROLE-OPTED-SHIFT'),
            ('color', 9),
            ('active', True),
        )
        for field_name, value in dual_role_edits:
            self.shift.with_user(self.admin).write({field_name: value})
            self.assertEqual(self.shift.with_user(self.admin)[field_name], value)

        unassigned_shift = self.env['sl.shift'].create({
            'name': 'Synthetic unassigned shift', 'code': 'UNASSIGNED-SHIFT',
            'color': 2, 'start_time': 8, 'end_time': 16,
        })
        unassigned_edits = (
            ('name', 'Synthetic edited unassigned shift'),
            ('code', 'UNASSIGNED-SHIFT-EDITED'),
            ('color', 5),
            ('active', False),
        )
        for field_name, value in unassigned_edits:
            unassigned_shift.with_user(hr_manager).write({field_name: value})
            self.assertEqual(unassigned_shift.with_user(hr_manager)[field_name], value)

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

    def test_native_daily_exclusion_preserves_unmanaged_rows_and_adjustments(self):
        self._explicit_native_wrong_ruleset()
        unmanaged = self._punch('2026-10-31 10:00:00', '2026-10-31 11:00:00')
        managed = self._punch()
        native = self.env['hr.attendance.overtime'].search([
            ('employee_id', '=', self.employee.id), ('adjustment', '=', False),
        ])
        self.assertEqual((str(native.date), native.duration), ('2026-10-31', 1))
        adjustment = self.env['hr.attendance.overtime'].create({
            'employee_id': self.employee.id, 'date': '2026-11-02',
            'duration': 3, 'duration_real': 3, 'adjustment': True,
        })
        (unmanaged | managed)._update_overtime()
        self.assertEqual((managed.worked_hours, managed.overtime_hours), (10, 2))
        self.assertEqual(native.duration, 1)
        self.assertEqual(adjustment.duration, 3)
        with self.assertRaises(AccessError):
            native.write({'date': '2026-11-02'})
        with self.assertRaises(AccessError):
            adjustment.write({'adjustment': False})
        with self.assertRaises(AccessError):
            self.env['hr.attendance.overtime'].with_context(
                default_employee_id=self.employee.id, default_date='2026-11-02',
                default_adjustment=False).create({'duration': 11, 'duration_real': 11})
        self.assertEqual(str(native.date), '2026-10-31')
        self.assertTrue(adjustment.adjustment)

    def test_caught_cross_company_attendance_reparent_is_atomic(self):
        attendance = self._punch()
        company = self.env['res.company'].create({'name': 'Synthetic Attendance Foreign'})
        foreign = self.env['hr.employee'].with_company(company).create({
            'name': 'Synthetic foreign destination', 'company_id': company.id,
        })
        actor = attendance.with_user(self.admin).with_context(allowed_company_ids=[self.env.company.id])
        with self.env.cr.savepoint():
            try:
                actor.write({'employee_id': foreign.id})
            except AccessError:
                pass
            else:
                self.fail('Foreign employee reparent accepted')
            self.env.flush_all()
            self.env.cr.execute('SELECT employee_id FROM hr_attendance WHERE id = %s', (attendance.id,))
            self.assertEqual(self.env.cr.fetchone()[0], self.employee.id)

    def test_foreign_summary_and_audit_reads_are_denied(self):
        day = self._punch().sl_shift_day_id
        other = self.env['res.company'].create({'name': 'Synthetic foreign viewer company'})
        foreign = new_test_user(self.env, login='slshift-foreign-viewer',
                                groups='base.group_user,hr.group_hr_user,sl_employee_shift_attendance.group_shift_approver',
                                company_id=other.id, company_ids=[Command.set([other.id])])
        with self.assertRaises(AccessError):
            day.with_user(foreign).with_context(allowed_company_ids=[other.id]).read(['net_hours'])
        with self.assertRaises(AccessError):
            day.audit_ids.with_user(foreign).with_context(allowed_company_ids=[other.id]).read(['reason'])

    def test_assigned_native_officer_without_private_hr_role_can_correct_managed_punch(self):
        actor = new_test_user(self.env, login='slshift-native-officer-only',
                              groups='base.group_user,hr_attendance.group_hr_attendance_officer')
        self.employee.attendance_manager_id = actor
        attendance = self._punch().with_user(actor)
        attendance.write({'check_out': '2026-11-03 04:00:00'})
        self.assertEqual((attendance.worked_hours, attendance.overtime_hours), (9, 1))
        self.assertFalse(actor.has_group('hr.group_hr_user'))

    def test_cross_company_reparenting_rejected(self):
        attendance = self._punch()
        company = self.env['res.company'].create({'name': 'Synthetic Foreign Company'})
        foreign_employee = self.env['hr.employee'].with_company(company).create({'name': 'Foreign Synthetic Employee', 'company_id': company.id})
        with self.assertRaises(AccessError):
            self.assignment.with_user(self.admin).with_context(allowed_company_ids=[self.env.company.id]).write({'employee_id': foreign_employee.id})
        self.assertEqual(self.assignment.employee_id, self.employee)
        with self.assertRaises(AccessError):
            attendance.sl_shift_day_id.with_user(self.approver).with_context(allowed_company_ids=[company.id]).action_approve(2, 'Foreign attempt')
