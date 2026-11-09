# SPDX-License-Identifier: LGPL-3.0-or-later
from datetime import date

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestShiftWorkEntry(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create({'name': 'Synthetic work-entry employee', 'date_version': '2026-01-01', 'contract_date_start': '2026-01-01'})
        cls.employee.version_id.work_entry_source = 'sl_shift_manual'
        cls.shift = cls.env['sl.shift'].create({'name': 'Synthetic bridge night', 'start_time': 18, 'end_time': 3, 'break_minutes': 60})
        cls.assignment = cls.env['sl.shift.assignment'].create({
            'employee_id': cls.employee.id, 'shift_id': cls.shift.id, 'date_from': '2026-11-01',
            'date_to': '2026-11-30', 'attendance_policy': 'shift', 'schedule_tz': 'UTC',
            'workdays': '0,1,2,3,4,5,6', 'break_window_set': True, 'break_start': 22,
            'work_entry_enabled': True,
            'regular_type_id': cls.env.ref('hr_work_entry.work_entry_type_attendance').id,
            'overtime_type_id': cls.env.ref('hr_work_entry.work_entry_type_overtime').id,
        })
        cls.actor = new_test_user(
            cls.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-shift-bridge-actor@example.invalid', login='slshift-bridge-actor',
            groups='base.group_user,hr.group_hr_manager,hr_attendance.group_hr_attendance_manager,sl_employee_shift_attendance.group_shift_approver')
        cls.officer = new_test_user(
            cls.env['res.users'].with_context(no_reset_password=True).env,
            email='synthetic-shift-bridge-officer@example.invalid', login='slshift-bridge-officer',
            groups='base.group_user,hr.group_hr_manager,hr_attendance.group_hr_attendance_user')

    def _punch(self, start='2026-11-02 18:00:00', stop='2026-11-03 05:00:00'):
        return self.env['hr.attendance'].create({'employee_id': self.employee.id, 'check_in': start, 'check_out': stop})

    def _approved(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id.with_user(self.actor)
        day.action_approve(2, 'Synthetic explicit authorization')
        return attendance, day, day.action_generate_work_entries()

    def _snapshot(self, attendance, day):
        self.env.flush_all()
        result = []
        for query, params in [
            ('SELECT row_to_json(a) FROM hr_attendance a WHERE id = %s', (attendance.id,)),
            ('SELECT row_to_json(d) FROM sl_shift_day d WHERE id = %s', (day.id,)),
            ('SELECT row_to_json(w) FROM hr_work_entry w WHERE sl_shift_day_id = %s ORDER BY id', (day.id,)),
            ('SELECT row_to_json(a) FROM sl_shift_audit a WHERE day_id = %s ORDER BY id', (day.id,)),
        ]:
            self.env.cr.execute(query, params)
            result.append(self.env.cr.fetchall())
        return result

    def test_regular_and_approved_overtime_map_to_real_native_work_entries(self):
        _attendance, day, entries = self._approved()
        self.assertEqual(entries._name, 'hr.work.entry')
        self.assertEqual(sorted((str(e.date), e.sl_shift_kind, e.duration) for e in entries),
                         [('2026-11-02', 'regular', 5), ('2026-11-03', 'overtime', 2), ('2026-11-03', 'regular', 3)])
        self.assertEqual(sum(entries.mapped('duration')), 10)
        self.assertEqual(sum(entries.filtered(lambda e: e.sl_shift_kind == 'regular').mapped('duration')), 8)
        self.assertEqual(day.presence_days, 1)
        self.assertTrue(all(e.version_id == self.employee.version_id and e.company_id == self.employee.company_id for e in entries))

    def test_generate_ui_action_is_serializable_and_reuses_native_entries(self):
        _attendance, day, entries = self._approved()
        action = day.action_generate_and_open_work_entries()
        self.assertEqual(action['res_model'], 'hr.work.entry')
        self.assertEqual(action['domain'], [('id', 'in', entries.ids)])

    def test_pending_and_refused_overtime_never_pay_raw_overtime(self):
        day = self._punch().sl_shift_day_id.with_user(self.actor)
        entries = day.action_generate_work_entries()
        self.assertEqual(sum(entries.mapped('duration')), 8)
        self.assertFalse(entries.filtered(lambda e: e.sl_shift_kind == 'overtime'))
        day.action_refuse('Not authorized')
        self.assertFalse(entries.exists())
        entries = day.action_generate_work_entries()
        self.assertEqual(sum(entries.mapped('duration')), 8)

    def test_partial_approval_and_changed_decision_invalidate_draft_entries(self):
        attendance, day, entries = self._approved()
        day.action_approve(1, 'Only one hour')
        self.assertFalse(entries.exists())
        replacement = day.action_generate_work_entries()
        self.assertEqual(sum(replacement.mapped('duration')), 9)
        self.assertEqual(sum(replacement.filtered(lambda e: e.sl_shift_kind == 'overtime').mapped('duration')), 1)
        attendance.check_out = '2026-11-03 04:00:00'
        self.assertFalse(replacement.exists())
        self.assertEqual(day.approved_overtime_hours, 0)
        self.assertEqual(sum(day.action_generate_work_entries().mapped('duration')), 8)

    def test_manual_generation_and_native_regeneration_are_idempotent(self):
        _attendance, day, entries = self._approved()
        old_ids = sorted(entries.ids)
        self.assertEqual(sorted(day.action_generate_work_entries().ids), old_ids)
        native = self.employee.version_id.generate_work_entries(date(2026, 11, 1), date(2026, 11, 30), force=True)
        self.assertFalse(native)
        self.assertEqual(sorted(day.action_generate_work_entries().ids), old_ids)
        self.assertEqual(sum(day.work_entry_ids.mapped('duration')), 10)

    def test_explicit_source_mapping_and_role_are_required(self):
        day = self._punch().sl_shift_day_id
        with self.assertRaises(AccessError):
            day.with_user(self.officer).action_generate_work_entries()
        self.assignment.work_entry_enabled = False
        with self.assertRaises(UserError):
            day.with_user(self.actor).action_generate_work_entries()
        self.assignment.work_entry_enabled = True
        self.employee.version_id.work_entry_source = 'calendar'
        with self.assertRaises(UserError):
            day.with_user(self.actor).action_generate_work_entries()

    def test_work_entry_direct_writes_defaults_copy_and_source_spoofing_refused(self):
        attendance, day, entries = self._approved()
        baseline = self._snapshot(attendance, day)
        for values in ({'duration': 99}, {'amount_rate': 99}, {'sl_shift_day_id': False}, {'version_id': False},
                       {'date': '2026-11-10'}, {'sl_shift_digest': 'forged'}, {'state': 'validated'}, {'active': False}):
            with self.assertRaises(AccessError):
                entries.with_user(self.actor).with_context(_sl_shift_capability=True).write(values)
        with self.assertRaises(AccessError):
            self.env['hr.work.entry'].with_user(self.actor).with_context(default_sl_shift_day_id=day.id).create({
                'employee_id': self.employee.id, 'version_id': self.employee.version_id.id,
                'date': '2026-11-03', 'duration': 2, 'work_entry_type_id': self.assignment.overtime_type_id.id})
        with self.assertRaises(AccessError):
            entries[:1].with_user(self.actor).copy()
        with self.assertRaises(AccessError):
            entries.with_user(self.actor).unlink()
        self.assertEqual(baseline, self._snapshot(attendance, day))

    def test_new_punch_cannot_enter_a_finalized_shift_work_entry_date(self):
        _attendance, day, entries = self._approved()
        entries.with_user(self.actor).action_validate()
        with self.assertRaises(UserError):
            self.env['hr.attendance'].with_user(self.actor).create({
                'employee_id': self.employee.id,
                'check_in': '2026-11-03 06:00:00',
                'check_out': '2026-11-03 07:00:00',
            })
        self.assertFalse(self.env['hr.attendance'].sudo().search([
            ('employee_id', '=', self.employee.id), ('check_in', '=', '2026-11-03 06:00:00'),
        ]))
        self.assertEqual(set(day.work_entry_ids.ids), set(entries.ids))

    def test_finalized_native_entries_freeze_complete_mutation_surface(self):
        attendance, day, entries = self._approved()
        self.assertTrue(entries.with_user(self.actor).action_validate())
        self.assertEqual(set(entries.mapped('state')), {'validated'})
        baseline = self._snapshot(attendance, day)
        operations = [
            lambda: attendance.with_user(self.actor).write({'check_out': '2026-11-03 04:00:00'}),
            lambda: attendance.with_user(self.actor).unlink(),
            lambda: day.action_approve(1, 'Changed closed period'),
            lambda: day.action_refuse('Changed closed period'),
            lambda: entries.with_user(self.actor).write({'duration': 1}),
            lambda: entries.with_user(self.actor).write({'state': 'draft'}),
            lambda: entries.with_user(self.actor).unlink(),
            lambda: self.assignment.with_user(self.actor).write({'break_start': 23}),
            lambda: self.employee.version_id.with_user(self.actor).write({'work_entry_source': 'calendar'}),
            lambda: self.assignment.overtime_type_id.with_user(self.actor).write({'code': 'FORGED'}),
            lambda: self.assignment.overtime_type_id.with_user(self.actor).write({'is_extra_hours': False}),
            lambda: self.env['hr.attendance'].with_user(self.actor).create({'employee_id': self.employee.id, 'check_in': '2026-11-03 06:00:00', 'check_out': '2026-11-03 07:00:00'}),
        ]
        # Catch inside an outer savepoint and inspect SQL before it closes:
        # assertRaises' automatic rollback cannot mask partial writes here.
        for operation in operations:
            with self.env.cr.savepoint():
                try:
                    operation()
                except (AccessError, UserError):
                    pass
                else:
                    self.fail('A finalized mutation was accepted')
                self.assertEqual(baseline, self._snapshot(attendance, day))
        self.assertEqual(set(day.action_generate_work_entries().ids), set(entries.ids))
        control = self._punch('2026-11-05 18:00:00', '2026-11-06 03:00:00')
        self.assertEqual(control.worked_hours, 8)

    def test_month_boundary_clips_hours_but_not_presence(self):
        day = self._punch('2026-11-30 18:00:00', '2026-12-01 05:00:00').sl_shift_day_id.with_user(self.actor)
        day.action_approve(2, 'Synthetic boundary')
        entries = day.action_generate_work_entries()
        november = sum(entries.filtered(lambda e: e.date.month == 11).mapped('duration'))
        december = sum(entries.filtered(lambda e: e.date.month == 12).mapped('duration'))
        self.assertEqual((november, december, november + december, day.presence_days), (5, 5, 10, 1))
        self.assertEqual(str(day.shift_date), '2026-11-30')

    def test_repair_preview_includes_existing_native_work_entries(self):
        _attendance, _day, entries = self._approved()
        preview = self.assignment.with_user(self.actor).action_repair_attendance()
        self.assertEqual({row['id'] for row in preview[0]['existing_work_entries']}, set(entries.ids))
        self.assertEqual(preview[0]['proposed_approved_overtime'], 2)
        self.assertFalse(preview[0]['finalized_work_entries_block_repair'])

    def test_existing_native_entries_are_reported_not_deleted(self):
        self.assignment.work_entry_enabled = False
        self.employee.version_id.work_entry_source = 'calendar'
        existing = self.env['hr.work.entry'].create({'employee_id': self.employee.id, 'version_id': self.employee.version_id.id,
                                                    'date': '2026-11-02', 'duration': 8,
                                                    'work_entry_type_id': self.assignment.regular_type_id.id})
        self.employee.version_id.work_entry_source = 'sl_shift_manual'
        self.assignment.work_entry_enabled = True
        attendance = self._punch()
        day = attendance.sl_shift_day_id.with_user(self.actor)
        with self.assertRaises(UserError):
            day.action_generate_work_entries()
        self.assertTrue(existing.exists())
        self.assertEqual(existing.duration, 8)
        self.assertFalse(day.work_entry_ids)

    def test_leave_and_holiday_overlap_fail_closed_without_provider_guess(self):
        self.env['resource.calendar.leaves'].create({'name': 'Synthetic public holiday',
                                                    'calendar_id': self.employee.resource_calendar_id.id,
                                                    'date_from': '2026-11-02 00:00:00', 'date_to': '2026-11-04 00:00:00'})
        day = self._punch().sl_shift_day_id.with_user(self.actor)
        with self.assertRaises(UserError):
            day.action_generate_work_entries()
        self.assertFalse(day.work_entry_ids)

    def test_generic_native_creation_cannot_duplicate_enabled_dates_before_punches(self):
        # Even a caller supplying an older calendar version cannot race the
        # explicitly opted-in assignment before its first summary exists.
        self.employee.version_id.work_entry_source = 'calendar'
        with self.assertRaises(AccessError):
            self.env['hr.work.entry'].with_user(self.actor).create({
                'employee_id': self.employee.id, 'version_id': self.employee.version_id.id,
                'date': '2026-11-02', 'duration': 8,
                'work_entry_type_id': self.assignment.regular_type_id.id})

    def test_inferred_manual_version_cannot_bypass_source_guard(self):
        work_entries = self.env['hr.work.entry'].with_user(self.actor)
        self.assertEqual(self.employee.version_id.work_entry_source, 'sl_shift_manual')
        with self.env.cr.savepoint():
            try:
                work_entries.create({
                    'employee_id': self.employee.id, 'date': '2026-10-31', 'duration': 1,
                    'work_entry_type_id': self.assignment.regular_type_id.id,
                })
            except AccessError:
                pass
            else:
                self.fail('Native version inference bypassed the exclusive manual-source guard')
            self.env.flush_all()
            self.assertFalse(self.env['hr.work.entry'].sudo().search([
                ('employee_id', '=', self.employee.id), ('date', '=', '2026-10-31'),
            ]))

        self.employee.version_id.work_entry_source = 'calendar'
        control = work_entries.create({
            'employee_id': self.employee.id, 'date': '2026-10-31', 'duration': 1,
            'work_entry_type_id': self.assignment.regular_type_id.id,
        })
        self.assertEqual(control.version_id, self.employee.version_id)

    def test_context_default_relational_commands_cannot_forge_authoritative_children(self):
        # This caller never receives the internal capability, including through
        # defaults applied by nested ORM creates.
        attendance = self.env['hr.attendance'].with_context(default_work_entry_ids=[Command.create({
            'employee_id': self.employee.id, 'version_id': self.employee.version_id.id,
            'date': '2026-11-03', 'duration': 22, 'work_entry_type_id': self.assignment.overtime_type_id.id,
        })]).create({'employee_id': self.employee.id, 'check_in': '2026-11-02 18:00:00', 'check_out': '2026-11-03 03:00:00'})
        self.assertFalse(attendance.sl_shift_day_id.work_entry_ids, 'User context defaults forged authoritative work entries')
