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
        cls.employee = cls.env['hr.employee'].create({'name': 'Synthetic Shift Integration', 'date_version': '2026-01-01'})
        cls.shift = cls.env['sl.shift'].create({'name': 'Synthetic 18-03', 'start_time': 18, 'end_time': 3, 'break_minutes': 60})
        cls.assignment = cls.env['sl.shift.assignment'].create({
            'employee_id': cls.employee.id, 'shift_id': cls.shift.id,
            'date_from': '2026-11-01', 'date_to': '2026-11-30', 'attendance_policy': 'shift',
            'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6', 'break_window_set': True, 'break_start': 22,
        })
        cls.approver = new_test_user(
            cls.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-shift-approver@example.invalid', login='slshift-approver',
            groups='base.group_user,hr.group_hr_user,sl_employee_shift_attendance.group_shift_approver')
        cls.officer = new_test_user(
            cls.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-shift-officer@example.invalid', login='slshift-officer',
            groups='base.group_user,hr.group_hr_user,hr_attendance.group_hr_attendance_user')
        cls.admin = new_test_user(
            cls.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-shift-config-admin@example.invalid', login='slshift-config-admin',
            groups='base.group_user,hr.group_hr_manager,hr_attendance.group_hr_attendance_manager,sl_employee_shift_attendance.group_shift_approver')

    def _punch(self, start='2026-11-02 18:00:00', stop='2026-11-03 05:00:00', **values):
        return self.env['hr.attendance'].create(dict(employee_id=self.employee.id, check_in=start, check_out=stop, **values))

    def test_summary_regular_raw_approved_presence_and_native_exclusion(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        self.assertTrue(day)
        self.assertEqual((day.elapsed_hours, day.net_hours, day.regular_hours, day.raw_overtime_hours,
                          day.approved_overtime_hours, day.presence_days), (11, 10, 8, 2, 0, 1))
        self.assertFalse(attendance.linked_overtime_ids)
        self.assertFalse(self.env['hr.attendance.overtime.line'].search([('employee_id', '=', self.employee.id)]))
        self.assertEqual(attendance.expected_hours, 8)

    def test_guarded_decision_wizard_works_for_restricted_approver(self):
        from odoo.tests import Form
        attendance = self._punch()
        self.assertFalse(
            self.approver.has_group('hr_attendance.group_hr_attendance_user'),
            'A shift approver must not inherit the native all-attendance role',
        )
        with self.assertRaises(AccessError):
            attendance.with_user(self.approver).check_access('read')
        day = attendance.sl_shift_day_id.with_user(self.approver)
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

    def test_module_update_removes_legacy_attendance_group_implication(self):
        approver_group = self.env.ref('sl_employee_shift_attendance.group_shift_approver')
        attendance_group = self.env.ref('hr_attendance.group_hr_attendance_user')
        approver_group.write({'implied_ids': [Command.link(attendance_group.id)]})
        self.assertIn(attendance_group, approver_group.implied_ids)

        from odoo.tools.convert import convert_file
        convert_file(
            self.env,
            'sl_employee_shift_attendance',
            'security/security.xml',
            {},
            mode='update',
        )
        approver_group.invalidate_recordset(['implied_ids'])
        self.assertNotIn(attendance_group, approver_group.implied_ids)

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
        self.assertEqual(attendance.validated_overtime_hours, 1)
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
        ruleset = self.env['hr.attendance.overtime.ruleset'].create({'name': 'Synthetic empty-schedule baseline',
                                                                   'company_id': self.env.company.id, 'rate_combination_mode': 'max'})
        empty_calendar = self.env['resource.calendar'].create({
            'name': 'Synthetic empty overtime calendar', 'tz': 'UTC',
            'attendance_ids': [Command.clear()],
        })
        self.env['hr.attendance.overtime.rule'].create({'name': 'Synthetic all elapsed is extra',
                                                       'ruleset_id': ruleset.id, 'base_off': 'timing',
                                                       'timing_type': 'schedule', 'resource_calendar_id': empty_calendar.id,
                                                       'employee_tolerance': 0, 'employer_tolerance': 0, 'paid': False})
        self.employee.version_ids.write({'ruleset_id': ruleset.id})

    def test_pending_native_history_is_reconciled_to_one_authoritative_engine(self):
        self.assignment.attendance_policy = 'off'
        self.env.company.attendance_overtime_validation = 'by_manager'
        self._explicit_native_wrong_ruleset()
        attendance = self._punch()
        native = self.env['hr.attendance.overtime.line'].search([('employee_id', '=', self.employee.id)])
        self.assertTrue(native)
        self.assertEqual(set(native.mapped('status')), {'to_approve'})
        self.assignment.with_user(self.admin).write({'attendance_policy': 'shift'})
        self.assignment.with_user(self.admin).action_repair_attendance(False, 'Explicit historical adoption')
        self.assertFalse(native.exists())
        day = attendance.sl_shift_day_id
        self.assertEqual((attendance.worked_hours, day.regular_hours, day.raw_overtime_hours, day.approved_overtime_hours), (10, 8, 2, 0))
        removed = day.audit_ids.filtered(lambda a: a.event == 'recomputed').evidence['removed_native_lines']
        self.assertTrue(removed)
        self.assertEqual(sum(v['duration'] for v in removed), 11)

    def test_decided_native_history_blocks_adoption_atomically(self):
        self.assignment.attendance_policy = 'off'
        self.env.company.attendance_overtime_validation = 'no_validation'
        self._explicit_native_wrong_ruleset()
        attendance = self._punch()
        native = self.env['hr.attendance.overtime.line'].search([('employee_id', '=', self.employee.id)])
        original_ids = native.ids
        self.assertEqual(set(native.mapped('status')), {'approved'})
        preview = self.assignment.with_user(self.admin).action_repair_attendance()
        self.assertTrue(preview[0]['native_decision_blocks_repair'])
        with self.env.cr.savepoint():
            try:
                self.assignment.with_user(self.admin).write({'attendance_policy': 'shift'})
            except UserError:
                pass
            else:
                self.fail('Decided native overtime was silently replaced')
            self.env.flush_all()
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
        self.assertFalse(self.env['hr.attendance.overtime.line'].search([('employee_id', '=', self.employee.id), ('time_start', '=', friday.check_in)]))

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
            self.env['hr.attendance.overtime.line'].with_user(self.admin).create({
                'employee_id': self.employee.id, 'date': '2026-11-02', 'time_start': attendance.check_in,
                'time_stop': attendance.check_out, 'duration': 11, 'status': 'approved'})

    def test_date_only_native_overtime_cannot_bypass_shift_approval(self):
        self._punch()
        officer = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-date-only-overtime-officer',
            groups='base.group_user,hr.group_hr_user,hr_attendance.group_hr_attendance_officer',
        )
        overtime = self.env['hr.attendance.overtime.line'].with_user(officer)
        self.employee.attendance_manager_id = officer
        with self.assertRaises(AccessError):
            overtime.create({
                'employee_id': self.employee.id, 'date': '2026-11-02',
                'duration': 2, 'manual_duration': 2, 'status': 'approved',
            })
        self.assertFalse(self.env['hr.attendance.overtime.line'].sudo().search([
            ('employee_id', '=', self.employee.id), ('date', '=', '2026-11-02'),
        ]))

        unmanaged = self.env['hr.employee'].create({'name': 'Unmanaged native overtime control'})
        unmanaged.attendance_manager_id = officer
        control = overtime.create({
            'employee_id': unmanaged.id, 'date': '2026-11-02',
            'duration': 2, 'manual_duration': 2, 'status': 'approved',
        })
        self.assertEqual(control.employee_id, unmanaged)
        before = control.read(['employee_id', 'date', 'duration', 'manual_duration', 'status'])
        with self.assertRaises(AccessError):
            control.write({'employee_id': self.employee.id})
        self.assertEqual(before, control.read(['employee_id', 'date', 'duration', 'manual_duration', 'status']))
        control.write({'duration': 3})
        self.assertEqual(control.duration, 3)

    def test_date_only_native_overtime_overlap_uses_native_and_schedule_timezones(self):
        """A Tokyo Saturday overtime date overlaps a UTC Friday night shift.

        The shift is Friday-only and ends at 03:00 UTC Saturday, while the
        native civil Saturday starts at 15:00 UTC Friday. Its assignment ends
        Friday and is archived, so checking only date equality/workdays misses
        this real interval overlap.
        """
        calendar = self.env['resource.calendar'].create({
            'name': 'Synthetic Tokyo native overtime calendar', 'tz': 'Asia/Tokyo',
        })
        employee = self.env['hr.employee'].create({
            'name': 'Tokyo native overtime employee', 'date_version': '2026-01-01',
            'resource_calendar_id': calendar.id,
        })
        self.assertEqual(employee._get_tz(), 'Asia/Tokyo')
        shift = self.env['sl.shift'].create({
            'name': 'UTC Friday night overtime guard', 'start_time': 18, 'end_time': 3,
        })
        assignment = self.env['sl.shift.assignment'].create({
            'employee_id': employee.id, 'shift_id': shift.id,
            'date_from': '2026-11-06', 'date_to': '2026-11-06',
            'schedule_tz': 'UTC', 'workdays': '4', 'attendance_policy': 'off',
        })
        native_officer = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-crossdate-native-officer',
            groups='base.group_user,hr.group_hr_user,hr_attendance.group_hr_attendance_officer',
        )
        self.env.company.attendance_overtime_validation = 'by_manager'
        employee.attendance_manager_id = native_officer
        overtime = self.env['hr.attendance.overtime.line'].with_user(native_officer)
        old_lines = overtime.create([
            {'employee_id': employee.id, 'date': '2026-11-07', 'duration': 1},
            {'employee_id': employee.id, 'date': '2026-11-07', 'duration': 1},
            {'employee_id': employee.id, 'date': '2026-11-07', 'duration': 1},
        ])
        proposed_line = overtime.create({
            'employee_id': employee.id, 'date': '2026-11-09', 'duration': 1,
        })
        self.assertFalse(any(old_lines.mapped('time_start')))
        self.assertEqual(set(old_lines.mapped('status')), {'to_approve'})

        assignment.with_user(self.admin).write({'attendance_policy': 'shift'})
        assignment.active = False

        # A genuinely unmanaged date on the same employee remains native.
        control = overtime.create({
            'employee_id': employee.id, 'date': '2026-11-09', 'duration': 2,
        })
        self.assertEqual(control.employee_id, employee)
        self.assertFalse(control.time_start)

        # Date-only create, old-row write/approval/unlink, and a proposed date
        # change must all consult the civil-day interval, not just its date.
        with self.assertRaises(AccessError):
            overtime.create({'employee_id': employee.id, 'date': '2026-11-07', 'duration': 2})
        with self.assertRaises(AccessError):
            old_lines[0].write({'duration': 2})
        with self.assertRaises(AccessError):
            old_lines[1].action_approve()
        with self.assertRaises(AccessError):
            old_lines[2].unlink()
        with self.assertRaises(AccessError):
            proposed_line.write({'date': '2026-11-07'})
        self.assertEqual(old_lines.exists().ids, old_lines.ids)
        self.assertEqual(str(proposed_line.date), '2026-11-09')

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
            start = datetime(2026, 11, 1, 18) + timedelta(days=index)  # noqa: DTZ001 - Odoo stores naive UTC.
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

    def test_hr_only_cannot_delete_archived_opted_assignment(self):
        hr_only = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-assignment-removal-hr-only@example.invalid',
            login='slshift-assignment-remove-hr-only',
            groups='base.group_user,hr.group_hr_manager',
        )
        employee = self.env['hr.employee'].create({
            'name': 'Synthetic archived opted assignment removal', 'date_version': '2026-01-01',
        })
        assignment = self.env['sl.shift.assignment'].create({
            'employee_id': employee.id, 'shift_id': self.shift.id,
            'date_from': '2026-11-10', 'attendance_policy': 'shift',
            'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6',
            'break_window_set': True, 'break_start': 22,
        })
        assignment.active = False
        restricted = assignment.with_user(hr_only).with_context(active_test=False)
        restricted.check_access('unlink')

        with self.env.cr.savepoint():
            caught = None
            try:
                restricted.unlink()
            except AccessError as error:
                caught = error
            self.assertIsNotNone(caught, 'HR-only deletion bypassed dual-role authorization')
            self.assertIn(
                'Shift attendance configuration requires HR and Attendance administrator roles',
                str(caught),
            )
            self.env.flush_all()
            self.env.cr.execute(
                'SELECT attendance_policy, active FROM sl_shift_assignment WHERE id = %s',
                (assignment.id,),
            )
            self.assertEqual(self.env.cr.fetchone(), ('shift', False))

        # The dual-role owner can remove an opted-in assignment with no history.
        self.assignment.with_user(self.admin).unlink()

    def test_hr_only_employee_delete_cannot_cascade_archived_opted_assignment(self):
        hr_only = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-employee-removal-hr-only@example.invalid',
            login='slshift-employee-remove-hr-only',
            groups='base.group_user,hr.group_hr_manager',
        )
        employee = self.env['hr.employee'].create({
            'name': 'Synthetic employee cascade removal', 'date_version': '2026-01-01',
        })
        assignment = self.env['sl.shift.assignment'].create({
            'employee_id': employee.id, 'shift_id': self.shift.id,
            'date_from': '2026-11-11', 'attendance_policy': 'shift',
            'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6',
            'break_window_set': True, 'break_start': 22,
        })
        assignment.active = False
        restricted = employee.with_user(hr_only)
        restricted.check_access('unlink')

        with self.env.cr.savepoint():
            caught = None
            try:
                restricted.unlink()
            except AccessError as error:
                caught = error
            self.assertIsNotNone(caught, 'Employee deletion cascaded around assignment authorization')
            self.assertIn(
                'Shift attendance configuration requires HR and Attendance administrator roles',
                str(caught),
            )
            self.env.flush_all()
            self.env.cr.execute('SELECT id FROM hr_employee WHERE id = %s', (employee.id,))
            self.assertEqual(self.env.cr.fetchone(), (employee.id,))
            self.env.cr.execute(
                'SELECT attendance_policy, active FROM sl_shift_assignment WHERE id = %s',
                (assignment.id,),
            )
            self.assertEqual(self.env.cr.fetchone(), ('shift', False))

        # Employee removal remains available to the dual-role HR/Attendance admin.
        approved_employee = self.env['hr.employee'].create({
            'name': 'Synthetic authorized employee cascade removal', 'date_version': '2026-01-01',
        })
        self.env['sl.shift.assignment'].create({
            'employee_id': approved_employee.id, 'shift_id': self.shift.id,
            'date_from': '2026-11-12', 'attendance_policy': 'shift',
            'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6',
            'break_window_set': True, 'break_start': 22, 'active': False,
        })
        approved_employee.with_user(self.admin).unlink()
        self.assertFalse(approved_employee.exists())

    def test_employee_delete_preserves_assignment_history_guard(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        assignment = day.assignment_id
        employee = self.employee.with_user(self.admin)
        employee.check_access('unlink')

        with self.env.cr.savepoint():
            caught = None
            try:
                employee.unlink()
            except UserError as error:
                caught = error
            self.assertIsNotNone(caught, 'Employee deletion bypassed the assignment history guard')
            self.assertIn('Historical assignments with shift evidence cannot be deleted', str(caught))
            self.env.flush_all()
            self.env.cr.execute('SELECT id FROM hr_employee WHERE id = %s', (self.employee.id,))
            self.assertEqual(self.env.cr.fetchone(), (self.employee.id,))
            self.env.cr.execute('SELECT id FROM sl_shift_assignment WHERE id = %s', (assignment.id,))
            self.assertEqual(self.env.cr.fetchone(), (assignment.id,))
            self.env.cr.execute('SELECT id FROM sl_shift_day WHERE id = %s', (day.id,))
            self.assertEqual(self.env.cr.fetchone(), (day.id,))

    def test_employee_company_is_frozen_with_attendance_only_evidence(self):
        self._punch()
        company = self.env['res.company'].create({'name': 'Synthetic Company Move'})
        with self.assertRaises(UserError):
            self.employee.with_user(self.admin).with_context(allowed_company_ids=[self.env.company.id, company.id]).write({'company_id': company.id})
        self.assertEqual(self.employee.company_id, self.env.company)

    def test_hr_only_cannot_reclassify_employee_with_opted_in_assignment(self):
        destination = self.env['res.company'].create({'name': 'Synthetic HR-only Destination'})
        hr_only = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-company-reclass-hr-only@example.invalid',
            login='slshift-company-reclass-hr-only',
            groups='base.group_user,hr.group_hr_manager',
        )
        hr_only.write({'company_ids': [Command.link(destination.id)]})
        employee = self.env['hr.employee'].create({
            'name': 'Synthetic HR-only company reclassification', 'date_version': '2026-01-01',
        })
        assignment = self.env['sl.shift.assignment'].create({
            'employee_id': employee.id, 'shift_id': self.shift.id,
            'date_from': '2026-11-10', 'attendance_policy': 'shift',
            'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6',
            'break_window_set': True, 'break_start': 22,
        })

        with self.assertRaisesRegex(
                AccessError,
                'Shift attendance configuration requires HR and Attendance administrator roles'):
            employee.with_user(hr_only).with_context(
                allowed_company_ids=[self.env.company.id, destination.id],
            ).write({'company_id': destination.id})

        self.assertEqual(employee.company_id, self.env.company)
        self.assertEqual(assignment.company_id, self.env.company)

    def test_dual_role_can_reclassify_opted_employee_to_authorized_destination(self):
        destination = self.env['res.company'].create({'name': 'Synthetic Authorized Destination'})
        self.admin.write({'company_ids': [Command.link(destination.id)]})
        employee = self.env['hr.employee'].create({
            'name': 'Synthetic authorized company reclassification', 'date_version': '2026-01-01',
        })
        assignment = self.env['sl.shift.assignment'].create({
            'employee_id': employee.id, 'shift_id': self.shift.id,
            'date_from': '2026-11-10', 'attendance_policy': 'shift',
            'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6',
            'break_window_set': True, 'break_start': 22,
        })
        self.env.flush_all()
        self.env.cr.execute(
            'SELECT generation FROM sl_shift_template_guard WHERE shift_id = %s',
            (self.shift.id,),
        )
        generation_before = self.env.cr.fetchone()[0]

        employee.with_user(self.admin).with_context(
            allowed_company_ids=[self.env.company.id, destination.id],
        ).write({'company_id': destination.id})

        self.env.flush_all()
        self.assertEqual(employee.company_id, destination)
        self.assertEqual(assignment.company_id, destination)
        self.env.cr.execute(
            'SELECT generation FROM sl_shift_template_guard WHERE shift_id = %s',
            (self.shift.id,),
        )
        self.assertGreater(self.env.cr.fetchone()[0], generation_before)

    def test_opted_employee_reclassification_rejects_unauthorized_destination(self):
        destination = self.env['res.company'].create({'name': 'Synthetic Unauthorized Destination'})
        employee = self.env['hr.employee'].create({
            'name': 'Synthetic unauthorized company reclassification', 'date_version': '2026-01-01',
        })
        assignment = self.env['sl.shift.assignment'].create({
            'employee_id': employee.id, 'shift_id': self.shift.id,
            'date_from': '2026-11-10', 'attendance_policy': 'shift',
            'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6',
            'break_window_set': True, 'break_start': 22,
        })

        with self.assertRaisesRegex(AccessError, 'destination company is not enabled'):
            employee.with_user(self.admin).with_context(
                allowed_company_ids=[self.env.company.id],
            ).write({'company_id': destination.id})

        self.assertEqual(employee.company_id, self.env.company)
        self.assertEqual(assignment.company_id, self.env.company)

    def test_archived_opted_assignment_without_summary_keeps_company_reclassification_atomic(self):
        destination = self.env['res.company'].create({'name': 'Synthetic Archived Unauthorized Destination'})
        employee = self.env['hr.employee'].create({
            'name': 'Synthetic archived company reclassification', 'date_version': '2026-01-01',
        })
        assignment = self.env['sl.shift.assignment'].create({
            'employee_id': employee.id, 'shift_id': self.shift.id,
            'date_from': '2026-11-10', 'attendance_policy': 'shift',
            'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6',
            'break_window_set': True, 'break_start': 22, 'active': False,
        })
        self.assertFalse(self.env['sl.shift.day'].sudo().search([('assignment_id', '=', assignment.id)]))

        with self.env.cr.savepoint():
            caught = None
            try:
                employee.with_user(self.admin).with_context(
                    allowed_company_ids=[self.env.company.id],
                ).write({'company_id': destination.id})
            except AccessError as error:
                caught = error
            self.assertIsNotNone(caught, 'Unauthorized destination reclassified an archived opted-in employee')
            self.env.flush_all()
            self.env.cr.execute('SELECT company_id FROM hr_employee WHERE id = %s', (employee.id,))
            self.assertEqual(self.env.cr.fetchone(), (self.env.company.id,))
            self.env.cr.execute(
                'SELECT company_id, active, attendance_policy FROM sl_shift_assignment WHERE id = %s',
                (assignment.id,),
            )
            self.assertEqual(self.env.cr.fetchone(), (self.env.company.id, False, 'shift'))

    def test_assignment_employee_is_not_reparented_after_history_exists(self):
        attendance = self._punch()
        other = self.env['hr.employee'].create({'name': 'Synthetic same-company target'})
        with self.assertRaises(UserError):
            self.assignment.with_user(self.admin).write({'employee_id': other.id})
        self.assertEqual(attendance.sl_shift_day_id.employee_id, self.employee)
        self.assertEqual(self.assignment.employee_id, self.employee)

    def test_open_attendance_cannot_be_reparented_outside_enabled_companies(self):
        attendance = self._punch(stop=False)
        day = attendance.sl_shift_day_id
        company = self.env['res.company'].create({'name': 'Synthetic Open Attendance Foreign Company'})
        foreign_employee = self.env['hr.employee'].sudo().with_company(company).create({
            'name': 'Foreign Open Attendance Target', 'company_id': company.id,
        })
        before = (attendance.employee_id.id, day.digest, day.state, day.net_hours, day.audit_ids.ids)
        restricted = attendance.with_user(self.admin).with_context(allowed_company_ids=[self.env.company.id])
        with self.assertRaises(AccessError):
            restricted.write({'employee_id': foreign_employee.id})
        self.assertEqual(before, (attendance.employee_id.id, day.digest, day.state, day.net_hours, day.audit_ids.ids))

        same_company = self.env['hr.employee'].create({'name': 'Same-company attendance target'})
        control = self.env['hr.attendance'].create({
            'employee_id': self.employee.id, 'check_in': '2026-11-05 18:00:00',
            'check_out': '2026-11-05 19:00:00',
        })
        control.with_user(self.admin).write({'employee_id': same_company.id})
        self.assertEqual(control.employee_id, same_company)

    def test_cross_company_reparenting_rejected(self):
        attendance = self._punch()
        company = self.env['res.company'].create({'name': 'Synthetic Foreign Company'})
        foreign_employee = self.env['hr.employee'].with_company(company).create({'name': 'Foreign Synthetic Employee', 'company_id': company.id})
        with self.assertRaises(AccessError):
            self.assignment.with_user(self.admin).with_context(allowed_company_ids=[self.env.company.id]).write({'employee_id': foreign_employee.id})
        self.assertEqual(self.assignment.employee_id, self.employee)
        with self.assertRaises(AccessError):
            attendance.sl_shift_day_id.with_user(self.approver).with_context(allowed_company_ids=[company.id]).action_approve(2, 'Foreign attempt')

    def test_foreign_company_employee_cannot_create_managed_attendance(self):
        company = self.env['res.company'].create({'name': 'Synthetic Isolated Attendance Company'})
        employee = self.env['hr.employee'].sudo().with_company(company).create({
            'name': 'Foreign Managed Employee', 'company_id': company.id,
        })
        self.env['sl.shift.assignment'].sudo().with_company(company).create({
            'employee_id': employee.id, 'shift_id': self.shift.id,
            'date_from': '2026-11-01', 'date_to': '2026-11-30', 'attendance_policy': 'shift',
            'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6',
            'break_window_set': True, 'break_start': 22,
        })
        foreign_values = {'employee_id': employee.id, 'check_in': '2026-11-02 18:00:00',
                          'check_out': '2026-11-03 05:00:00'}
        restricted_attendance = self.env['hr.attendance'].with_user(self.officer).with_context(
            allowed_company_ids=[self.env.company.id])
        with self.assertRaises(AccessError):
            restricted_attendance.create(foreign_values)
        self.assertFalse(self.env['hr.attendance'].sudo().search([('employee_id', '=', employee.id)]))
        self.assertFalse(self.env['sl.shift.day'].sudo().search([('employee_id', '=', employee.id)]))

    def test_assignment_schedule_cannot_rewrite_existing_shift_evidence(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        before = (self.assignment.break_start, day.digest, day.state, day.net_hours)
        with self.assertRaises(UserError):
            self.assignment.with_user(self.admin).write({'break_start': 23})
        self.assertEqual(before, (self.assignment.break_start, day.digest, day.state, day.net_hours))

    def test_assignment_date_range_cannot_exclude_existing_shift_evidence(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        with self.assertRaises(UserError):
            self.assignment.with_user(self.admin).write({'date_to': '2026-11-01'})
        self.assertEqual(day.assignment_id, self.assignment)
        self.assertEqual((day.state, day.net_hours, attendance.sl_shift_day_id), ('pending', 10, day))
        self.assignment.with_user(self.admin).write({'date_to': '2026-11-10'})
        future = self.env['sl.shift.assignment'].with_user(self.admin).create({
            'employee_id': self.employee.id, 'shift_id': self.shift.id,
            'date_from': '2026-11-11', 'date_to': '2026-11-30',
        })
        self.assertEqual((str(self.assignment.date_to), str(future.date_from)), ('2026-11-10', '2026-11-11'))

    def test_out_of_window_punch_is_not_assigned_to_a_neighboring_shift(self):
        outside = self._punch('2026-11-02 17:00:00', '2026-11-02 17:30:00')
        self.assertFalse(outside.sl_shift_day_id, 'A pre-shift punch must not attach to the prior shift')
        after = self._punch('2026-11-03 03:00:00', '2026-11-03 04:00:00')
        self.assertFalse(after.sl_shift_day_id, 'A post-shift punch must not attach to the ended shift')

    def test_opted_template_metadata_writes_require_both_administrator_roles(self):
        hr_only = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-template-hr-only@example.invalid',
            login='slshift-template-hr-only',
            groups='base.group_user,hr.group_hr_manager',
        )
        self.assertTrue(hr_only.has_group('hr.group_hr_manager'))
        self.assertFalse(hr_only.has_group('hr_attendance.group_hr_attendance_manager'))

        employee = self.env['hr.employee'].create({
            'name': 'Synthetic template metadata owner', 'date_version': '2026-01-01',
        })
        template = self.env['sl.shift'].create({
            'name': 'Synthetic opted metadata base', 'code': 'META-AUTH-BASE',
            'color': 1, 'start_time': 9, 'end_time': 17,
        })
        assignment = self.env['sl.shift.assignment'].create({
            'employee_id': employee.id, 'shift_id': template.id,
            'date_from': '2026-11-09', 'attendance_policy': 'shift',
            'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6',
        })
        self.assertEqual(assignment.attendance_policy, 'shift')
        self.assertTrue(template.with_user(hr_only).has_access('write'),
                        'The native HR Manager ACL permits shift writes')

        metadata_edits = (
            ('name', 'Synthetic renamed opted metadata template'),
            ('code', 'META-AUTH-EDITED'),
            ('color', 7),
            ('active', False),
        )
        for field_name, value in metadata_edits:
            self.env.flush_all()
            self.env.cr.execute(
                'SELECT name, code, color, active FROM sl_shift WHERE id = %s',
                (template.id,),
            )
            before = self.env.cr.fetchone()
            with self.env.cr.savepoint():
                try:
                    template.with_user(hr_only).write({field_name: value})
                except AccessError as error:
                    self.assertIn('Shift attendance configuration requires HR and Attendance administrator roles', str(error))
                else:
                    self.fail(f'HR-only manager edited opted-in template field {field_name}')
                self.env.flush_all()
                self.env.cr.execute(
                    'SELECT name, code, color, active FROM sl_shift WHERE id = %s',
                    (template.id,),
                )
                self.assertEqual(self.env.cr.fetchone(), before,
                                 f'Denied {field_name} write changed the persisted template')

        self.assertTrue(self.admin.has_group('hr.group_hr_manager'))
        self.assertTrue(self.admin.has_group('hr_attendance.group_hr_attendance_manager'))
        dual_role_edits = (
            ('name', 'Synthetic dual-role opted metadata template'),
            ('code', 'META-AUTH-DUAL'),
            ('color', 8),
            ('active', False),
        )
        for field_name, value in dual_role_edits:
            template.with_user(self.admin).write({field_name: value})
            self.assertEqual(template.with_user(self.admin)[field_name], value)

        unassigned = self.env['sl.shift'].create({
            'name': 'Synthetic unassigned metadata base', 'code': 'META-AUTH-UNASSIGNED',
            'color': 2, 'start_time': 8, 'end_time': 16,
        })
        unassigned_edits = (
            ('name', 'Synthetic edited unassigned metadata template'),
            ('code', 'META-AUTH-UNASSIGNED-EDITED'),
            ('color', 5),
            ('active', False),
        )
        for field_name, value in unassigned_edits:
            unassigned.with_user(hr_only).write({field_name: value})
            self.assertEqual(unassigned.with_user(hr_only)[field_name], value)
