# SPDX-License-Identifier: LGPL-3.0-or-later

import json

from lxml import etree

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestShiftWorkEntry(TransactionCase):
    def setUp(self):
        super().setUp()
        self.employee = self.env['hr.employee'].create({'name': 'Synthetic work-entry employee'})
        self.employee.sl_shift_work_entry_source = 'sl_shift_manual'
        self.overtime_type = self.env['hr.work.entry.type'].create({'name': 'Synthetic explicitly mapped extra hours', 'code': 'SL_TEST_OT14'})
        self.shift = self.env['sl.shift'].create({'name': 'Synthetic bridge night', 'start_time': 18, 'end_time': 3, 'break_minutes': 60})
        self.assignment = self.env['sl.shift.assignment'].create({
            'employee_id': self.employee.id, 'shift_id': self.shift.id, 'date_from': '2026-11-01',
            'date_to': '2026-11-30', 'attendance_policy': 'shift', 'schedule_tz': 'UTC',
            'workdays': '0,1,2,3,4,5,6', 'break_window_set': True, 'break_start': 22,
            'work_entry_enabled': True,
            'regular_type_id': self.env.ref('hr_work_entry.work_entry_type_attendance').id,
            'overtime_type_id': self.overtime_type.id,
        })
        self.actor = new_test_user(self.env['res.users'].with_context(no_reset_password=True).env, email='synthetic-shift@example.invalid', login='slshift-bridge-actor', groups='base.group_user,hr.group_hr_manager,hr_attendance.group_hr_attendance_manager,sl_employee_shift_attendance.group_shift_approver')
        self.officer = new_test_user(self.env['res.users'].with_context(no_reset_password=True).env, email='synthetic-shift@example.invalid', login='slshift-bridge-officer', groups='base.group_user,hr.group_hr_manager,hr_attendance.group_hr_attendance_user')
        self.approver = new_test_user(self.env['res.users'].with_context(no_reset_password=True).env, email='synthetic-shift@example.invalid', login='slshift-bridge-approver', groups='base.group_user,hr.group_hr_user,sl_employee_shift_attendance.group_shift_approver')
        self.assignment.flush()

    def _punch(self, start='2026-11-02 18:00:00', stop='2026-11-03 05:00:00'):
        return self.env['hr.attendance'].create({'employee_id': self.employee.id, 'check_in': start, 'check_out': stop})

    def _approved(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id.with_user(self.actor)
        day.action_approve(2, 'Synthetic explicit authorization')
        return attendance, day, day.action_generate_work_entries()

    def _snapshot(self, attendance, day):
        self.env['hr.attendance'].flush()
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
        attendance, day, entries = self._approved()
        self.assertEqual(entries._name, 'hr.work.entry')
        self.assertEqual(sorted((str(e.date_start), str(e.date_stop), e.sl_shift_kind, e.duration) for e in entries),
                         [('2026-11-02 18:00:00', '2026-11-02 22:00:00', 'regular', 4),
                          ('2026-11-02 23:00:00', '2026-11-03 00:00:00', 'regular', 1),
                          ('2026-11-03 00:00:00', '2026-11-03 03:00:00', 'regular', 3),
                          ('2026-11-03 03:00:00', '2026-11-03 05:00:00', 'overtime', 2)])
        self.assertEqual(sum(entries.mapped('duration')), 10)
        self.assertEqual(sum(entries.filtered(lambda e: e.sl_shift_kind == 'regular').mapped('duration')), 8)
        self.assertEqual(day.presence_days, 1)
        self.assertTrue(all(e.company_id == self.employee.company_id for e in entries))

    def test_generate_ui_action_is_serializable_and_reuses_native_entries(self):
        attendance, day, entries = self._approved()
        action = day.action_generate_and_open_work_entries()
        self.assertEqual(action['res_model'], 'hr.work.entry')
        self.assertEqual(action['domain'], [('id', 'in', entries.ids)])

    def test_generate_button_visibility_matches_authorization_roles(self):
        day = self._punch().sl_shift_day_id
        view = self.env.ref('sl_employee_shift_work_entry.view_shift_day_work_entry_form')
        actors = {
            'hr_only': self.officer,
            'approver_only': self.approver,
            'dual_role': self.actor,
        }
        capability = {}
        expected_modifier = [
            '|', ['state', 'in', ['open', 'void']],
            ['can_generate_work_entries', '=', False],
        ]
        for label, user in actors.items():
            with self.subTest(actor=label):
                actor_day = day.with_user(user).sudo()
                self.assertIn('can_generate_work_entries', actor_day._fields)
                capability[label] = actor_day.can_generate_work_entries
                view_data = actor_day.fields_view_get(view.id, 'form')
                self.assertIn('can_generate_work_entries', view_data['fields'])
                root = etree.fromstring(view_data['arch'].encode())
                buttons = root.xpath("//button[@name='action_generate_and_open_work_entries']")
                if buttons:
                    self.assertEqual(len(buttons), 1)
                    modifiers = json.loads(buttons[0].get('modifiers', '{}'))
                    if label == 'approver_only':
                        self.assertTrue(modifiers.get('invisible'))
                    else:
                        self.assertEqual(modifiers.get('invisible'), expected_modifier)
                else:
                    self.assertEqual(label, 'approver_only')
                visible = bool(buttons) and day.state not in ('open', 'void') and capability[label]
                self.assertEqual(visible, label == 'dual_role')
        self.assertEqual(capability, {'hr_only': False, 'approver_only': False, 'dual_role': True})

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

    def test_manual_generation_is_idempotent_without_fictional_native_generator(self):
        attendance, day, entries = self._approved()
        old_ids = sorted(entries.ids)
        self.assertEqual(sorted(day.action_generate_work_entries().ids), old_ids)
        self.assertNotIn('contract_id', self.env['hr.work.entry']._fields)
        self.assertFalse(hasattr(self.employee, '_generate_work_entries'))
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
        self.employee.sl_shift_work_entry_source = 'native'
        with self.assertRaises(UserError):
            day.with_user(self.actor).action_generate_work_entries()

    def test_work_entry_direct_writes_defaults_copy_and_source_spoofing_refused(self):
        attendance, day, entries = self._approved()
        baseline = self._snapshot(attendance, day)
        for values in ({'duration': 99}, {'date_stop': '2026-11-10 20:00:00'}, {'sl_shift_day_id': False}, {'company_id': False},
                       {'date_start': '2026-11-10 18:00:00'}, {'sl_shift_digest': 'forged'}, {'state': 'validated'}, {'active': False}):
            with self.assertRaises(AccessError):
                entries.with_user(self.actor).with_context(_sl_shift_capability=True).write(values)
        with self.assertRaises(AccessError):
            self.env['hr.work.entry'].with_context(default_name='Synthetic native14 entry').with_user(self.actor).with_context(default_sl_shift_day_id=day.id).create({
                'employee_id': self.employee.id,
                'date_start': '2026-11-03 03:00:00', 'date_stop': '2026-11-03 05:00:00', 'work_entry_type_id': self.assignment.overtime_type_id.id})
        with self.assertRaises(AccessError):
            entries[:1].with_user(self.actor).copy()
        with self.assertRaises(AccessError):
            entries.with_user(self.actor).unlink()
        self.assertEqual(baseline, self._snapshot(attendance, day))

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
            lambda: self.employee.with_user(self.actor).write({'sl_shift_work_entry_source': 'native'}),
            lambda: self.assignment.overtime_type_id.with_user(self.actor).write({'code': 'FORGED'}),
            lambda: self.assignment.overtime_type_id.with_user(self.actor).write({'active': False}),
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
        november = sum(entries.filtered(lambda e: e.date_start.month == 11).mapped('duration'))
        december = sum(entries.filtered(lambda e: e.date_start.month == 12).mapped('duration'))
        self.assertEqual((november, december, november + december, day.presence_days), (5, 5, 10, 1))
        self.assertEqual(str(day.shift_date), '2026-11-30')

    def test_repair_preview_includes_existing_native_work_entries(self):
        attendance, day, entries = self._approved()
        preview = self.assignment.with_user(self.actor).action_repair_attendance()
        self.assertEqual(set(row['id'] for row in preview[0]['existing_work_entries']), set(entries.ids))
        self.assertEqual(preview[0]['proposed_approved_overtime'], 2)
        self.assertFalse(preview[0]['finalized_work_entries_block_repair'])

    def test_existing_native_entries_are_reported_not_deleted(self):
        self.assignment.work_entry_enabled = False
        self.employee.sl_shift_work_entry_source = 'native'
        existing = self.env['hr.work.entry'].create({'name': 'Synthetic unrelated native entry', 'employee_id': self.employee.id,
                                                    'date_start': '2026-11-02 18:00:00', 'date_stop': '2026-11-03 02:00:00',
                                                    'work_entry_type_id': self.assignment.regular_type_id.id})
        self.employee.sl_shift_work_entry_source = 'sl_shift_manual'
        self.assignment.work_entry_enabled = True
        attendance = self._punch()
        day = attendance.sl_shift_day_id.with_user(self.actor)
        with self.assertRaises(UserError):
            day.action_generate_work_entries()
        self.assertTrue(existing.exists())
        self.assertEqual(existing.duration, 8)
        self.assertFalse(day.work_entry_ids)

    def test_native_entry_only_in_unapproved_overtime_tail_blocks_export_atomically(self):
        self.assignment.work_entry_enabled = False
        self.employee.sl_shift_work_entry_source = 'native'
        native_tail = self.env['hr.work.entry'].create({
            'name': 'Synthetic native overtime-tail entry', 'employee_id': self.employee.id,
            'date_start': '2026-11-03 03:00:00', 'date_stop': '2026-11-03 05:00:00',
            'work_entry_type_id': self.assignment.regular_type_id.id,
        })
        self.employee.sl_shift_work_entry_source = 'sl_shift_manual'
        self.assignment.work_entry_enabled = True
        day = self._punch().sl_shift_day_id.with_user(self.actor)
        self.assertEqual((day.state, day.regular_hours, day.raw_overtime_hours), ('pending', 8, 2))
        with self.env.cr.savepoint():
            try:
                day.action_generate_work_entries()
            except UserError:
                pass
            else:
                self.fail('A native entry in the unapproved overtime tail did not block export')
            self.assertTrue(native_tail.exists(), 'The pre-existing native row must be retained')
            self.assertFalse(day.work_entry_ids, 'A failed export must leave no managed rows')

    def test_nonoverlapping_native_entry_is_preserved_while_shift_export_succeeds(self):
        self.assignment.work_entry_enabled = False
        self.employee.sl_shift_work_entry_source = 'native'
        native_unrelated = self.env['hr.work.entry'].create({
            'name': 'Synthetic unrelated native entry', 'employee_id': self.employee.id,
            'date_start': '2026-11-05 09:00:00', 'date_stop': '2026-11-05 10:00:00',
            'work_entry_type_id': self.assignment.regular_type_id.id,
        })
        self.employee.sl_shift_work_entry_source = 'sl_shift_manual'
        self.assignment.work_entry_enabled = True
        day = self._punch().sl_shift_day_id.with_user(self.actor)
        generated = day.action_generate_work_entries()
        self.assertEqual(sum(generated.mapped('duration')), 8)
        self.assertTrue(native_unrelated.exists())
        self.assertEqual(native_unrelated.duration, 1)

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
        self.employee.sl_shift_work_entry_source = 'native'
        with self.assertRaises(AccessError):
            self.env['hr.work.entry'].with_context(default_name='Synthetic native14 entry').with_user(self.actor).create({
                'employee_id': self.employee.id,
                'date_start': '2026-11-02 18:00:00', 'date_stop': '2026-11-03 02:00:00',
                'work_entry_type_id': self.assignment.regular_type_id.id})

    def test_context_default_relational_commands_cannot_forge_authoritative_children(self):
        # This caller never receives the internal capability, including through
        # defaults applied by nested ORM creates.
        attendance = self.env['hr.attendance'].with_context(default_work_entry_ids=[(0, 0, {
            'employee_id': self.employee.id,
            'date_start': '2026-11-03 03:00:00', 'date_stop': '2026-11-03 05:00:00', 'work_entry_type_id': self.assignment.overtime_type_id.id,
        })]).create({'employee_id': self.employee.id, 'check_in': '2026-11-02 18:00:00', 'check_out': '2026-11-03 03:00:00'})
        self.assertFalse(attendance.sl_shift_day_id.work_entry_ids, 'User context defaults forged authoritative work entries')


    def test_default_employee_cannot_bypass_exclusive_manual_source(self):
        with self.assertRaises(AccessError):
            self.env['hr.work.entry'].with_user(self.actor).with_context(
                default_employee_id=self.employee.id, default_name='Synthetic default source bypass',
                default_date_start='2026-10-31 10:00:00', default_duration=1).create({
                    'work_entry_type_id': self.assignment.regular_type_id.id})

    def test_overlap_into_managed_duty_cannot_bypass_start_date_guard(self):
        self.employee.sl_shift_work_entry_source = 'native'
        with self.assertRaises(AccessError):
            self.env['hr.work.entry'].with_context(default_name='Synthetic native14 entry').with_user(self.actor).create({
                'name': 'Synthetic preceding-date overlap', 'employee_id': self.employee.id,
                 'date_start': '2026-10-31 23:00:00',
                'date_stop': '2026-11-01 20:00:00', 'work_entry_type_id': self.assignment.regular_type_id.id})

    def test_no_contract_or_native_overtime_api_is_invented(self):
        self.assertNotIn('contract_id', self.env['hr.work.entry']._fields)
        self.assertNotIn('hr.attendance.overtime', self.env.registry)
        self.assertNotIn('work_entry_source', self.env['hr.employee']._fields)
        self.assertEqual(self.employee.sl_shift_work_entry_source, 'sl_shift_manual')

    def test_finalized_interval_uses_assignment_window_not_employee_civil_midnight(self):
        self.assignment.work_entry_enabled = False
        self.employee.sl_shift_work_entry_source = 'native'
        self.employee.resource_id.tz = 'Pacific/Honolulu'
        shift = self.env['sl.shift'].create({'name': 'Synthetic UTC day shift', 'start_time': 9, 'end_time': 18, 'break_minutes': 60})
        self.assignment.write({'shift_id': shift.id, 'schedule_tz': 'UTC', 'break_start': 13})
        native = self.env['hr.work.entry'].create({'name': 'Finalized UTC morning', 'employee_id': self.employee.id,
             'date_start': '2026-11-02 09:00:00', 'date_stop': '2026-11-02 10:00:00',
            'work_entry_type_id': self.assignment.regular_type_id.id})
        self.assertTrue(native.action_validate())
        with self.assertRaises(UserError):
            self._punch('2026-11-02 09:00:00', '2026-11-02 18:00:00')
        self.assertEqual(native.state, 'validated')

    def test_foreign_native_work_entries_are_not_readable_or_reparentable(self):
        company = self.env['res.company'].create({'name': 'Synthetic foreign bridge company'})
        foreign_employee = self.env['hr.employee'].with_company(company).create({
            'name': 'Synthetic foreign work-entry employee', 'company_id': company.id})
        foreign = self.env['hr.work.entry'].with_company(company).create({
            'name': 'Synthetic foreign work entry', 'employee_id': foreign_employee.id,
            'company_id': company.id, 'date_start': '2026-11-02 09:00:00', 'date_stop': '2026-11-02 10:00:00',
            'work_entry_type_id': self.assignment.regular_type_id.id})
        restricted = foreign.with_user(self.actor).with_context(allowed_company_ids=[self.env.company.id])
        with self.assertRaises(AccessError):
            restricted.read(['date_start', 'duration'])
        own_employee = self.env['hr.employee'].create({'name': 'Synthetic own native control'})
        own = self.env['hr.work.entry'].with_user(self.actor).create({
            'name': 'Synthetic own native control', 'employee_id': own_employee.id,
            'date_start': '2026-11-02 09:00:00', 'date_stop': '2026-11-02 10:00:00',
            'work_entry_type_id': self.assignment.regular_type_id.id})
        self.assertEqual(own.duration, 1)
        for values in ({'employee_id': foreign_employee.id, 'company_id': company.id}, {'company_id': company.id}):
            with self.env.cr.savepoint():
                try:
                    own.with_user(self.actor).with_context(allowed_company_ids=[self.env.company.id]).write(values)
                except AccessError:
                    pass
                else:
                    self.fail('Foreign source reparenting was accepted')
                own.flush()
                self.env.cr.execute('SELECT employee_id, company_id FROM hr_work_entry WHERE id=%s', (own.id,))
                self.assertEqual(self.env.cr.fetchone(), (own_employee.id, self.env.company.id))

    def test_default_state_and_relational_source_spoof_cannot_change_export(self):
        day = self._punch().sl_shift_day_id.with_user(self.actor)
        entries = day.with_context(default_state='validated', default_duration=99,
                                   default_sl_shift_day_id=False, _sl_shift_capability=True).action_generate_work_entries()
        self.assertEqual(set(entries.mapped('state')), {'draft'})
        self.assertEqual(sum(entries.mapped('duration')), 8)
        self.assertEqual(entries.sl_shift_day_id, day)
        with self.assertRaises(AccessError):
            day.with_user(self.actor).write({'work_entry_ids': [(0, 0, {
                'name': 'Forged child', 'employee_id': self.employee.id,
                'date_start': '2026-11-03 03:00:00', 'date_stop': '2026-11-03 05:00:00'})]})
        self.assertFalse(entries.filtered(lambda e: e.sl_shift_kind == 'overtime'))

    def test_full_ordinary_and_verified_split_break_export_eight_regular_hours(self):
        ordinary = self._punch(stop='2026-11-03 03:00:00')
        day = ordinary.sl_shift_day_id.with_user(self.actor)
        entries = day.action_generate_work_entries()
        self.assertEqual((sum(entries.mapped('duration')), day.presence_days), (8, 1))
        self.assertFalse(entries.filtered(lambda e: e.sl_shift_kind == 'overtime'))
        split = self.env['hr.attendance'].create([
            {'employee_id': self.employee.id, 'check_in': '2026-11-04 18:00:00', 'check_out': '2026-11-04 22:00:00'},
            {'employee_id': self.employee.id, 'check_in': '2026-11-04 23:00:00', 'check_out': '2026-11-05 03:00:00'}])
        split_day = split.sl_shift_day_id.with_user(self.actor)
        split_entries = split_day.action_generate_work_entries()
        self.assertEqual((sum(split_entries.mapped('duration')), split_day.presence_days), (8, 1))
        self.assertEqual(sum((e.date_stop - e.date_start).total_seconds()/3600 for e in split_entries), 8)

    def test_unassigned_native_entries_and_duration_updates_keep_native_behavior(self):
        employee = self.env['hr.employee'].create({'name': 'Synthetic unassigned native14 employee'})
        self.assertEqual(employee.sl_shift_work_entry_source, 'native')
        entry = self.env['hr.work.entry'].with_user(self.actor).create({
            'name': 'Unassigned native control', 'employee_id': employee.id,
            'date_start': '2026-11-02 09:00:00', 'date_stop': '2026-11-02 12:00:00',
            'work_entry_type_id': self.assignment.regular_type_id.id})
        self.assertEqual(entry.duration, 3)
        entry.write({'date_stop': '2026-11-02 13:00:00'})
        self.assertEqual(entry.duration, 4)
        self.assertTrue(entry.with_user(self.actor).action_validate())
        self.assertFalse(entry.sl_shift_day_id)

    def test_incomplete_shift_cannot_export_work_entries(self):
        day = self._punch(stop=False).sl_shift_day_id.with_user(self.actor)
        with self.assertRaises(UserError):
            day.action_generate_work_entries()
        self.assertFalse(day.work_entry_ids)

    def _legacy_finalized_entry(self):
        self.assignment.work_entry_enabled = False
        self.employee.sl_shift_work_entry_source = 'native'
        entry = self.env['hr.work.entry'].create({
            'name': 'Synthetic pre-existing finalized native14 entry', 'employee_id': self.employee.id,
            'date_start': '2026-11-02 18:00:00', 'date_stop': '2026-11-03 03:00:00',
            'work_entry_type_id': self.assignment.regular_type_id.id})
        self.assertTrue(entry.action_validate())
        self.assignment.flush()
        return entry

    def test_legacy_finalized_native_entry_cannot_be_reopened_before_adoption(self):
        entry = self._legacy_finalized_entry()
        with self.assertRaises((AccessError, UserError)):
            entry.with_user(self.actor).write({'state': 'draft'})
        self.assertEqual(entry.state, 'validated')

    def test_legacy_finalized_period_cannot_be_bypassed_by_disabling_policy(self):
        entry = self._legacy_finalized_entry()
        with self.assertRaises(UserError):
            self.assignment.with_user(self.actor).write({'attendance_policy': 'off'})
        self.assertEqual(self.assignment.attendance_policy, 'shift')
        self.assertEqual(entry.state, 'validated')

    def test_legacy_finalized_period_freezes_template_before_first_punch(self):
        entry = self._legacy_finalized_entry()
        with self.assertRaises(UserError):
            self.shift.with_user(self.actor).write({'end_time': 5})
        self.assertEqual(self.shift.end_time, 3)
        self.assertEqual(entry.state, 'validated')

    def test_legacy_finalized_period_freezes_assignment_company_parent(self):
        self._legacy_finalized_entry()
        company = self.env['res.company'].create({'name': 'Synthetic finalized company move'})
        with self.assertRaises(UserError):
            self.employee.with_user(self.actor).with_context(allowed_company_ids=[self.env.company.id, company.id]).write({'company_id': company.id})
        self.assertEqual(self.employee.company_id, self.env.company)

    def test_employee_source_configuration_requires_actual_role_even_for_defaults(self):
        with self.assertRaises(AccessError):
            self.employee.with_user(self.officer).write({'sl_shift_work_entry_source': 'native'})
        for values, context in [({'sl_shift_work_entry_source': 'sl_shift_manual'}, {}),
                                ({}, {'default_sl_shift_work_entry_source': 'sl_shift_manual'})]:
            with self.assertRaises(AccessError):
                self.env['hr.employee'].with_user(self.officer).with_context(context).create(dict(
                    {'name': 'Synthetic unauthorized source'}, **values))
