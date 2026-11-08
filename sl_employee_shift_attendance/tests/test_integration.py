# SPDX-License-Identifier: LGPL-3.0-or-later
from datetime import datetime, timedelta

from odoo import SUPERUSER_ID, api, registry
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import BaseCase, TransactionCase, tagged
from odoo.tests.common import get_db_name, new_test_user


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
        cls.approver = new_test_user(cls.env['res.users'].with_context(no_reset_password=True).env, email='synthetic-shift@example.invalid', login='slshift-approver',
                                    groups='base.group_user,hr.group_hr_user,sl_employee_shift_attendance.group_shift_approver')
        cls.officer = new_test_user(cls.env['res.users'].with_context(no_reset_password=True).env, email='synthetic-shift@example.invalid', login='slshift-officer',
                                   groups='base.group_user,hr.group_hr_user,hr_attendance.group_hr_attendance_user')
        cls.admin = new_test_user(cls.env['res.users'].with_context(no_reset_password=True).env, email='synthetic-shift@example.invalid', login='slshift-config-admin',
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
        self.assertNotIn('overtime_status', attendance._fields)  # native16 has no approval state

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
        empty = self.env['resource.calendar'].create({'name': 'Synthetic empty native16 calendar', 'tz': 'UTC',
                                                     'attendance_ids': [(5, 0, 0)]})
        self.employee.resource_calendar_id = empty
        self.employee.resource_id.tz = 'UTC'

    def test_pending_native_history_is_reconciled_to_one_authoritative_engine(self):
        self.assignment.attendance_policy = 'off'
        self._explicit_native_wrong_ruleset()
        attendance = self._punch()
        native = self.env['hr.attendance.overtime'].search([('employee_id', '=', self.employee.id), ('adjustment', '=', False)])
        self.assertTrue(native)
        adjustment = self.env['hr.attendance.overtime'].create({'employee_id': self.employee.id, 'date': '2026-11-02', 'adjustment': True, 'duration': 0.5})
        self.assignment.with_user(self.admin).write({'attendance_policy': 'shift'})
        self.assignment.with_user(self.admin).action_repair_attendance(False, 'Explicit historical adoption')
        self.assertFalse(native.exists())
        self.assertEqual(adjustment.duration, 0.5)
        day = attendance.sl_shift_day_id
        self.assertEqual((attendance.worked_hours, day.regular_hours, day.raw_overtime_hours, day.approved_overtime_hours), (10, 8, 2, 0))
        removed = day.audit_ids.filtered(lambda a: a.event == 'recomputed').evidence['removed_native_lines']
        self.assertTrue(removed)
        self.assertEqual(sum(v['duration'] for v in removed), 11)

    def test_native16_engine_excludes_managed_employee_days_not_adjustments_or_unrelated_days(self):
        self._explicit_native_wrong_ruleset()
        managed = self._punch()
        self.assertTrue(managed.sl_shift_day_id)
        self.assertFalse(self.env['hr.attendance.overtime'].search([('employee_id', '=', self.employee.id)]))
        adjustment = self.env['hr.attendance.overtime'].create({'employee_id': self.employee.id, 'date': '2026-11-02', 'duration': 0.5, 'adjustment': True})
        adjustment.duration = 0.75
        self.assertEqual(adjustment.duration, 0.75)
        with self.assertRaises(AccessError):
            adjustment.write({'adjustment': False})
        other = self.env['hr.employee'].create({'name': 'Native16 unrelated', 'resource_calendar_id': self.employee.resource_calendar_id.id})
        self.env['hr.attendance'].create({'employee_id': other.id, 'check_in': '2026-11-02 18:00:00', 'check_out': '2026-11-03 03:00:00'})
        native = self.env['hr.attendance.overtime'].search([('employee_id', '=', other.id), ('adjustment', '=', False)])
        self.assertEqual(sum(native.mapped('duration')), 9)
        before = self.env['hr.attendance'].create({'employee_id': self.employee.id, 'check_in': '2026-10-31 18:00:00', 'check_out': '2026-11-01 03:00:00'})
        self.assertEqual(before.worked_hours, 9)
        native = self.env['hr.attendance.overtime'].search([('employee_id', '=', self.employee.id), ('date', '=', '2026-10-31'), ('adjustment', '=', False)])
        self.assertEqual(sum(native.mapped('duration')), 9)

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
        self.assertFalse(self.env['hr.attendance.overtime'].search([('employee_id', '=', self.employee.id), ('date', '=', friday.check_in.date())]))

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
        for values in ({'worked_hours': 99}, {'sl_raw_overtime_hours': 99}, {'sl_approved_overtime_hours': 99}, {'sl_shift_day_id': False}):
            with self.assertRaises(AccessError):
                attendance.with_user(self.admin).write(values)
        with self.assertRaises(AccessError):
            self.env['hr.attendance'].with_user(self.admin).with_context(default_worked_hours=99).create({
                'employee_id': self.employee.id, 'check_in': '2026-11-03 18:00:00', 'check_out': '2026-11-04 03:00:00'})
        with self.assertRaises(AccessError):
            self.env['hr.attendance.overtime'].with_user(self.admin).create({
                'employee_id': self.employee.id, 'date': '2026-11-02', 'duration': 11})

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

    def test_disabled_policy_does_not_unfreeze_historical_shift_template(self):
        day = self._punch().sl_shift_day_id
        self.assignment.with_user(self.admin).write({'attendance_policy': 'off'})
        self.assertTrue(day.exists(), 'Opting out must retain the historical summary row')
        self.env.flush_all()
        self.env.cr.execute('SELECT row_to_json(s) FROM sl_shift s WHERE id = %s', (self.shift.id,))
        shift_before = self.env.cr.fetchone()[0]
        self.env.cr.execute('SELECT row_to_json(d) FROM sl_shift_day d WHERE id = %s', (day.id,))
        day_before = self.env.cr.fetchone()[0]
        with self.env.cr.savepoint():
            try:
                self.shift.with_user(self.admin).write({'start_time': 19})
            except UserError:
                pass
            else:
                self.fail('A shift template with historical evidence was edited while policy was disabled')
            self.env.flush_all()
            self.env.cr.execute('SELECT row_to_json(s) FROM sl_shift s WHERE id = %s', (self.shift.id,))
            self.assertEqual(self.env.cr.fetchone()[0], shift_before)
            self.env.cr.execute('SELECT row_to_json(d) FROM sl_shift_day d WHERE id = %s', (day.id,))
            self.assertEqual(self.env.cr.fetchone()[0], day_before)

    def test_disabled_policy_does_not_unfreeze_historical_assignment(self):
        day = self._punch().sl_shift_day_id
        self.assignment.with_user(self.admin).write({'attendance_policy': 'off'})
        self.assertTrue(day.exists(), 'Opting out must retain the historical summary row')
        self.env.flush_all()
        self.env.cr.execute('SELECT row_to_json(a) FROM sl_shift_assignment a WHERE id = %s',
                            (self.assignment.id,))
        assignment_before = self.env.cr.fetchone()[0]
        self.env.cr.execute('SELECT row_to_json(d) FROM sl_shift_day d WHERE id = %s', (day.id,))
        day_before = self.env.cr.fetchone()[0]
        with self.env.cr.savepoint():
            try:
                self.assignment.with_user(self.admin).write({'date_from': '2026-11-02'})
            except UserError:
                pass
            else:
                self.fail('A disabled assignment with historical shift evidence was edited')
            self.env.flush_all()
            self.env.cr.execute('SELECT row_to_json(a) FROM sl_shift_assignment a WHERE id = %s',
                                (self.assignment.id,))
            self.assertEqual(self.env.cr.fetchone()[0], assignment_before)
            self.env.cr.execute('SELECT row_to_json(d) FROM sl_shift_day d WHERE id = %s', (day.id,))
            self.assertEqual(self.env.cr.fetchone()[0], day_before)

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
            self.env.flush_all()
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


    def test_opted_template_requires_hr_and_attendance_admin_before_first_punch(self):
        hr_manager = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-hr-only@example.invalid', login='slshift-hr-only-template',
            groups='base.group_user,hr.group_hr_manager',
        )
        employee = self.env['hr.employee'].create({'name': 'Synthetic opted template owner'})
        template = self.env['sl.shift'].create({
            'name': 'Synthetic opted template authorization', 'start_time': 9, 'end_time': 17,
        })
        assignment = self.env['sl.shift.assignment'].create({
            'employee_id': employee.id, 'shift_id': template.id,
            'date_from': '2026-11-09', 'attendance_policy': 'shift',
            'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6',
        })
        self.assertEqual(assignment.attendance_policy, 'shift')
        self.assertFalse(self.env['hr.attendance'].search([('employee_id', '=', employee.id)]))

        self.env.flush_all()
        self.env.cr.execute('SELECT start_time FROM sl_shift WHERE id = %s', (template.id,))
        before = self.env.cr.fetchone()[0]
        with self.env.cr.savepoint():
            try:
                template.with_user(hr_manager).write({'start_time': 10})
            except AccessError:
                pass
            else:
                self.fail('An HR-only manager edited an opted-in template before its first punch')
            self.env.flush_all()
            self.env.cr.execute('SELECT start_time FROM sl_shift WHERE id = %s', (template.id,))
            self.assertEqual(self.env.cr.fetchone()[0], before)

        template.with_user(self.admin).write({'start_time': 11})
        self.assertEqual(template.start_time, 11,
                         'HR plus Attendance Administrator remains a valid editor')

        unassigned_template = self.env['sl.shift'].create({
            'name': 'Synthetic unassigned template authorization', 'start_time': 8, 'end_time': 16,
        })
        unassigned_template.with_user(hr_manager).write({'start_time': 9})
        self.assertEqual(unassigned_template.start_time, 9,
                         'An HR-only manager may edit an unassigned template')

    def test_opted_template_metadata_writes_require_both_administrator_roles(self):
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
            'date_from': '2026-11-09', 'attendance_policy': 'shift',
            'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6',
        })
        self.assertEqual(assignment.attendance_policy, 'shift')
        self.assertFalse(self.env['hr.attendance'].search([('employee_id', '=', employee.id)]))
        self.assertTrue(template.with_user(hr_manager).check_access_rights('write', raise_exception=False),
                        'Native HR Manager ACL grants shift write access')

        metadata_edits = (
            ('name', 'Synthetic renamed opted template'),
            ('code', 'META-RENAMED'),
            ('color', 7),
            ('active', False),
        )
        for field_name, value in metadata_edits:
            self.env.cr.execute(
                'SELECT name, code, color, active FROM sl_shift WHERE id = %s',
                (template.id,),
            )
            before = self.env.cr.fetchone()
            with self.env.cr.savepoint():
                try:
                    template.with_user(hr_manager).write({field_name: value})
                except AccessError as error:
                    self.assertIn('Shift attendance configuration requires HR and Attendance administrator roles', str(error))
                else:
                    self.fail('HR-only manager edited opted-in template field %s' % field_name)
                self.env.flush_all()
                self.env.cr.execute(
                    'SELECT name, code, color, active FROM sl_shift WHERE id = %s',
                    (template.id,),
                )
                self.assertEqual(self.env.cr.fetchone(), before,
                                 'Denied %s write changed the persisted template' % field_name)

        self.assertTrue(self.admin.has_group('hr.group_hr_manager'))
        self.assertTrue(self.admin.has_group('hr_attendance.group_hr_attendance_manager'))
        dual_role_edits = (
            ('name', 'Synthetic dual-role opted template'),
            ('code', 'META-DUAL'),
            ('color', 8),
            ('active', True),
        )
        for field_name, value in dual_role_edits:
            template.with_user(self.admin).write({field_name: value})
            self.assertEqual(template.with_user(self.admin)[field_name], value)

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


@tagged('post_install', '-at_install')
class TestShiftTemplateHistoryRace(BaseCase):
    """Exercise template/punch serialization on independent PostgreSQL transactions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.registry = registry(get_db_name())

    def test_template_write_races_with_managed_punch_without_stale_summary(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor

        import psycopg2

        employees = []
        shifts = []
        assignments = []
        try:
            with self.registry.cursor() as setup_cr:
                api.Transaction(self.registry)
                setup_env = api.Environment(setup_cr, SUPERUSER_ID, {})
                employee = setup_env['hr.employee'].create({'name': 'Synthetic template race employee'})
                control_employee = setup_env['hr.employee'].create({'name': 'Synthetic template control employee'})
                shift = setup_env['sl.shift'].create({
                    'name': 'Synthetic template race shift', 'start_time': 9, 'end_time': 17,
                })
                control_shift = setup_env['sl.shift'].create({
                    'name': 'Synthetic template edit control', 'start_time': 8, 'end_time': 16,
                })
                assignment_values = {
                    'date_from': '2026-11-01', 'date_to': '2026-11-30',
                    'attendance_policy': 'shift', 'schedule_tz': 'UTC',
                    'workdays': '0,1,2,3,4,5,6',
                }
                assignment = setup_env['sl.shift.assignment'].create(dict(
                    assignment_values, employee_id=employee.id, shift_id=shift.id,
                ))
                control_assignment = setup_env['sl.shift.assignment'].create(dict(
                    assignment_values, employee_id=control_employee.id, shift_id=control_shift.id,
                ))
                employees = [employee.id, control_employee.id]
                shifts = [shift.id, control_shift.id]
                assignments = [assignment.id, control_assignment.id]
                setup_cr.commit()

            # A legitimate nonconcurrent edit remains allowed when an assigned
            # template has no attendance evidence.
            with self.registry.cursor() as control_cr:
                api.Transaction(self.registry)
                control_env = api.Environment(control_cr, SUPERUSER_ID, {})
                control_env['sl.shift'].browse(shifts[1]).write({'start_time': 10})
                control_cr.commit()
            with self.registry.cursor() as verify_control_cr:
                api.Transaction(self.registry)
                verify_control_env = api.Environment(verify_control_cr, SUPERUSER_ID, {})
                self.assertEqual(verify_control_env['sl.shift'].browse(shifts[1]).start_time, 10)
                self.assertFalse(verify_control_env['sl.shift.day'].sudo().search([
                    ('assignment_id', '=', assignments[1]),
                ]))

            barrier = threading.Barrier(2, timeout=5)
            punch_finished = threading.Event()
            punch_committed = threading.Event()

            def arm_transaction(cr):
                cr.execute("SET LOCAL lock_timeout = '3000ms'")
                cr.execute("SET LOCAL statement_timeout = '10000ms'")

            def take_snapshot(cr, env):
                cr.execute('SHOW transaction_isolation')
                isolation = cr.fetchone()[0]
                shift_row = env['sl.shift'].browse(shifts[0]).read(
                    ['start_time', 'end_time', 'break_minutes'])[0]
                assignment_row = env['sl.shift.assignment'].browse(assignments[0]).read(
                    ['employee_id', 'shift_id', 'attendance_policy'])[0]
                history_count = env['sl.shift.day'].sudo().search_count([
                    ('assignment_id', '=', assignments[0]),
                ])
                return isolation, shift_row, assignment_row, history_count

            def create_managed_punch():
                try:
                    with self.registry.cursor() as punch_cr:
                        api.Transaction(self.registry)
                        arm_transaction(punch_cr)
                        punch_env = api.Environment(punch_cr, SUPERUSER_ID, {})
                        snapshot = take_snapshot(punch_cr, punch_env)
                        barrier.wait()
                        attendance = punch_env['hr.attendance'].create({
                            'employee_id': employees[0],
                            'check_in': '2026-11-09 09:00:00',
                            'check_out': '2026-11-09 18:00:00',
                        })
                        attendance_id = attendance.id
                        punch_cr.commit()
                        punch_committed.set()
                        return {'snapshot': snapshot, 'attendance_id': attendance_id}
                finally:
                    punch_finished.set()

            def edit_template_from_stale_snapshot():
                with self.registry.cursor() as edit_cr:
                    api.Transaction(self.registry)
                    arm_transaction(edit_cr)
                    edit_env = api.Environment(edit_cr, SUPERUSER_ID, {})
                    snapshot = take_snapshot(edit_cr, edit_env)
                    barrier.wait()
                    if not punch_finished.wait(timeout=12):
                        raise TimeoutError('Managed punch did not finish within the bounded race window')
                    if not punch_committed.is_set():
                        raise RuntimeError('Managed punch transaction did not commit')
                    try:
                        edit_env['sl.shift'].browse(shifts[0]).write({'start_time': 10})
                        edit_cr.commit()
                    except psycopg2.errors.SerializationFailure:
                        return {'snapshot': snapshot, 'outcome': 'serialization'}
                    except UserError:
                        return {'snapshot': snapshot, 'outcome': 'rejected'}
                    return {'snapshot': snapshot, 'outcome': 'committed'}

            with ThreadPoolExecutor(max_workers=2) as executor:
                punch_future = executor.submit(create_managed_punch)
                edit_future = executor.submit(edit_template_from_stale_snapshot)
                punch_result = punch_future.result(timeout=20)
                edit_result = edit_future.result(timeout=20)

            for snapshot in (punch_result['snapshot'], edit_result['snapshot']):
                self.assertEqual(snapshot[0], 'repeatable read')
                self.assertEqual(snapshot[1]['start_time'], 9)
                self.assertEqual(snapshot[2]['attendance_policy'], 'shift')
                self.assertEqual(snapshot[3], 0, 'Both transaction snapshots must precede the punch commit')

            retry_rejected = False
            if edit_result['outcome'] == 'serialization':
                # The serialization loser must retry in a fresh transaction;
                # that snapshot must see the committed history and retain freeze.
                with self.registry.cursor() as retry_cr:
                    api.Transaction(self.registry)
                    arm_transaction(retry_cr)
                    retry_env = api.Environment(retry_cr, SUPERUSER_ID, {})
                    self.assertEqual(retry_env['sl.shift.day'].sudo().search_count([
                        ('assignment_id', '=', assignments[0]),
                    ]), 1)
                    try:
                        with retry_cr.savepoint():
                            retry_env['sl.shift'].browse(shifts[0]).write({'start_time': 10})
                    except UserError:
                        retry_rejected = True
                    else:
                        retry_cr.commit()

            self.assertIn(edit_result['outcome'], ('serialization', 'rejected'),
                          'A stale template writer must not commit over a managed punch')
            self.assertTrue(retry_rejected or edit_result['outcome'] == 'rejected',
                            'The writer or its fresh retry must reject after history is committed')

            with self.registry.cursor() as verify_cr:
                api.Transaction(self.registry)
                verify_env = api.Environment(verify_cr, SUPERUSER_ID, {})
                shift = verify_env['sl.shift'].browse(shifts[0])
                attendance = verify_env['hr.attendance'].browse(punch_result['attendance_id'])
                day = verify_env['sl.shift.day'].sudo().search([
                    ('assignment_id', '=', assignments[0]),
                ])
                self.assertEqual(shift.start_time, 9)
                self.assertEqual(len(day), 1)
                self.assertEqual(attendance.sl_shift_day_id, day)
                self.assertEqual(str(day.start), '2026-11-09 09:00:00')
                self.assertEqual((day.expected_hours, day.net_hours, day.regular_hours,
                                  day.raw_overtime_hours, day.presence_days), (8, 9, 8, 1, 1))
                self.assertEqual(attendance.worked_hours, 9)
        finally:
            if employees:
                with self.registry.cursor() as cleanup_cr:
                    api.Transaction(self.registry)
                    cleanup_env = api.Environment(cleanup_cr, SUPERUSER_ID, {})
                    cleanup_cr.execute(
                        'SELECT id FROM sl_shift_day WHERE employee_id = ANY(%s)', (employees,))
                    day_ids = [row[0] for row in cleanup_cr.fetchall()]
                    if day_ids:
                        cleanup_cr.execute('DELETE FROM sl_shift_audit WHERE day_id = ANY(%s)', (day_ids,))
                        cleanup_cr.execute(
                            'UPDATE hr_attendance SET sl_shift_day_id = NULL WHERE sl_shift_day_id = ANY(%s)',
                            (day_ids,))
                        cleanup_cr.execute('DELETE FROM sl_shift_day WHERE id = ANY(%s)', (day_ids,))
                    cleanup_cr.execute('DELETE FROM hr_attendance WHERE employee_id = ANY(%s)', (employees,))
                    cleanup_env['sl.shift.assignment'].browse(assignments).unlink()
                    cleanup_env['sl.shift'].browse(shifts).unlink()
                    cleanup_env['hr.employee'].browse(employees).unlink()
                    cleanup_cr.commit()

    def test_new_assignment_and_template_edit_serialize_on_shift_key(self):
        import threading
        import uuid
        from concurrent.futures import ThreadPoolExecutor

        import psycopg2

        token = uuid.uuid4().hex
        employee_id = shift_id = assignment_id = None
        try:
            with self.registry.cursor() as setup_cr:
                api.Transaction(self.registry)
                setup_env = api.Environment(setup_cr, SUPERUSER_ID, {})
                employee = setup_env['hr.employee'].create({'name': 'Synthetic shift-key race ' + token})
                shift = setup_env['sl.shift'].create({
                    'name': 'Synthetic shift-key template ' + token,
                    'start_time': 9, 'end_time': 17, 'break_minutes': 60,
                })
                employee_id, shift_id = employee.id, shift.id
                setup_cr.commit()

            barrier = threading.Barrier(2, timeout=5)
            template_committed = threading.Event()

            def arm_transaction(cr):
                cr.execute("SET LOCAL lock_timeout = '3000ms'")
                cr.execute("SET LOCAL statement_timeout = '10000ms'")

            def assignment_from_stale_snapshot():
                with self.registry.cursor() as assignment_cr:
                    api.Transaction(self.registry)
                    arm_transaction(assignment_cr)
                    assignment_env = api.Environment(assignment_cr, SUPERUSER_ID, {})
                    assignment_cr.execute('SHOW transaction_isolation')
                    isolation = assignment_cr.fetchone()[0]
                    old_start = assignment_env['sl.shift'].browse(shift_id).start_time
                    existing = assignment_env['sl.shift.assignment'].with_context(active_test=False).search([
                        ('shift_id', '=', shift_id),
                    ])
                    barrier.wait()
                    if not template_committed.wait(timeout=12):
                        raise TimeoutError('Template writer did not commit within the bounded race window')
                    values = {
                        'employee_id': employee_id, 'shift_id': shift_id,
                        'date_from': '2026-11-09', 'date_to': '2026-11-15',
                        'attendance_policy': 'shift', 'schedule_tz': 'UTC',
                        'workdays': '0,1,2,3,4,5,6', 'break_window_set': True,
                        # Valid only against the 09:00 template seen by this snapshot.
                        'break_start': 9.5,
                    }
                    try:
                        assignment = assignment_env['sl.shift.assignment'].create(values)
                        assignment_cr.commit()
                        return {'outcome': 'committed', 'assignment_id': assignment.id,
                                'isolation': isolation, 'old_start': old_start,
                                'existing_count': len(existing)}
                    except psycopg2.errors.SerializationFailure:
                        return {'outcome': 'serialization', 'isolation': isolation,
                                'old_start': old_start, 'existing_count': len(existing)}

            def edit_template_from_stale_snapshot():
                with self.registry.cursor() as template_cr:
                    api.Transaction(self.registry)
                    arm_transaction(template_cr)
                    template_env = api.Environment(template_cr, SUPERUSER_ID, {})
                    isolation = template_cr.execute('SHOW transaction_isolation')
                    isolation = template_cr.fetchone()[0]
                    old_start = template_env['sl.shift'].browse(shift_id).start_time
                    existing = template_env['sl.shift.assignment'].with_context(active_test=False).search([
                        ('shift_id', '=', shift_id),
                    ])
                    barrier.wait()
                    template_env['sl.shift'].browse(shift_id).write({'start_time': 10})
                    template_cr.commit()
                    template_committed.set()
                    return {'outcome': 'committed', 'isolation': isolation,
                            'old_start': old_start, 'existing_count': len(existing)}

            with ThreadPoolExecutor(max_workers=2) as executor:
                assignment_future = executor.submit(assignment_from_stale_snapshot)
                template_future = executor.submit(edit_template_from_stale_snapshot)
                template_result = template_future.result(timeout=20)
                assignment_result = assignment_future.result(timeout=20)

            self.assertEqual(template_result['isolation'], 'repeatable read')
            self.assertEqual(assignment_result['isolation'], 'repeatable read')
            self.assertEqual(template_result['old_start'], 9)
            self.assertEqual(assignment_result['old_start'], 9)
            self.assertEqual(template_result['existing_count'], 0)
            self.assertEqual(assignment_result['existing_count'], 0)
            self.assertEqual(assignment_result['outcome'], 'serialization',
                             'The stale assignment writer must lose the shared shift-key update')

            with self.registry.cursor() as retry_cr:
                api.Transaction(self.registry)
                arm_transaction(retry_cr)
                retry_env = api.Environment(retry_cr, SUPERUSER_ID, {})
                current_shift = retry_env['sl.shift'].browse(shift_id)
                self.assertEqual(current_shift.start_time, 10,
                                 'A fresh retry must see the committed template')
                self.assertFalse(retry_env['sl.shift.assignment'].with_context(active_test=False).search([
                    ('shift_id', '=', shift_id),
                ]), 'The serialization loser must not leave a stale assignment behind')
                stale_values = {
                    'employee_id': employee_id, 'shift_id': shift_id,
                    'date_from': '2026-11-09', 'date_to': '2026-11-15',
                    'attendance_policy': 'shift', 'schedule_tz': 'UTC',
                    'workdays': '0,1,2,3,4,5,6', 'break_window_set': True,
                    'break_start': 9.5,
                }
                with self.assertRaises(ValidationError):
                    with retry_cr.savepoint():
                        retry_env['sl.shift.assignment'].create(stale_values)
                stale_values['break_start'] = 10.5
                assignment = retry_env['sl.shift.assignment'].create(stale_values)
                assignment_id = assignment.id
                retry_cr.commit()

            with self.registry.cursor() as verify_cr:
                api.Transaction(self.registry)
                verify_env = api.Environment(verify_cr, SUPERUSER_ID, {})
                current_shift = verify_env['sl.shift'].browse(shift_id)
                assignment = verify_env['sl.shift.assignment'].browse(assignment_id)
                self.assertEqual(current_shift.start_time, 10)
                self.assertEqual(assignment.shift_id, current_shift)
                self.assertEqual(assignment.break_start, 10.5)
                self.assertEqual(verify_env['sl.shift.assignment'].with_context(active_test=False).search_count([
                    ('shift_id', '=', shift_id),
                ]), 1)
        finally:
            if employee_id:
                with self.registry.cursor() as cleanup_cr:
                    api.Transaction(self.registry)
                    cleanup_env = api.Environment(cleanup_cr, SUPERUSER_ID, {})
                    cleanup_env['sl.shift.assignment'].with_context(active_test=False).search([
                        ('employee_id', '=', employee_id),
                    ]).unlink()
                    cleanup_env['sl.shift'].browse(shift_id).unlink()
                    cleanup_env['hr.employee'].browse(employee_id).unlink()
                    cleanup_cr.commit()

    def test_new_opted_assignment_serializes_with_stale_attendance_punch(self):
        import threading
        import uuid
        from concurrent.futures import ThreadPoolExecutor

        import psycopg2

        token = uuid.uuid4().hex
        employee_id = shift_id = assignment_id = attendance_id = None
        try:
            with self.registry.cursor() as setup_cr:
                api.Transaction(self.registry)
                setup_env = api.Environment(setup_cr, SUPERUSER_ID, {})
                employee = setup_env['hr.employee'].create({'name': 'Synthetic assignment-punch race ' + token})
                shift = setup_env['sl.shift'].create({
                    'name': 'Synthetic assignment-punch shift ' + token,
                    'start_time': 9, 'end_time': 17,
                })
                employee_id, shift_id = employee.id, shift.id
                setup_cr.commit()

            barrier = threading.Barrier(2, timeout=5)
            assignment_committed = threading.Event()

            def arm_transaction(cr):
                cr.execute("SET LOCAL lock_timeout = '3000ms'")
                cr.execute("SET LOCAL statement_timeout = '10000ms'")

            def create_opted_assignment():
                with self.registry.cursor() as assignment_cr:
                    api.Transaction(self.registry)
                    arm_transaction(assignment_cr)
                    assignment_env = api.Environment(assignment_cr, SUPERUSER_ID, {})
                    assignment_cr.execute('SHOW transaction_isolation')
                    isolation = assignment_cr.fetchone()[0]
                    old_assignments = assignment_env['sl.shift.assignment'].with_context(active_test=False).search([
                        ('employee_id', '=', employee_id),
                    ])
                    barrier.wait()
                    assignment = assignment_env['sl.shift.assignment'].create({
                        'employee_id': employee_id, 'shift_id': shift_id,
                        'date_from': '2026-11-09', 'date_to': '2026-11-15',
                        'attendance_policy': 'shift', 'schedule_tz': 'UTC',
                        'workdays': '0,1,2,3,4,5,6',
                    })
                    assignment_id = assignment.id
                    assignment_cr.commit()
                    assignment_committed.set()
                    return {'assignment_id': assignment_id, 'isolation': isolation,
                            'old_assignment_count': len(old_assignments)}

            def punch_from_stale_snapshot():
                with self.registry.cursor() as punch_cr:
                    api.Transaction(self.registry)
                    arm_transaction(punch_cr)
                    punch_env = api.Environment(punch_cr, SUPERUSER_ID, {})
                    punch_cr.execute('SHOW transaction_isolation')
                    isolation = punch_cr.fetchone()[0]
                    old_assignments = punch_env['sl.shift.assignment'].with_context(active_test=False).search([
                        ('employee_id', '=', employee_id),
                    ])
                    barrier.wait()
                    if not assignment_committed.wait(timeout=12):
                        raise TimeoutError('Assignment writer did not commit within the bounded race window')
                    try:
                        attendance = punch_env['hr.attendance'].create({
                            'employee_id': employee_id,
                            'check_in': '2026-11-09 09:00:00',
                            'check_out': '2026-11-09 17:00:00',
                        })
                        attendance_id = attendance.id
                        punch_cr.commit()
                        return {'outcome': 'committed', 'attendance_id': attendance_id,
                                'isolation': isolation, 'old_assignment_count': len(old_assignments)}
                    except psycopg2.errors.SerializationFailure:
                        return {'outcome': 'serialization', 'isolation': isolation,
                                'old_assignment_count': len(old_assignments)}

            with ThreadPoolExecutor(max_workers=2) as executor:
                assignment_future = executor.submit(create_opted_assignment)
                punch_future = executor.submit(punch_from_stale_snapshot)
                assignment_result = assignment_future.result(timeout=20)
                punch_result = punch_future.result(timeout=20)

            self.assertEqual(assignment_result['isolation'], 'repeatable read')
            self.assertEqual(punch_result['isolation'], 'repeatable read')
            self.assertEqual(assignment_result['old_assignment_count'], 0)
            self.assertEqual(punch_result['old_assignment_count'], 0)
            assignment_id = assignment_result['assignment_id']
            if punch_result['outcome'] == 'committed':
                attendance_id = punch_result['attendance_id']
            self.assertEqual(punch_result['outcome'], 'serialization',
                             'The stale punch must lose against the newly opted-in assignment')

            with self.registry.cursor() as retry_cr:
                api.Transaction(self.registry)
                arm_transaction(retry_cr)
                retry_env = api.Environment(retry_cr, SUPERUSER_ID, {})
                assignment = retry_env['sl.shift.assignment'].browse(assignment_id)
                self.assertEqual(assignment.attendance_policy, 'shift',
                                 'A fresh punch retry must see the committed opted-in assignment')
                attendance = retry_env['hr.attendance'].create({
                    'employee_id': employee_id,
                    'check_in': '2026-11-09 09:00:00',
                    'check_out': '2026-11-09 17:00:00',
                })
                attendance_id = attendance.id
                retry_cr.commit()

            with self.registry.cursor() as verify_cr:
                api.Transaction(self.registry)
                verify_env = api.Environment(verify_cr, SUPERUSER_ID, {})
                attendance = verify_env['hr.attendance'].browse(attendance_id)
                self.assertTrue(attendance.sl_shift_day_id)
                self.assertEqual(attendance.sl_shift_day_id.assignment_id.id, assignment_id)
                self.assertEqual((attendance.worked_hours, attendance.sl_shift_day_id.net_hours,
                                  attendance.sl_shift_day_id.presence_days), (8, 8, 1))
        finally:
            if employee_id:
                with self.registry.cursor() as cleanup_cr:
                    api.Transaction(self.registry)
                    cleanup_env = api.Environment(cleanup_cr, SUPERUSER_ID, {})
                    cleanup_cr.execute(
                        'SELECT id FROM sl_shift_day WHERE employee_id = %s', (employee_id,))
                    day_ids = [row[0] for row in cleanup_cr.fetchall()]
                    if day_ids:
                        cleanup_cr.execute('DELETE FROM sl_shift_audit WHERE day_id = ANY(%s)', (day_ids,))
                        cleanup_cr.execute(
                            'UPDATE hr_attendance SET sl_shift_day_id = NULL WHERE sl_shift_day_id = ANY(%s)',
                            (day_ids,))
                        cleanup_cr.execute('DELETE FROM sl_shift_day WHERE id = ANY(%s)', (day_ids,))
                    cleanup_cr.execute('DELETE FROM hr_attendance WHERE employee_id = %s', (employee_id,))
                    cleanup_env['sl.shift.assignment'].with_context(active_test=False).search([
                        ('employee_id', '=', employee_id),
                    ]).unlink()
                    cleanup_env['sl.shift'].browse(shift_id).unlink()
                    cleanup_env['hr.employee'].browse(employee_id).unlink()
                    cleanup_cr.commit()
