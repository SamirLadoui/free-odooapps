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
        cls.employee = cls.env['hr.employee'].create({'name': 'Synthetic work-entry employee'})
        cls.contract = cls.env['hr.contract'].create({
            'name': 'Synthetic bridge contract', 'employee_id': cls.employee.id,
            'date_start': '2026-01-01', 'wage': 1, 'state': 'open',
            'resource_calendar_id': cls.employee.resource_calendar_id.id,
            'work_entry_source': 'sl_shift_manual',
        })
        cls.shift = cls.env['sl.shift'].create({'name': 'Synthetic bridge night', 'start_time': 18, 'end_time': 3, 'break_minutes': 60})
        cls.assignment = cls.env['sl.shift.assignment'].create({
            'employee_id': cls.employee.id, 'shift_id': cls.shift.id, 'date_from': '2026-11-01',
            'date_to': '2026-11-30', 'attendance_policy': 'shift', 'schedule_tz': 'UTC',
            'workdays': '0,1,2,3,4,5,6', 'break_window_set': True, 'break_start': 22,
            'work_entry_enabled': True,
            'regular_type_id': cls.env.ref('hr_work_entry.work_entry_type_attendance').id,
            'overtime_type_id': cls.env.ref('hr_work_entry.overtime_work_entry_type').id,
        })
        cls.actor = new_test_user(cls.env, login='slshift-bridge-actor', groups='base.group_user,hr.group_hr_manager,hr_contract.group_hr_contract_manager,hr_attendance.group_hr_attendance_manager,sl_employee_shift_attendance.group_shift_approver')
        cls.officer = new_test_user(cls.env, login='slshift-bridge-officer', groups='base.group_user,hr.group_hr_manager,hr_attendance.group_hr_attendance_officer')
        cls.approver = new_test_user(cls.env, login='slshift-bridge-approver', groups='base.group_user,hr.group_hr_user,sl_employee_shift_attendance.group_shift_approver')

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
            ('SELECT row_to_json(a) FROM sl_shift_assignment a WHERE id = %s', (day.assignment_id.id,)),
            ('SELECT row_to_json(c) FROM hr_contract c WHERE id = %s', (self.contract.id,)),
            ('SELECT row_to_json(e) FROM hr_employee e WHERE id = %s', (attendance.employee_id.id,)),
            ('SELECT row_to_json(t) FROM hr_work_entry_type t WHERE id = ANY(%s) ORDER BY id',
             ((day.assignment_id.regular_type_id | day.assignment_id.overtime_type_id).ids,)),
        ]:
            self.env.cr.execute(query, params)
            result.append(self.env.cr.fetchall())
        return result

    def test_regular_and_approved_overtime_map_to_real_native_work_entries(self):
        attendance, day, entries = self._approved()
        self.assertEqual(entries._name, 'hr.work.entry')
        self.assertEqual(sorted((str(e.date_start), str(e.date_stop), e.sl_shift_kind, e.duration) for e in entries), [
            ('2026-11-02 18:00:00', '2026-11-02 22:00:00', 'regular', 4),
            ('2026-11-02 23:00:00', '2026-11-03 00:00:00', 'regular', 1),
            ('2026-11-03 00:00:00', '2026-11-03 03:00:00', 'regular', 3),
            ('2026-11-03 03:00:00', '2026-11-03 05:00:00', 'overtime', 2),
        ])
        self.assertEqual(sum(entries.mapped('duration')), 10)
        self.assertEqual(sum(entries.filtered(lambda e: e.sl_shift_kind == 'regular').mapped('duration')), 8)
        self.assertEqual(day.presence_days, 1)
        self.assertTrue(all(e.contract_id == self.contract and e.company_id == self.employee.company_id for e in entries))

    def test_generate_button_requires_hr_manager_and_shift_approver(self):
        view_id = self.env.ref('sl_employee_shift_work_entry.view_shift_day_work_entry_form').id

        def arch(user):
            return self.env['sl.shift.day'].with_user(user).get_views([(view_id, 'form')])['views']['form']['arch']

        button = 'action_generate_and_open_work_entries'
        self.assertNotIn(button, arch(self.officer))
        self.assertNotIn(button, arch(self.approver))
        self.assertIn(button, arch(self.actor))

    def test_generate_ui_action_is_serializable_and_reuses_native_entries(self):
        attendance, day, entries = self._approved()
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
        attendance, day, entries = self._approved()
        old_ids = sorted(entries.ids)
        self.assertEqual(sorted(day.action_generate_work_entries().ids), old_ids)
        native = self.contract.generate_work_entries(date(2026, 11, 1), date(2026, 11, 30), force=True)
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
        self.contract.work_entry_source = 'calendar'
        with self.assertRaises(UserError):
            day.with_user(self.actor).action_generate_work_entries()

    def test_work_entry_direct_writes_defaults_copy_and_source_spoofing_refused(self):
        attendance, day, entries = self._approved()
        baseline = self._snapshot(attendance, day)
        for values in ({'duration': 99}, {'sl_shift_day_id': False}, {'contract_id': False},
                       {'date_start': '2026-11-10 18:00:00'}, {'sl_shift_digest': 'forged'}, {'state': 'validated'}, {'active': False}):
            with self.assertRaises(AccessError):
                entries.with_user(self.actor).with_context(_sl_shift_capability=True).write(values)
        with self.assertRaises(AccessError):
            self.env['hr.work.entry'].with_user(self.actor).with_context(default_sl_shift_day_id=day.id).create({
                'employee_id': self.employee.id, 'contract_id': self.contract.id,
                'date_start': '2026-11-03 03:00:00', 'date_stop': '2026-11-03 05:00:00', 'work_entry_type_id': self.assignment.overtime_type_id.id})
        with self.assertRaises(AccessError):
            entries[:1].with_user(self.actor).copy()
        with self.assertRaises(AccessError):
            entries.with_user(self.actor).unlink()
        self.assertEqual(baseline, self._snapshot(attendance, day))

    def test_finalized_native_entries_freeze_complete_mutation_surface(self):
        other = self.env['hr.employee'].create({'name': 'Synthetic same-company frozen target'})
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
            lambda: self.assignment.with_user(self.actor).write({'schedule_tz': 'Asia/Dubai'}),
            lambda: self.assignment.with_user(self.actor).write({'workdays': '0,1,2,3,4'}),
            lambda: self.assignment.with_user(self.actor).write({'employee_id': other.id}),
            lambda: self.assignment.with_user(self.actor).write({'company_id': self.env.company.id}),
            lambda: attendance.with_user(self.actor).write({'employee_id': other.id}),
            lambda: self.contract.with_user(self.actor).write({'work_entry_source': 'calendar'}),
            lambda: self.contract.with_user(self.actor).write({'date_end': '2026-11-02'}),
            lambda: self.contract.with_user(self.actor).write({'employee_id': other.id}),
            lambda: self.assignment.overtime_type_id.with_user(self.actor).write({'code': 'FORGED'}),
            lambda: self.assignment.overtime_type_id.with_user(self.actor).write({'is_leave': True}),
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
        post_stop = self.env['hr.attendance'].with_user(self.actor).create({
            'employee_id': self.employee.id, 'check_in': '2026-11-03 06:00:00',
            'check_out': '2026-11-03 07:00:00',
        })
        self.assertFalse(post_stop.sl_shift_day_id)
        self.assertEqual(post_stop.worked_hours, 1)
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
        self.contract.work_entry_source = 'calendar'
        existing = self.env['hr.work.entry'].create({'name': 'Synthetic unrelated native entry', 'employee_id': self.employee.id, 'contract_id': self.contract.id,
                                                    'date_start': '2026-11-02 18:00:00', 'date_stop': '2026-11-03 02:00:00',
                                                    'work_entry_type_id': self.assignment.regular_type_id.id})
        with self.assertRaises(UserError):
            self.contract.work_entry_source = 'sl_shift_manual'
        self.assertTrue(existing.exists())
        self.assertEqual(existing.duration, 8)
        self.assertEqual(self.contract.work_entry_source, 'calendar')

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
        self.contract.work_entry_source = 'calendar'
        with self.assertRaises(AccessError):
            self.env['hr.work.entry'].with_user(self.actor).create({
                'employee_id': self.employee.id, 'contract_id': self.contract.id,
                'date_start': '2026-11-02 18:00:00', 'date_stop': '2026-11-03 02:00:00',
                'work_entry_type_id': self.assignment.regular_type_id.id})

    def test_native_interval_after_scheduled_stop_is_not_owned_by_prior_shift(self):
        self.contract.work_entry_source = 'calendar'
        model = self.env['hr.work.entry'].with_user(self.actor)
        outside = model.create({
            'name': 'Synthetic interval after scheduled stop',
            'employee_id': self.employee.id, 'contract_id': self.contract.id,
            'date_start': '2026-11-03 16:00:00', 'date_stop': '2026-11-03 17:00:00',
            'work_entry_type_id': self.assignment.regular_type_id.id,
        })
        self.assertFalse(outside.sl_shift_day_id)
        with self.assertRaises(AccessError):
            model.create({
                'name': 'Synthetic overnight interval still owned',
                'employee_id': self.employee.id, 'contract_id': self.contract.id,
                'date_start': '2026-11-03 02:00:00', 'date_stop': '2026-11-03 03:00:00',
                'work_entry_type_id': self.assignment.regular_type_id.id,
            })

    def test_context_default_relational_commands_cannot_forge_authoritative_children(self):
        # This caller never receives the internal capability, including through
        # defaults applied by nested ORM creates.
        attendance = self.env['hr.attendance'].with_context(default_work_entry_ids=[Command.create({
            'employee_id': self.employee.id, 'contract_id': self.contract.id,
            'date_start': '2026-11-03 03:00:00', 'date_stop': '2026-11-04 01:00:00', 'work_entry_type_id': self.assignment.overtime_type_id.id,
        })]).create({'employee_id': self.employee.id, 'check_in': '2026-11-02 18:00:00', 'check_out': '2026-11-03 03:00:00'})
        self.assertFalse(attendance.sl_shift_day_id.work_entry_ids, 'User context defaults forged authoritative work entries')

    def test_inferred_manual_contract_cannot_bypass_source_guard(self):
        # Native Odoo 17 infers contract_id below this extension. Omitting it
        # cannot bypass manual-source ownership outside managed assignment dates.
        with self.env.cr.savepoint():
            try:
                self.env['hr.work.entry'].with_user(self.actor).create({
                    'name': 'Synthetic inferred manual contract', 'employee_id': self.employee.id,
                    'date_start': '2026-10-31 10:00:00', 'date_stop': '2026-10-31 11:00:00',
                    'work_entry_type_id': self.assignment.regular_type_id.id,
                })
            except AccessError as error:
                self.assertIn('Managed work-entry source', str(error))
            else:
                self.fail('Native inferred manual source bypassed the ownership guard')
            self.env.flush_all()
            self.env.cr.execute('SELECT count(*) FROM hr_work_entry WHERE employee_id = %s', (self.employee.id,))
            self.assertEqual(self.env.cr.fetchone()[0], 0)

    def test_native_interval_defaults_duration_and_updates_are_owned_atomically(self):
        self.contract.work_entry_source = 'calendar'
        model = self.env['hr.work.entry'].with_user(self.actor)
        values = {'name': 'Synthetic native ownership control', 'employee_id': self.employee.id,
                  'contract_id': self.contract.id, 'date_start': '2026-10-31 10:00:00',
                  'date_stop': '2026-10-31 11:00:00',
                  'work_entry_type_id': self.assignment.regular_type_id.id}
        control = model.create(values)
        self.assertEqual(control.duration, 1)
        before = control.read(['date_start', 'date_stop', 'duration', 'employee_id'])
        operations = [
            lambda: model.create([dict(values, name='Valid first batch row'),
                                  dict(values, date_stop='2026-11-03 12:00:00')]),
            lambda: model.with_context(default_employee_id=self.employee.id,
                                       default_contract_id=self.contract.id,
                                       default_date_start='2026-10-31 12:00:00',
                                       default_date_stop='2026-11-03 12:00:00').create({
                                           'name': 'Synthetic default interval',
                                           'work_entry_type_id': self.assignment.regular_type_id.id}),
            lambda: model.create({k: v for k, v in dict(values, duration=72).items() if k != 'date_stop'}),
            lambda: control.write({'date_stop': '2026-11-03 12:00:00'}),
            lambda: control.write({'duration': 72}),
        ]
        for operation in operations:
            with self.env.cr.savepoint():
                try:
                    operation()
                except AccessError:
                    pass
                else:
                    self.fail('A complete native interval crossed manual source ownership')
                self.env.flush_all()
                self.assertEqual(before, control.read(['date_start', 'date_stop', 'duration', 'employee_id']))
                self.env.cr.execute('SELECT count(*) FROM hr_work_entry WHERE employee_id = %s', (self.employee.id,))
                self.assertEqual(self.env.cr.fetchone()[0], 1)
        control.write({'date_stop': '2026-10-31 12:00:00'})
        self.assertEqual(control.duration, 2)

    def test_historical_contract_and_low_level_native_generation_seams(self):
        from datetime import datetime
        self.contract.date_end = '2026-12-31'
        future = self.env['hr.contract'].create({
            'name': 'Synthetic future contract', 'employee_id': self.employee.id,
            'date_start': '2027-01-01', 'wage': 1, 'state': 'open',
            'resource_calendar_id': self.employee.resource_calendar_id.id,
            'work_entry_source': 'sl_shift_manual',
        })
        self.employee.contract_id = future
        attendance, day, entries = self._approved()
        self.assertEqual(entries.contract_id, self.contract)
        self.assertEqual(sum(entries.mapped('duration')), 10)
        start, stop = datetime(2026, 11, 1), datetime(2026, 12, 1)
        self.assertEqual(self.contract._get_contract_work_entries_values(start, stop), [])
        self.assertEqual(self.contract._get_work_entries_values(start, stop), [])

    def test_long_native_interval_cannot_cross_enabled_shift_from_unmanaged_start(self):
        self.contract.work_entry_source = 'calendar'
        with self.assertRaises(AccessError):
            self.env['hr.work.entry'].with_user(self.actor).create({
                'name': 'Synthetic spanning native interval', 'employee_id': self.employee.id,
                'contract_id': self.contract.id, 'date_start': '2026-10-31 12:00:00',
                'date_stop': '2026-11-03 12:00:00',
                'work_entry_type_id': self.assignment.regular_type_id.id,
            })
