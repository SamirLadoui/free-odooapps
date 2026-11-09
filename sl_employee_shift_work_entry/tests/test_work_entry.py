# SPDX-License-Identifier: LGPL-3.0-or-later
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import uuid

from psycopg2.errors import SerializationFailure

from odoo import Command, fields, SUPERUSER_ID, api
from odoo.exceptions import AccessError, UserError
from odoo.modules.registry import Registry
from odoo.tests import BaseCase, TransactionCase, tagged
from odoo.tests.common import get_db_name, new_test_user


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
        cls.leave_type = cls.env['hr.leave.type'].create({
            'name': 'Synthetic shift overlap leave type',
            'requires_allocation': 'no',
            'time_type': 'leave',
            'request_unit': 'hour',
            'leave_validation_type': 'hr',
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

    def _punch(self, start='2026-11-02 18:00:00', stop='2026-11-03 05:00:00'):
        return self.env['hr.attendance'].create({'employee_id': self.employee.id, 'check_in': start, 'check_out': stop})

    def _calendar_leave(self, start='2026-11-02 19:00:00', stop='2026-11-02 20:00:00'):
        return self.env['resource.calendar.leaves'].create({
            'name': 'Synthetic shift-overlap calendar leave',
            'resource_id': self.employee.resource_id.id,
            'calendar_id': self.employee.resource_calendar_id.id,
            'date_from': start,
            'date_to': stop,
            'time_type': 'leave',
        })

    def _overnight_leave_calendar(self):
        calendar = self.env['resource.calendar'].create({
            'name': 'Synthetic leave interval calendar', 'tz': 'UTC',
            'attendance_ids': [
                Command.create({'name': '%s night' % day, 'dayofweek': str(day),
                                'hour_from': 0, 'hour_to': 4, 'day_period': 'morning'})
                for day in range(7)
            ] + [
                Command.create({'name': '%s day' % day, 'dayofweek': str(day),
                                'hour_from': 8, 'hour_to': 9, 'day_period': 'morning'})
                for day in range(7)
            ] + [
                Command.create({'name': '%s evening' % day, 'dayofweek': str(day),
                                'hour_from': 16, 'hour_to': 22, 'day_period': 'afternoon'})
                for day in range(7)
            ],
        })
        self.employee.resource_calendar_id = calendar
        self.contract.resource_calendar_id = calendar
        return calendar

    def _native_leave(self, leave_date='2026-11-02', start=19, stop=20, leave_type=None):
        requested = date.fromisoformat(leave_date)
        return self.env['hr.leave'].with_context(
            mail_create_nolog=True, mail_notrack=True, mail_create_nosubscribe=True,
            hr_work_entry_no_check=True,
        ).create({
            'name': 'Synthetic shift-overlap leave',
            'employee_id': self.employee.id,
            'holiday_status_id': (leave_type or self.leave_type).id,
            'request_unit_hours': True,
            'request_date_from': requested,
            'request_date_to': requested,
            'request_hour_from': start,
            'request_hour_to': stop,
        })

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
            ('SELECT row_to_json(a) FROM sl_shift_assignment a WHERE id = %s', (self.assignment.id,)),
            ('SELECT row_to_json(c) FROM hr_contract c WHERE id = %s', (self.contract.id,)),
            ('SELECT row_to_json(e) FROM hr_employee e WHERE id = %s', (self.employee.id,)),
            ('SELECT row_to_json(t) FROM hr_work_entry_type t WHERE id IN %s ORDER BY id',
             (tuple((self.assignment.regular_type_id | self.assignment.overtime_type_id).ids),)),
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

    def test_generate_ui_action_is_serializable_and_reuses_native_entries(self):
        attendance, day, entries = self._approved()
        action = day.action_generate_and_open_work_entries()
        self.assertEqual(action['res_model'], 'hr.work.entry')
        self.assertEqual(action['domain'], [('id', 'in', entries.ids)])

    def test_work_entries_generated_audit_replaces_entry_identifiers(self):
        attendance, day, entries = self._approved()
        audit = day.sudo().audit_ids.filtered(
            lambda record: record.event == 'work_entries_generated'
        )[:1]
        evidence = audit.evidence
        self.assertNotIn('entry_ids', evidence)
        self.assertEqual(evidence['entry_count'], len(entries))
        self.assertTrue(evidence['entry_digest'])

    def test_shift_day_relation_ids_follow_native_child_access_in_every_read_api(self):
        attendance, day, entries = self._approved()
        standalone_approver = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-relation-standalone-approver',
            email='synthetic-relation-standalone-approver@example.invalid',
            groups='base.group_user,sl_employee_shift_attendance.group_shift_approver',
        )
        attendance_officer = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-relation-attendance-officer',
            email='synthetic-relation-attendance-officer@example.invalid',
            groups='base.group_user,hr_attendance.group_hr_attendance_officer',
        )
        combined = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-relation-combined',
            email='synthetic-relation-combined@example.invalid',
            groups='base.group_user,hr_attendance.group_hr_attendance_officer,'
                   'sl_employee_shift_attendance.group_shift_approver',
        )
        exact_manager = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-relation-hr-approver',
            email='synthetic-relation-hr-approver@example.invalid',
            groups='base.group_user,hr.group_hr_manager,sl_employee_shift_attendance.group_shift_approver',
        )
        self.employee.attendance_manager_id = attendance_officer

        def read_relation(user, field_name):
            record = day.with_user(user)
            return {
                'read': record.read([field_name])[0][field_name],
                'search_read': record.search_read([('id', '=', day.id)], [field_name])[0][field_name],
                'web_read': record.web_read({field_name: {}})[0][field_name],
            }

        for user in (standalone_approver, exact_manager):
            with self.subTest(user=user.login, field='attendance_ids'):
                for path in ('read', 'search_read', 'web_read'):
                    with self.assertRaises(AccessError):
                        getattr(day.with_user(user), path)(['attendance_ids']) if path == 'read' else (
                            day.with_user(user).search_read([('id', '=', day.id)], ['attendance_ids'])
                            if path == 'search_read' else day.with_user(user).web_read({'attendance_ids': {}})
                        )

        attendance_values = read_relation(attendance_officer, 'attendance_ids')
        self.assertEqual(attendance_values['read'], [attendance.id])
        self.assertEqual(attendance_values['search_read'], [attendance.id])
        self.assertEqual(attendance_values['web_read'], [attendance.id])

        combined_attendance = read_relation(combined, 'attendance_ids')
        self.assertEqual(combined_attendance, {'read': [], 'search_read': [], 'web_read': []})

        for user in (standalone_approver, attendance_officer, combined):
            with self.subTest(user=user.login, field='work_entry_ids'):
                for path in ('read', 'search_read', 'web_read'):
                    with self.assertRaises(AccessError):
                        getattr(day.with_user(user), path)(['work_entry_ids']) if path == 'read' else (
                            day.with_user(user).search_read([('id', '=', day.id)], ['work_entry_ids'])
                            if path == 'search_read' else day.with_user(user).web_read({'work_entry_ids': {}})
                        )

        manager_entries = read_relation(exact_manager, 'work_entry_ids')
        self.assertEqual(manager_entries['read'], entries.ids)
        self.assertEqual(manager_entries['search_read'], entries.ids)
        self.assertEqual(manager_entries['web_read'], entries.ids)

    def test_reverse_shift_day_relation_is_hidden_from_native_hr_readers_everywhere(self):
        attendance, day, entries = self._approved()
        company_b = self.env['res.company'].create({'name': 'Synthetic reverse relation company B'})
        foreign_employee = self.env['hr.employee'].with_company(company_b).create({
            'name': 'Synthetic reverse relation employee B', 'company_id': company_b.id,
        })
        foreign_contract = self.env['hr.contract'].with_company(company_b).create({
            'name': 'Synthetic reverse relation contract B', 'employee_id': foreign_employee.id,
            'company_id': company_b.id, 'date_start': '2026-01-01', 'wage': 1, 'state': 'open',
            'resource_calendar_id': foreign_employee.resource_calendar_id.id,
            'work_entry_source': 'sl_shift_manual',
        })
        foreign_assignment = self.env['sl.shift.assignment'].with_company(company_b).create({
            'employee_id': foreign_employee.id, 'shift_id': self.shift.id,
            'date_from': '2026-11-01', 'date_to': '2026-11-30',
            'attendance_policy': 'shift', 'schedule_tz': 'UTC',
            'workdays': '0,1,2,3,4,5,6', 'break_window_set': True, 'break_start': 22,
            'work_entry_enabled': True,
            'regular_type_id': self.assignment.regular_type_id.id,
            'overtime_type_id': self.assignment.overtime_type_id.id,
        })
        foreign_actor = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-reverse-relation-foreign-actor',
            email='synthetic-reverse-relation-foreign-actor@example.invalid',
            company_id=company_b.id, company_ids=[Command.set([company_b.id])],
            groups='base.group_user,hr.group_hr_manager,hr_attendance.group_hr_attendance_manager,sl_employee_shift_attendance.group_shift_approver',
        )
        foreign_attendance = self.env['hr.attendance'].with_company(company_b).create({
            'employee_id': foreign_employee.id, 'check_in': '2026-11-02 18:00:00',
            'check_out': '2026-11-03 05:00:00',
        })
        foreign_day = foreign_attendance.sl_shift_day_id.with_user(foreign_actor).with_context(
            allowed_company_ids=[company_b.id],
        )
        foreign_day.action_approve(2, 'Synthetic reverse relation foreign approval')
        foreign_entries = foreign_day.action_generate_work_entries()
        self.assertEqual(set(foreign_entries.mapped('sl_shift_day_id').ids), {foreign_day.id})

        readers = (
            new_test_user(
                self.env['res.users'].with_context(no_reset_password=True).env,
                login='slshift-reverse-relation-hr-user',
                email='synthetic-reverse-relation-hr-user@example.invalid',
                company_id=self.env.company.id,
                company_ids=[Command.set([self.env.company.id, company_b.id])],
                groups='base.group_user,hr.group_hr_user,base.group_allow_export',
            ),
            new_test_user(
                self.env['res.users'].with_context(no_reset_password=True).env,
                login='slshift-reverse-relation-hr-manager',
                email='synthetic-reverse-relation-hr-manager@example.invalid',
                company_id=self.env.company.id,
                company_ids=[Command.set([self.env.company.id, company_b.id])],
                groups='base.group_user,hr.group_hr_manager,base.group_allow_export',
            ),
        )
        managed_entries = (entries | foreign_entries).with_context(
            allowed_company_ids=[self.env.company.id, company_b.id],
        )
        for reader in readers:
            with self.subTest(reader=reader.login):
                self.assertFalse(reader.has_group('sl_employee_shift_attendance.group_shift_approver'))
                native_rows = managed_entries.with_user(reader).search_read([], ['id', 'duration'])
                self.assertEqual({row['id'] for row in native_rows}, set(managed_entries.ids))
                self.assertTrue(managed_entries.with_user(reader).export_data(['duration'])['datas'])

                with self.assertRaises(AccessError):
                    managed_entries.with_user(reader).read(['sl_shift_day_id'])
                with self.assertRaises(AccessError):
                    managed_entries.with_user(reader).search_read([], ['sl_shift_day_id'])
                with self.assertRaises(AccessError):
                    managed_entries.with_user(reader).web_read({'sl_shift_day_id': {}})
                with self.assertRaises(AccessError):
                    managed_entries.with_user(reader).web_read({
                        'sl_shift_day_id': {'fields': {'display_name': {}}},
                    })
                with self.assertRaises(AccessError):
                    managed_entries.with_user(reader).export_data(['sl_shift_day_id'])
                with self.assertRaises(AccessError):
                    managed_entries.with_user(reader).export_data(['sl_shift_day_id/display_name'])

    def test_action_validate_rejects_mixed_managed_and_unmanaged_recordsets_atomically(self):
        attendance, day, entries = self._approved()
        other_employee = self.env['hr.employee'].create({'name': 'Synthetic unrelated validation employee'})
        other_contract = self.env['hr.contract'].create({
            'name': 'Synthetic unrelated native contract', 'employee_id': other_employee.id,
            'date_start': '2026-01-01', 'wage': 1, 'state': 'open',
            'resource_calendar_id': other_employee.resource_calendar_id.id,
            'work_entry_source': 'calendar',
        })
        unrelated = self.env['hr.work.entry'].create({
            'name': 'Synthetic unrelated native entry', 'employee_id': other_employee.id,
            'contract_id': other_contract.id, 'date_start': '2026-11-10 09:00:00',
            'date_stop': '2026-11-10 10:00:00',
            'work_entry_type_id': self.assignment.regular_type_id.id,
        })
        self.assertEqual(set(entries.mapped('state')), {'draft'})
        self.assertEqual(unrelated.state, 'draft')

        with self.assertRaises(UserError):
            (entries | unrelated).with_user(self.actor).action_validate()

        self.assertEqual(set(entries.mapped('state')), {'draft'})
        self.assertEqual(unrelated.state, 'draft')

    def test_generation_coverage_rejects_forged_context_and_changes_only_coverage(self):
        from odoo.addons.sl_employee_shift_work_entry.models.bridge import internal

        before = self.contract.read([
            'name', 'employee_id', 'company_id', 'work_entry_source', 'date_start', 'date_end',
            'resource_calendar_id', 'state', 'active', 'date_generated_from',
            'date_generated_to', 'last_generation_date',
        ])[0]
        with self.assertRaises(AccessError):
            self.contract.with_user(self.actor).with_context(
                _sl_shift_capability=True,
            )._sl_update_generation_coverage('2026-11-02 18:00:00', '2026-11-03 05:00:00')
        self.assertEqual(before, self.contract.read(list(before))[0])

        internal(self.contract)._sl_update_generation_coverage(
            '2026-11-02 18:00:00', '2026-11-03 05:00:00',
        )
        after = self.contract.read(list(before))[0]
        for field_name in before:
            if field_name not in {'date_generated_from', 'date_generated_to', 'last_generation_date'}:
                self.assertEqual(after[field_name], before[field_name], field_name)
        self.assertEqual(
            after['date_generated_from'],
            fields.Datetime.to_datetime('2026-11-02 18:00:00'),
        )
        self.assertEqual(
            after['date_generated_to'],
            fields.Datetime.to_datetime('2026-11-03 05:00:00'),
        )
        self.assertEqual(after['last_generation_date'], fields.Date.today())

    def test_native_work_entries_page_is_hidden_for_users_without_native_read_access(self):
        attendance, day, entries = self._approved()
        standalone_approver = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-work-entry-page-approver',
            email='synthetic-work-entry-page-approver@example.invalid',
            groups='base.group_user,sl_employee_shift_attendance.group_shift_approver',
        )
        attendance_officer = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-work-entry-page-officer',
            email='synthetic-work-entry-page-officer@example.invalid',
            groups='base.group_user,hr_attendance.group_hr_attendance_officer',
        )
        self.employee.attendance_manager_id = attendance_officer

        from odoo.tests import Form
        for user in (standalone_approver, attendance_officer):
            with self.subTest(user=user.login):
                self.assertFalse(user.has_group('hr.group_hr_user'))
                self.assertFalse(user.has_group('hr_contract.group_hr_contract_manager'))
                view = day.with_user(user).get_view(
                    view_ref='sl_employee_shift_work_entry.view_shift_day_work_entry_form',
                    view_type='form',
                )
                self.assertNotIn('Native Work Entries', view['arch'])
                form = Form(day.with_user(user))
                self.assertEqual(form.employee_id, self.employee)
                self.assertEqual(form.raw_overtime_hours, 2)

    def test_hr_manager_shift_approver_generates_without_contract_manager_membership(self):
        actor = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-generation-hr-approver',
            email='synthetic-generation-hr-approver@example.invalid',
            groups='base.group_user,hr.group_hr_manager,sl_employee_shift_attendance.group_shift_approver',
        )
        self.assertTrue(actor.has_group('hr.group_hr_manager'))
        self.assertTrue(actor.has_group('sl_employee_shift_attendance.group_shift_approver'))
        self.assertFalse(actor.has_group('hr_contract.group_hr_contract_manager'))

        attendance = self._punch()
        day = attendance.sl_shift_day_id.with_user(actor)
        day.action_approve(2, 'Generation role boundary')
        entries = day.action_generate_work_entries()
        self.assertTrue(entries)
        self.assertEqual(set(entries.mapped('contract_id').ids), {self.contract.id})
        self.assertEqual(day.action_generate_and_open_work_entries()['res_model'], 'hr.work.entry')
        self.assertEqual(
            self.env['hr.work.entry'].with_user(actor).browse(entries.ids).read(['id']),
            [{'id': entry_id} for entry_id in entries.ids],
        )

        approver_only = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-generation-approver-only',
            email='synthetic-generation-approver-only@example.invalid',
            groups='base.group_user,sl_employee_shift_attendance.group_shift_approver',
        )
        hr_only = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-generation-hr-only',
            email='synthetic-generation-hr-only@example.invalid',
            groups='base.group_user,hr.group_hr_manager',
        )
        for user in (approver_only, hr_only):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                day.with_user(user).action_generate_work_entries()

    def test_generate_work_entries_button_requires_both_roles(self):
        approver_only = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-ui-approver-only',
            email='synthetic-ui-approver-only@example.invalid',
            groups='base.group_user,sl_employee_shift_attendance.group_shift_approver',
        )
        hr_only = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-ui-hr-only',
            email='synthetic-ui-hr-only@example.invalid',
            groups='base.group_user,hr.group_hr_manager',
        )
        day = self._punch().sl_shift_day_id

        self.assertTrue(day.with_user(self.actor).can_generate_work_entries)
        self.assertFalse(day.with_user(approver_only).can_generate_work_entries)
        self.assertFalse(day.with_user(hr_only).can_generate_work_entries)

        view = day.with_user(self.actor).get_view(
            view_ref='sl_employee_shift_work_entry.view_shift_day_work_entry_form',
            view_type='form',
        )
        self.assertIn('can_generate_work_entries', view['arch'])
        self.assertIn('not can_generate_work_entries', view['arch'])

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

    def test_manual_generation_tracks_native_contract_coverage(self):
        attendance, day, entries = self._approved()
        self.assertLessEqual(self.contract.date_generated_from, min(entries.mapped('date_start')))
        self.assertGreaterEqual(self.contract.date_generated_to, max(entries.mapped('date_stop')))
        self.assertEqual(self.contract.last_generation_date, fields.Date.today())
        original = self.contract.read(['date_generated_from', 'date_generated_to', 'last_generation_date'])
        day.action_generate_work_entries()
        self.assertEqual(original, self.contract.read(['date_generated_from', 'date_generated_to', 'last_generation_date']))

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
        attendance, day, entries = self._approved()
        other = self.env['hr.employee'].create({'name': 'Synthetic finalized reparent target'})
        company = self.env['res.company'].create({'name': 'Synthetic finalized company target'})
        self.assertTrue(entries.with_user(self.actor).action_validate())
        self.assertEqual(set(entries.mapped('state')), {'validated'})
        baseline = self._snapshot(attendance, day)
        operations = [
            lambda: attendance.with_user(self.actor).write({'check_out': '2026-11-03 04:00:00'}),
            lambda: attendance.with_user(self.actor).write({'check_in': '2026-11-02 19:00:00'}),
            lambda: attendance.with_user(self.actor).write({'employee_id': other.id}),
            lambda: attendance.with_user(self.actor).unlink(),
            lambda: day.action_approve(1, 'Changed closed period'),
            lambda: day.action_refuse('Changed closed period'),
            lambda: entries.with_user(self.actor).write({'duration': 1}),
            lambda: entries.with_user(self.actor).write({'date_stop': '2026-11-03 06:00:00'}),
            lambda: entries.with_user(self.actor).write({'employee_id': other.id}),
            lambda: entries.with_user(self.actor).write({'company_id': company.id}),
            lambda: entries.with_user(self.actor).write({'contract_id': False}),
            lambda: entries.with_user(self.actor).write({'state': 'draft'}),
            lambda: entries.with_user(self.actor).unlink(),
            lambda: self.assignment.with_user(self.actor).write({'break_start': 23}),
            lambda: self.assignment.with_user(self.actor).write({'date_from': '2026-11-02'}),
            lambda: self.assignment.with_user(self.actor).write({'date_to': '2026-11-29'}),
            lambda: self.assignment.with_user(self.actor).write({'employee_id': other.id}),
            lambda: self.assignment.with_user(self.actor).write({'schedule_tz': 'Asia/Dubai'}),
            lambda: self.assignment.with_user(self.actor).write({'attendance_policy': 'off'}),
            lambda: self.contract.with_user(self.actor).write({'work_entry_source': 'calendar'}),
            lambda: self.contract.with_user(self.actor).write({'date_start': '2026-01-02'}),
            lambda: self.contract.with_user(self.actor).write({'date_end': '2026-11-30'}),
            lambda: self.contract.with_user(self.actor).write({'employee_id': other.id}),
            lambda: self.contract.with_user(self.actor).write({'company_id': company.id}),
            lambda: self.contract.with_user(self.actor).unlink(),
            lambda: self.employee.with_user(self.actor).write({'company_id': company.id}),
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
        outside = self._punch('2026-11-03 06:00:00', '2026-11-03 07:00:00')
        self.assertFalse(outside.sl_shift_day_id)
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

    def test_entries_first_blocks_overlapping_calendar_leave_creation(self):
        _attendance, day, entries = self._approved()

        with self.assertRaises(UserError):
            self._calendar_leave()

        self.assertEqual(set(day.work_entry_ids.ids), set(entries.ids))
        self.assertEqual(set(entries.mapped('state')), {'draft'})

    def test_entries_first_blocks_overlapping_calendar_leave_write(self):
        leave = self._calendar_leave(start='2026-11-03 19:00:00',
                                     stop='2026-11-03 20:00:00')
        _attendance, _day, entries = self._approved()

        with self.assertRaises(UserError):
            leave.write({'date_from': '2026-11-02 19:00:00',
                         'date_to': '2026-11-02 20:00:00'})

        self.assertEqual(str(leave.date_from), '2026-11-03 19:00:00')
        self.assertEqual(str(leave.date_to), '2026-11-03 20:00:00')
        self.assertEqual(set(entries.mapped('state')), {'draft'})

    def test_nonoverlapping_calendar_leave_is_allowed_with_manual_entries(self):
        _attendance, _day, entries = self._approved()

        leave = self._calendar_leave(start='2026-11-03 19:00:00',
                                     stop='2026-11-03 20:00:00')

        self.assertTrue(leave)
        self.assertEqual(set(entries.mapped('state')), {'draft'})

    def _native_work_entry(self, start, stop):
        self.assignment.work_entry_enabled = False
        self.contract.work_entry_source = 'calendar'
        return self.env['hr.work.entry'].create({
            'name': 'Synthetic unrelated native entry', 'employee_id': self.employee.id,
            'contract_id': self.contract.id, 'date_start': start, 'date_stop': stop,
            'work_entry_type_id': self.assignment.regular_type_id.id,
        })

    def test_calendar_leave_creation_allows_overlapping_native_work_entry(self):
        entry = self._native_work_entry('2026-11-02 19:00:00', '2026-11-02 20:00:00')
        self.assertFalse(entry.sl_shift_day_id)
        try:
            leave = self._calendar_leave()
        except UserError as error:
            self.fail('An unrelated native work entry blocked time-off creation: %s' % error)
        self.assertTrue(leave)

    def test_calendar_leave_write_allows_overlapping_native_work_entry(self):
        leave = self._calendar_leave(start='2026-11-03 19:00:00',
                                    stop='2026-11-03 20:00:00')
        entry = self._native_work_entry('2026-11-02 19:00:00', '2026-11-02 20:00:00')
        self.assertFalse(entry.sl_shift_day_id)
        try:
            leave.write({'date_from': '2026-11-02 19:00:00',
                         'date_to': '2026-11-02 20:00:00'})
        except UserError as error:
            self.fail('An unrelated native work entry blocked time-off update: %s' % error)
        self.assertEqual(str(leave.date_from), '2026-11-02 19:00:00')
        self.assertEqual(str(leave.date_to), '2026-11-02 20:00:00')

    def test_native_leave_approved_first_blocks_manual_generation(self):
        self._overnight_leave_calendar()
        leave = self._native_leave()
        leave.action_approve()
        self.assertEqual(leave.state, 'validate')

        day = self._punch().sl_shift_day_id.with_user(self.actor)
        with self.assertRaises(UserError):
            day.action_generate_work_entries()

        self.assertFalse(day.work_entry_ids)
        self.assertTrue(self.env['resource.calendar.leaves'].search([('holiday_id', '=', leave.id)]))

    def test_native_leave_approval_after_draft_manual_entries_is_blocked(self):
        self._overnight_leave_calendar()
        _attendance, day, entries = self._approved()
        leave = self._native_leave()

        with self.assertRaises(UserError):
            leave.action_approve()

        self.assertEqual(leave.state, 'confirm')
        self.assertFalse(self.env['resource.calendar.leaves'].search([('holiday_id', '=', leave.id)]))
        self.assertEqual(set(day.work_entry_ids.ids), set(entries.ids))
        self.assertEqual(set(entries.mapped('state')), {'draft'})

    def test_native_leave_overlap_after_midnight_is_blocked_by_exact_interval(self):
        self._overnight_leave_calendar()
        _attendance, day, entries = self._approved()
        leave = self._native_leave('2026-11-03', start=1, stop=2)

        with self.assertRaises(UserError):
            leave.action_approve()

        self.assertEqual(leave.state, 'confirm')
        self.assertFalse(self.env['resource.calendar.leaves'].search([('holiday_id', '=', leave.id)]))
        self.assertEqual(set(day.work_entry_ids.ids), set(entries.ids))

    def test_native_leave_same_date_outside_shift_does_not_block_generation(self):
        self._overnight_leave_calendar()
        leave = self._native_leave('2026-11-02', start=8, stop=9)
        leave.action_approve()

        day = self._punch().sl_shift_day_id.with_user(self.actor)
        entries = day.action_generate_work_entries()

        self.assertEqual(leave.state, 'validate')
        self.assertEqual(sum(entries.mapped('duration')), 8)
        self.assertTrue(all(leave.date_to <= entry.date_start or leave.date_from >= entry.date_stop for entry in entries))

    def test_validated_other_time_type_is_not_an_absence_for_generation(self):
        self._overnight_leave_calendar()
        other_type = self.env['hr.leave.type'].create({
            'name': 'Synthetic worked-time event', 'requires_allocation': 'no',
            'time_type': 'other', 'request_unit': 'hour', 'leave_validation_type': 'hr',
            'work_entry_type_id': self.assignment.regular_type_id.id,
        })
        leave = self._native_leave(leave_date='2026-11-02', start=19, stop=20, leave_type=other_type)
        leave = leave.with_context(hr_work_entry_no_check=False)
        leave.action_approve()

        calendar_leave = self.env['resource.calendar.leaves'].search([('holiday_id', '=', leave.id)])
        self.assertEqual(leave.state, 'validate')
        self.assertEqual(leave.holiday_status_id.time_type, 'other')
        self.assertEqual(calendar_leave.time_type, 'other')

        day = self._punch().sl_shift_day_id.with_user(self.actor)
        entries = day.action_generate_work_entries()
        self.assertEqual(sum(entries.mapped('duration')), 8)

    def test_validated_other_time_type_is_allowed_with_manual_entries(self):
        self._overnight_leave_calendar()
        other_type = self.env['hr.leave.type'].create({
            'name': 'Synthetic overlapping worked-time event', 'requires_allocation': 'no',
            'time_type': 'other', 'request_unit': 'hour', 'leave_validation_type': 'hr',
            'work_entry_type_id': self.assignment.regular_type_id.id,
        })
        _attendance, day, entries = self._approved()
        leave = self._native_leave(leave_date='2026-11-02', start=19, stop=20, leave_type=other_type)
        leave = leave.with_context(hr_work_entry_no_check=False)

        try:
            leave.action_approve()
        except UserError as error:
            self.fail('A worked-time record was treated as an absence over manual work: %s' % error)

        calendar_leave = self.env['resource.calendar.leaves'].search([('holiday_id', '=', leave.id)])
        self.assertEqual(leave.state, 'validate')
        self.assertEqual(calendar_leave.time_type, 'other')
        self.assertEqual(set(entries.mapped('state')), {'draft'})

    def test_native_leave_overnight_next_day_overlap_blocks_generation(self):
        self._overnight_leave_calendar()
        leave = self._native_leave('2026-11-03', start=1, stop=2)
        leave.action_approve()

        day = self._punch().sl_shift_day_id.with_user(self.actor)
        with self.assertRaises(UserError):
            day.action_generate_work_entries()

        self.assertFalse(day.work_entry_ids)
        self.assertEqual(leave.state, 'validate')

    def test_native_leave_same_date_outside_shift_interval_is_allowed(self):
        self._overnight_leave_calendar()
        _attendance, _day, entries = self._approved()
        leave = self._native_leave('2026-11-02', start=8, stop=9)

        leave.action_approve()

        self.assertEqual(leave.state, 'validate')
        self.assertTrue(self.env['resource.calendar.leaves'].search([('holiday_id', '=', leave.id)]))
        self.assertTrue(all(leave.date_to <= entry.date_start or leave.date_from >= entry.date_stop for entry in entries))
        self.assertEqual(set(entries.mapped('state')), {'draft'})

    def test_native_leave_direct_validation_write_after_manual_entries_is_blocked(self):
        self._overnight_leave_calendar()
        _attendance, day, entries = self._approved()
        leave = self._native_leave()

        with self.assertRaises(UserError):
            leave.write({'state': 'validate'})

        self.assertEqual(leave.state, 'confirm')
        self.assertEqual(set(day.work_entry_ids.ids), set(entries.ids))

    def test_combined_validation_and_date_write_checks_effective_interval_atomically(self):
        self._overnight_leave_calendar()
        _attendance, day, entries = self._approved()
        leave = self._native_leave('2026-11-06', start=8, stop=9)
        guarded_leave = leave.with_context(leave_skip_state_check=True, hr_work_entry_no_check=True)
        overlap_values = {
            'state': 'validate',
            'request_date_from': date(2026, 11, 3),
            'request_date_to': date(2026, 11, 3),
            'request_hour_from': 1,
            'request_hour_to': 2,
        }
        self.env.flush_all()
        self.env.cr.execute('SELECT row_to_json(l) FROM hr_leave l WHERE id = %s', (leave.id,))
        before = self.env.cr.fetchone()[0]

        with self.env.cr.savepoint():
            try:
                guarded_leave.write(overlap_values)
            except UserError:
                pass
            else:
                self.fail('A combined direct validation/date write accepted an overlapping proposed interval')
            self.env.flush_all()
            self.env.cr.execute('SELECT row_to_json(l) FROM hr_leave l WHERE id = %s', (leave.id,))
            self.assertEqual(self.env.cr.fetchone()[0], before)
            self.env.cr.execute('SELECT id FROM hr_work_entry WHERE sl_shift_day_id = %s ORDER BY id', (day.id,))
            self.assertEqual([row[0] for row in self.env.cr.fetchall()], sorted(entries.ids))

        leave.invalidate_recordset()
        guarded_leave.write({
            'state': 'validate',
            'request_date_from': date(2026, 11, 7),
            'request_date_to': date(2026, 11, 7),
            'request_hour_from': 8,
            'request_hour_to': 9,
        })
        self.assertEqual(leave.state, 'validate')
        self.assertEqual(leave.request_date_from, date(2026, 11, 7))
        self.assertEqual(leave.request_date_to, date(2026, 11, 7))

    def test_native_leave_approval_after_validated_manual_entries_is_blocked(self):
        self._overnight_leave_calendar()
        _attendance, day, entries = self._approved()
        self.assertTrue(entries.with_user(self.actor).action_validate())
        leave = self._native_leave()

        with self.assertRaises(UserError):
            leave.action_approve()

        self.assertEqual(leave.state, 'confirm')
        self.assertEqual(set(day.work_entry_ids.ids), set(entries.ids))
        self.assertEqual(set(entries.mapped('state')), {'validated'})

    def test_nonoverlapping_native_leave_and_manual_entries_are_allowed(self):
        self._overnight_leave_calendar()
        _attendance, _day, entries = self._approved()
        leave = self._native_leave('2026-11-06')
        leave.action_approve()

        self.assertEqual(leave.state, 'validate')
        self.assertTrue(self.env['resource.calendar.leaves'].search([('holiday_id', '=', leave.id)]))
        self.assertEqual(set(entries.mapped('state')), {'draft'})

    def test_generic_native_creation_cannot_duplicate_enabled_dates_before_punches(self):
        # Even a caller supplying an older calendar version cannot race the
        # explicitly opted-in assignment before its first summary exists.
        self.contract.work_entry_source = 'calendar'
        with self.assertRaises(AccessError):
            self.env['hr.work.entry'].with_user(self.actor).create({
                'employee_id': self.employee.id, 'contract_id': self.contract.id,
                'date_start': '2026-11-02 18:00:00', 'date_stop': '2026-11-03 02:00:00',
                'work_entry_type_id': self.assignment.regular_type_id.id})

    def test_foreign_company_sources_and_decisions_are_not_accessible(self):
        company = self.env['res.company'].create({'name': 'Synthetic foreign bridge company'})
        foreign = self.env['hr.employee'].with_company(company).create({
            'name': 'Synthetic foreign bridge employee', 'company_id': company.id,
        })
        contract = self.env['hr.contract'].with_company(company).create({
            'name': 'Synthetic foreign bridge contract', 'employee_id': foreign.id,
            'company_id': company.id, 'date_start': '2026-01-01', 'wage': 1, 'state': 'open',
            'resource_calendar_id': foreign.resource_calendar_id.id, 'work_entry_source': 'sl_shift_manual',
        })
        assignment = self.env['sl.shift.assignment'].with_company(company).create({
            'employee_id': foreign.id, 'shift_id': self.shift.id, 'date_from': '2026-11-01',
            'date_to': '2026-11-30', 'attendance_policy': 'shift', 'schedule_tz': 'UTC',
            'workdays': '0,1,2,3,4,5,6', 'break_window_set': True, 'break_start': 22,
            'work_entry_enabled': True, 'regular_type_id': self.assignment.regular_type_id.id,
            'overtime_type_id': self.assignment.overtime_type_id.id,
        })
        foreign_actor = new_test_user(self.env, login='slshift-foreign-bridge-actor',
            company_id=company.id, company_ids=[Command.set(company.ids)],
            groups='base.group_user,hr.group_hr_manager,hr_attendance.group_hr_attendance_manager,sl_employee_shift_attendance.group_shift_approver')
        attendance = self.env['hr.attendance'].with_company(company).create({
            'employee_id': foreign.id, 'check_in': '2026-11-02 18:00:00', 'check_out': '2026-11-03 05:00:00',
        })
        day = attendance.sl_shift_day_id.with_user(foreign_actor).with_context(allowed_company_ids=company.ids)
        day.action_approve(2, 'Synthetic foreign-company positive control')
        entries = day.action_generate_work_entries()
        self.assertEqual(sum(entries.mapped('duration')), 10)
        for records, field in ((assignment, 'schedule_tz'), (contract, 'work_entry_source'),
                               (attendance, 'check_in'), (day, 'net_hours'),
                               (day.audit_ids, 'evidence'), (entries, 'duration')):
            with self.subTest(model=records._name), self.assertRaises(AccessError):
                records.with_user(self.actor).with_context(allowed_company_ids=self.env.company.ids).read([field])
        with self.assertRaises(AccessError):
            day.with_user(self.actor).with_context(allowed_company_ids=self.env.company.ids).action_approve(2, 'Foreign attempt')
        with self.assertRaises(AccessError):
            day.with_user(self.actor).with_context(allowed_company_ids=self.env.company.ids).action_generate_work_entries()

    def test_context_default_relational_commands_cannot_forge_authoritative_children(self):
        # This caller never receives the internal capability, including through
        # defaults applied by nested ORM creates.
        attendance = self.env['hr.attendance'].with_context(default_work_entry_ids=[Command.create({
            'employee_id': self.employee.id, 'contract_id': self.contract.id,
            'date_start': '2026-11-03 03:00:00', 'date_stop': '2026-11-04 01:00:00', 'work_entry_type_id': self.assignment.overtime_type_id.id,
        })]).create({'employee_id': self.employee.id, 'check_in': '2026-11-02 18:00:00', 'check_out': '2026-11-03 03:00:00'})
        self.assertFalse(attendance.sl_shift_day_id.work_entry_ids, 'User context defaults forged authoritative work entries')

    def test_long_native_interval_cannot_cross_enabled_shift_from_unmanaged_start(self):
        self.contract.work_entry_source = 'calendar'
        with self.assertRaises(AccessError):
            self.env['hr.work.entry'].with_user(self.actor).create({
                'name': 'Synthetic spanning native interval', 'employee_id': self.employee.id,
                'contract_id': self.contract.id, 'date_start': '2026-10-31 12:00:00',
                'date_stop': '2026-11-03 12:00:00',
                'work_entry_type_id': self.assignment.regular_type_id.id,
            })

    def test_context_default_duration_cannot_cross_into_enabled_shift(self):
        self.contract.work_entry_source = 'calendar'
        entries = self.env['hr.work.entry'].with_user(self.actor).with_context(
            default_employee_id=self.employee.id, default_contract_id=self.contract.id,
            default_date_start='2026-10-31 12:00:00', default_duration=72,
        )
        with self.assertRaises(AccessError):
            entries.create({'name': 'Synthetic default duration span', 'employee_id': self.employee.id,
                            'date_stop': '2026-10-31 13:00:00',
                            'work_entry_type_id': self.assignment.regular_type_id.id})

    def test_unmanaged_interval_expansion_is_denied_before_stored_mutation(self):
        self.contract.work_entry_source = 'calendar'
        entry = self.env['hr.work.entry'].with_user(self.actor).create({
            'name': 'Synthetic unrelated positive control', 'employee_id': self.employee.id,
            'contract_id': self.contract.id, 'date_start': '2026-10-31 12:00:00',
            'date_stop': '2026-10-31 13:00:00',
            'work_entry_type_id': self.assignment.regular_type_id.id,
        })
        entry.write({'duration': 2})
        self.assertEqual(entry.duration, 2)
        self.env.flush_all()
        self.env.cr.execute('SELECT row_to_json(w) FROM hr_work_entry w WHERE id = %s', (entry.id,))
        baseline = self.env.cr.fetchone()
        for values in ({'date_stop': '2026-11-03 12:00:00'}, {'duration': 72},
                       {'date_start': '2026-11-02 18:00:00'}):
            with self.subTest(values=values), self.env.cr.savepoint():
                try:
                    entry.write(values)
                except AccessError:
                    pass
                else:
                    self.fail('An unmanaged interval was expanded into the shift source')
                self.env.flush_all()
                self.env.cr.execute('SELECT row_to_json(w) FROM hr_work_entry w WHERE id = %s', (entry.id,))
                self.assertEqual(self.env.cr.fetchone(), baseline)

    def test_mixed_batch_interval_create_is_atomic(self):
        self.contract.work_entry_source = 'calendar'
        values = {'name': 'Synthetic mixed native batch', 'employee_id': self.employee.id,
                  'contract_id': self.contract.id, 'work_entry_type_id': self.assignment.regular_type_id.id}
        self.env.flush_all()
        self.env.cr.execute('SELECT id FROM hr_work_entry WHERE employee_id = %s ORDER BY id', (self.employee.id,))
        baseline = self.env.cr.fetchall()
        with self.env.cr.savepoint():
            try:
                self.env['hr.work.entry'].with_user(self.actor).create([
                    dict(values, date_start='2026-10-30 12:00:00', date_stop='2026-10-30 13:00:00'),
                    dict(values, date_start='2026-10-31 12:00:00', date_stop='2026-11-03 12:00:00'),
                ])
            except AccessError:
                pass
            else:
                self.fail('A mixed batch inserted an unmanaged overlapping source')
            self.env.flush_all()
            self.env.cr.execute('SELECT id FROM hr_work_entry WHERE employee_id = %s ORDER BY id', (self.employee.id,))
            self.assertEqual(self.env.cr.fetchall(), baseline)

    def test_inferred_manual_contract_cannot_bypass_source_ownership(self):
        self.assignment.work_entry_enabled = False
        with self.assertRaises(AccessError):
            self.env['hr.work.entry'].with_user(self.actor).create({
                'name': 'Synthetic inferred manual contract', 'employee_id': self.employee.id,
                'date_start': '2026-11-02 18:00:00', 'date_stop': '2026-11-03 02:00:00',
                'work_entry_type_id': self.assignment.regular_type_id.id,
            })

    def test_interval_guard_uses_schedule_timezone_and_half_open_edges(self):
        self.contract.work_entry_source = 'calendar'
        self.assignment.write({'schedule_tz': 'Asia/Dubai', 'date_from': '2026-11-02', 'date_to': '2026-11-02'})
        values = {'name': 'Synthetic timezone interval', 'employee_id': self.employee.id,
                  'contract_id': self.contract.id, 'work_entry_type_id': self.assignment.regular_type_id.id}
        entries = self.env['hr.work.entry'].with_user(self.actor)
        control = entries.create(dict(values, date_start='2026-10-31 12:00:00', date_stop='2026-11-02 14:00:00'))
        self.assertTrue(control)
        with self.assertRaises(AccessError):
            entries.create(dict(values, date_start='2026-10-31 12:00:00', date_stop='2026-11-02 14:00:01'))


@tagged('post_install', '-at_install')
class TestConcurrentLeaveGeneration(BaseCase):
    """Independent transactions must serialize leave creation and generation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.registry = Registry(get_db_name())

    def test_leave_creation_and_generation_serialize_with_fresh_retry(self):
        registry = self.registry
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            employee = env['hr.employee'].create({'name': 'Synthetic leave-generation race employee'})
            actor = new_test_user(
                env, login='slshift-race-' + uuid.uuid4().hex[:8],
                groups='base.group_user,hr.group_hr_manager,hr_attendance.group_hr_attendance_manager,sl_employee_shift_attendance.group_shift_approver',
                context={'mail_create_nolog': True, 'mail_notrack': True,
                         'mail_create_nosubscribe': True, 'no_reset_password': True},
            )
            calendar = env['resource.calendar'].create({
                'name': 'Synthetic leave-generation race calendar', 'tz': 'UTC',
                'attendance_ids': [
                    Command.create({'name': '%s night' % day, 'dayofweek': str(day),
                                    'hour_from': 0, 'hour_to': 4, 'day_period': 'morning'})
                    for day in range(7)
                ] + [
                    Command.create({'name': '%s evening' % day, 'dayofweek': str(day),
                                    'hour_from': 16, 'hour_to': 22, 'day_period': 'afternoon'})
                    for day in range(7)
                ],
            })
            employee.resource_calendar_id = calendar
            contract = env['hr.contract'].create({
                'name': 'Synthetic leave-generation race contract', 'employee_id': employee.id,
                'date_start': '2026-01-01', 'wage': 1, 'state': 'open',
                'resource_calendar_id': calendar.id, 'work_entry_source': 'sl_shift_manual',
            })
            shift = env['sl.shift'].create({
                'name': 'Synthetic leave-generation race shift',
                'start_time': 18, 'end_time': 3, 'break_minutes': 60,
            })
            assignment = env['sl.shift.assignment'].create({
                'employee_id': employee.id, 'shift_id': shift.id,
                'date_from': '2026-11-01', 'date_to': '2026-11-30',
                'attendance_policy': 'shift', 'schedule_tz': 'UTC',
                'workdays': '0,1,2,3,4,5,6', 'break_window_set': True, 'break_start': 22,
                'work_entry_enabled': True,
                'regular_type_id': env.ref('hr_work_entry.work_entry_type_attendance').id,
                'overtime_type_id': env.ref('hr_work_entry.overtime_work_entry_type').id,
            })
            leave_type = env['hr.leave.type'].create({
                'name': 'Synthetic automatically approved race leave',
                'requires_allocation': 'no', 'time_type': 'leave', 'request_unit': 'hour',
                'leave_validation_type': 'no_validation',
            })
            attendance = env['hr.attendance'].create({
                'employee_id': employee.id, 'check_in': '2026-11-02 18:00:00',
                'check_out': '2026-11-03 05:00:00',
            })
            day = attendance.sl_shift_day_id
            day.with_user(actor).action_approve(2, 'Synthetic leave-generation race approval')
            ids = (employee.id, actor.id, calendar.id, contract.id, shift.id, assignment.id,
                   leave_type.id, attendance.id, day.id)
            cr.commit()

        employee_id, actor_id, calendar_id, contract_id, shift_id, assignment_id, leave_type_id, attendance_id, day_id = ids
        barrier = Barrier(2)
        leave_values = {
            'name': 'Synthetic automatically approved race leave',
            'employee_id': employee_id, 'holiday_status_id': leave_type_id,
            'request_unit_hours': True,
            'request_date_from': '2026-11-02', 'request_date_to': '2026-11-02',
            'request_hour_from': 19, 'request_hour_to': 20,
        }

        def race(operation):
            with registry.cursor() as cr:
                cr.transaction = api.Transaction(registry)
                env = api.Environment(cr, SUPERUSER_ID, {})
                cr.execute("SET LOCAL lock_timeout = '10s'")
                cr.execute("SET LOCAL statement_timeout = '20s'")
                cr.execute('SHOW transaction_isolation')
                isolation = cr.fetchone()[0].lower()
                env['hr.employee'].browse(employee_id).read(['name'])
                existing_entries = env['hr.work.entry'].search_count([
                    ('employee_id', '=', employee_id), ('sl_shift_day_id', '=', day_id),
                ])
                existing_leaves = env['hr.leave'].search_count([
                    ('employee_id', '=', employee_id), ('state', '=', 'validate'),
                ])
                barrier.wait(timeout=5)
                try:
                    if operation == 'leave':
                        result = env['hr.leave'].with_user(SUPERUSER_ID).with_context(
                            mail_create_nolog=True, mail_notrack=True, mail_create_nosubscribe=True,
                            hr_work_entry_no_check=True,
                        ).create(leave_values)
                    else:
                        result = env['sl.shift.day'].browse(day_id).with_user(actor_id).action_generate_work_entries()
                    cr.commit()
                    return ('committed', operation, isolation, existing_entries, existing_leaves,
                            result.ids if hasattr(result, 'ids') else result)
                except SerializationFailure:
                    cr.rollback()
                    return ('serialization', operation, isolation, existing_entries, existing_leaves, False)
                except Exception as error:
                    cr.rollback()
                    return ('error', operation, isolation, existing_entries, existing_leaves,
                            '%s: %s' % (type(error).__name__, error))

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(race, operation) for operation in ('leave', 'generate')]
                outcomes = [future.result(timeout=30) for future in futures]

            self.assertEqual({outcome[2] for outcome in outcomes}, {'repeatable read'}, outcomes)
            self.assertEqual({(outcome[3], outcome[4]) for outcome in outcomes}, {(0, 0)}, outcomes)
            self.assertEqual([outcome[0] for outcome in outcomes].count('committed'), 1, outcomes)
            self.assertEqual([outcome[0] for outcome in outcomes].count('serialization'), 1, outcomes)
            loser_operation = next(outcome[1] for outcome in outcomes if outcome[0] == 'serialization')

            with registry.cursor() as cr:
                cr.transaction = api.Transaction(registry)
                env = api.Environment(cr, SUPERUSER_ID, {})
                cr.execute("SET LOCAL lock_timeout = '10s'")
                cr.execute("SET LOCAL statement_timeout = '20s'")
                try:
                    if loser_operation == 'leave':
                        env['hr.leave'].with_user(SUPERUSER_ID).with_context(
                            mail_create_nolog=True, mail_notrack=True, mail_create_nosubscribe=True,
                            hr_work_entry_no_check=True,
                        ).create(leave_values)
                    else:
                        env['sl.shift.day'].browse(day_id).with_user(actor_id).action_generate_work_entries()
                except UserError as error:
                    expected = (
                        'This leave overlaps a shift day with manual work entries.'
                        if loser_operation == 'leave'
                        else 'A leave or public holiday overlaps this duty window.'
                    )
                    self.assertIn(expected, str(error))
                    cr.rollback()
                else:
                    cr.rollback()
                    self.fail('The fresh-snapshot retry accepted the conflicting leave or generation')
        finally:
            with registry.cursor() as cr:
                cr.execute('DELETE FROM hr_work_entry WHERE employee_id = %s AND sl_shift_day_id = %s',
                           (employee_id, day_id))
                cr.execute('DELETE FROM resource_calendar_leaves WHERE holiday_id IN '
                           '(SELECT id FROM hr_leave WHERE employee_id = %s)', (employee_id,))
                cr.execute('DELETE FROM mail_message WHERE model = %s AND res_id IN '
                           '(SELECT id FROM hr_leave WHERE employee_id = %s)', ('hr.leave', employee_id))
                cr.execute('DELETE FROM mail_followers WHERE res_model = %s AND res_id IN '
                           '(SELECT id FROM hr_leave WHERE employee_id = %s)', ('hr.leave', employee_id))
                cr.execute('DELETE FROM hr_leave WHERE employee_id = %s', (employee_id,))
                cr.execute('DELETE FROM sl_shift_audit WHERE day_id = %s', (day_id,))
                cr.execute('DELETE FROM hr_attendance WHERE id = %s', (attendance_id,))
                cr.execute('DELETE FROM sl_shift_day WHERE id = %s', (day_id,))
                cr.execute('DELETE FROM sl_shift_assignment WHERE id = %s', (assignment_id,))
                cr.execute('DELETE FROM hr_contract WHERE id = %s', (contract_id,))
                cr.execute('DELETE FROM sl_shift_guard WHERE employee_id = %s', (employee_id,))
                cr.execute('SELECT resource_id FROM hr_employee WHERE id = %s', (employee_id,))
                resource_id = cr.fetchone()[0]
                cr.execute('DELETE FROM hr_employee WHERE id = %s', (employee_id,))
                if resource_id:
                    cr.execute('DELETE FROM resource_resource WHERE id = %s', (resource_id,))
                cr.execute('SELECT partner_id FROM res_users WHERE id = %s', (actor_id,))
                partner_id = cr.fetchone()[0]
                cr.execute('DELETE FROM mail_message WHERE model = %s AND res_id = %s', ('res.users', actor_id))
                cr.execute('DELETE FROM mail_followers WHERE res_model = %s AND res_id = %s', ('res.users', actor_id))
                cr.execute('DELETE FROM res_users WHERE id = %s', (actor_id,))
                if partner_id:
                    cr.execute('DELETE FROM mail_message WHERE model = %s AND res_id = %s', ('res.partner', partner_id))
                    cr.execute('DELETE FROM mail_followers WHERE res_model = %s AND res_id = %s', ('res.partner', partner_id))
                    cr.execute('DELETE FROM res_partner WHERE id = %s', (partner_id,))
                cr.execute('DELETE FROM sl_shift WHERE id = %s', (shift_id,))
                cr.execute('DELETE FROM hr_leave_type WHERE id = %s', (leave_type_id,))
                cr.execute('DELETE FROM resource_calendar WHERE id = %s', (calendar_id,))
                cr.commit()
