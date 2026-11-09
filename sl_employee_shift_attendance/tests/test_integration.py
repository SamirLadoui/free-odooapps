# SPDX-License-Identifier: LGPL-3.0-or-later
from datetime import datetime, timedelta
import json

from odoo import Command, fields
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
        cls.plain_hr = new_test_user(
            cls.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-plain-hr', email='synthetic-plain-hr@example.invalid',
            groups='base.group_user,hr.group_hr_user',
        )

    def _punch(self, start='2026-11-02 18:00:00', stop='2026-11-03 05:00:00', **values):
        return self.env['hr.attendance'].create(dict(employee_id=self.employee.id, check_in=start, check_out=stop, **values))

    def test_summary_regular_raw_approved_presence_and_native_exclusion(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        self.assertTrue(day)
        self.assertEqual((day.elapsed_hours, day.net_hours, day.regular_hours, day.raw_overtime_hours,
                          day.approved_overtime_hours, day.presence_days), (11, 10, 8, 2, 0, 1))
        self.assertFalse(self.env['hr.attendance.overtime'].search([('employee_id', '=', self.employee.id)]))
        self.assertEqual(attendance.expected_hours, 8)

    def test_shift_day_and_audit_details_require_attendance_reader_role(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        audit = day.audit_ids[:1]
        self.assertTrue(audit, 'The fixture must include persisted shift audit evidence')
        self.assertTrue(self.plain_hr.has_group('hr.group_hr_user'))
        self.assertFalse(self.plain_hr.has_group('hr_attendance.group_hr_attendance_officer'))
        self.assertFalse(self.plain_hr.has_group('hr_attendance.group_hr_attendance_manager'))
        self.assertFalse(self.plain_hr.has_group('sl_employee_shift_attendance.group_shift_approver'))

        day_fields = [
            'employee_id', 'shift_date', 'start', 'stop', 'elapsed_hours', 'net_hours',
            'regular_hours', 'raw_overtime_hours', 'approved_overtime_hours',
            'presence_days', 'state', 'digest', 'evidence',
        ]
        audit_fields = [
            'day_id', 'company_id', 'actor_id', 'occurred_at', 'event', 'reason', 'evidence',
        ]
        with self.assertRaises(AccessError):
            self.env['sl.shift.day'].with_user(self.plain_hr).browse(day.id).read(day_fields)
        with self.assertRaises(AccessError):
            self.env['sl.shift.audit'].with_user(self.plain_hr).browse(audit.id).read(audit_fields)

        # The native officer assigned to this employee retains summary/audit reads.
        officer_day = self.env['sl.shift.day'].with_user(self.officer).browse(day.id)
        officer_day_values = officer_day.read(day_fields)[0]
        self.assertEqual(officer_day_values['employee_id'][0], self.employee.id)
        self.assertEqual(officer_day_values['net_hours'], 10)
        officer_audit_values = self.env['sl.shift.audit'].with_user(self.officer).browse(audit.id).read(audit_fields)[0]
        self.assertEqual(officer_audit_values['event'], 'recomputed')
        self.assertTrue(officer_audit_values['occurred_at'])

        # The custom approver keeps read access and the approval workflow.
        approver_day = self.env['sl.shift.day'].with_user(self.approver).browse(day.id)
        approver_day_values = approver_day.read(day_fields)[0]
        self.assertEqual(approver_day_values['raw_overtime_hours'], 2)
        self.assertEqual(
            self.env['sl.shift.audit'].with_user(self.approver).browse(audit.id).read(audit_fields)[0]['event'],
            'recomputed',
        )
        approver_day.action_approve(1, 'ACL positive-control approval')
        self.assertEqual(approver_day.approved_overtime_hours, 1)

        menu_groups = self.env.ref('sl_employee_shift_attendance.menu_shift_day').groups_id
        self.assertIn(self.env.ref('hr_attendance.group_hr_attendance_officer'), menu_groups)
        self.assertIn(self.env.ref('sl_employee_shift_attendance.group_shift_approver'), menu_groups)
        self.assertNotIn(self.env.ref('hr.group_hr_user'), menu_groups)

    def test_restricted_approver_never_receives_raw_punch_evidence_but_native_reader_does(self):
        attendance = self._punch(start='2026-11-02 19:00:00')
        day = attendance.sl_shift_day_id
        audit = day.audit_ids.filtered(lambda record: record.event == 'recomputed')[:1]
        native_reader = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-evidence-native-reader',
            email='synthetic-evidence-native-reader@example.invalid',
            groups='base.group_user,hr_attendance.group_hr_attendance_officer',
        )
        self.employee.attendance_manager_id = native_reader
        self.assertTrue(native_reader.has_group('hr_attendance.group_hr_attendance_officer'))
        self.assertFalse(native_reader.has_group('hr.group_hr_user'))
        self.assertTrue(audit)

        stored_day_evidence = self.env['sl.shift.day'].sudo().browse(day.id).read(['evidence'])[0]['evidence']
        stored_audit_evidence = self.env['sl.shift.audit'].sudo().browse(audit.id).read(['evidence'])[0]['evidence']
        self.assertTrue(stored_day_evidence['punches'])
        self.assertTrue(stored_audit_evidence['punches'])

        restricted_day_evidence = self.env['sl.shift.day'].with_user(self.approver).browse(day.id).read(['evidence'])[0]['evidence']
        restricted_audit_evidence = self.env['sl.shift.audit'].with_user(self.approver).browse(audit.id).read(['evidence'])[0]['evidence']
        self.assertNotIn('punches', restricted_day_evidence)
        self.assertNotIn('punches', restricted_audit_evidence)
        self.assertFalse(any(
            isinstance(value, list) and value and value[0] == attendance.id
            for evidence in (restricted_day_evidence, restricted_audit_evidence)
            for value in evidence.values()
        ))
        self.assertNotIn(str(attendance.check_in), repr(restricted_day_evidence))
        self.assertNotIn(str(attendance.check_out), repr(restricted_day_evidence))
        self.assertNotIn(str(attendance.check_in), repr(restricted_audit_evidence))
        self.assertNotIn(str(attendance.check_out), repr(restricted_audit_evidence))

        native_day_evidence = self.env['sl.shift.day'].with_user(native_reader).browse(day.id).read(['evidence'])[0]['evidence']
        native_audit_evidence = self.env['sl.shift.audit'].with_user(native_reader).browse(audit.id).read(['evidence'])[0]['evidence']
        self.assertEqual(native_day_evidence['punches'][0][0], attendance.id)
        self.assertEqual(native_day_evidence['punches'][0][1], fields.Datetime.to_string(attendance.check_in))
        self.assertEqual(native_day_evidence['punches'][0][2], fields.Datetime.to_string(attendance.check_out))
        self.assertEqual(native_audit_evidence['punches'][0][0], attendance.id)
        self.assertEqual(
            self.env['hr.attendance'].with_user(native_reader).browse(attendance.id).read(['check_in', 'check_out'])[0]['check_in'],
            attendance.check_in,
        )

    def test_restricted_evidence_is_closed_over_all_orm_and_web_output_paths(self):
        attendance = self._punch(start='2026-11-02 19:00:00')
        day = attendance.sl_shift_day_id
        audit = day.audit_ids.filtered(lambda record: record.event == 'recomputed')[:1]
        export_approver = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-evidence-export-approver',
            email='synthetic-evidence-export-approver@example.invalid',
            groups='base.group_user,base.group_allow_export,sl_employee_shift_attendance.group_shift_approver',
        )

        for model, record, group_field in (
            (self.env['sl.shift.day'], day, 'state'),
            (self.env['sl.shift.audit'], audit, 'event'),
        ):
            restricted = model.with_user(export_approver).browse(record.id)
            with self.subTest(model=model._name, path='read'):
                value = restricted.read(['evidence'])[0]['evidence']
                self.assertNotIn('punches', value)
                self.assertNotIn('removed_native_lines', value)
            with self.subTest(model=model._name, path='search_read'):
                value = restricted.search_read([('id', '=', record.id)], ['evidence'])[0]['evidence']
                self.assertNotIn('punches', value)
                self.assertNotIn('removed_native_lines', value)
            with self.subTest(model=model._name, path='web_read'):
                value = restricted.web_read({'evidence': {}})[0]['evidence']
                self.assertNotIn('punches', value)
                self.assertNotIn('removed_native_lines', value)
            with self.subTest(model=model._name, path='export_data'):
                with self.assertRaises(AccessError):
                    restricted.export_data(['evidence'])
            with self.subTest(model=model._name, path='read_group_fields'):
                groups = restricted.read_group(
                    [('id', '=', record.id)], ['__count', 'evidence'], [group_field],
                )
                self.assertTrue(groups)
                self.assertTrue(all('evidence' not in row for row in groups))
            with self.subTest(model=model._name, path='read_group_key'):
                with self.assertRaises(AccessError):
                    restricted.read_group([('id', '=', record.id)], ['__count'], ['evidence'])
                with self.assertRaises(AccessError):
                    restricted.read_group([], ['__count'], ['evidence'])
            with self.subTest(model=model._name, path='web_read_group_fields'):
                groups = restricted.web_read_group(
                    [('id', '=', record.id)], ['__count', 'evidence'], [group_field],
                )
                self.assertTrue(groups['groups'])
                self.assertTrue(all('evidence' not in row for row in groups['groups']))
            with self.subTest(model=model._name, path='web_read_group_key'):
                with self.assertRaises(AccessError):
                    restricted.web_read_group(
                        [('id', '=', record.id)], ['__count'], ['evidence'],
                    )

    def test_nested_relational_evidence_exports_are_guarded_and_manager_authorized(self):
        attendance = self._punch(start='2026-11-02 19:00:00')
        day = attendance.sl_shift_day_id
        audit = day.audit_ids.filtered(lambda record: record.event == 'recomputed')[:1]
        self.assertTrue(audit, 'The fixture must include persisted shift audit evidence')
        clean_day_evidence = dict(day.sudo().evidence)
        clean_audit_evidence = dict(audit.sudo().evidence)
        self.assertTrue(clean_day_evidence['punches'], 'The parent evidence must remain clean and valid')
        self.assertTrue(clean_audit_evidence['punches'], 'The child evidence must start clean and valid')

        restricted = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-relational-evidence-export-officer',
            email='synthetic-relational-evidence-export-officer@example.invalid',
            groups='base.group_user,base.group_allow_export,hr_attendance.group_hr_attendance_officer',
        )
        self.employee.attendance_manager_id = restricted
        manager = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-relational-evidence-export-manager',
            email='synthetic-relational-evidence-export-manager@example.invalid',
            groups='base.group_user,base.group_allow_export,hr_attendance.group_hr_attendance_manager',
        )

        direct_parent = self.env['sl.shift.day'].with_user(restricted).browse(day.id).export_data(['evidence'])
        self.assertEqual(json.loads(direct_parent['datas'][0][0])['punches'][0][0], attendance.id)

        child_evidence_variants = (
            ('malformed', {'punches': 'not-a-list', 'label': 'malformed-child-evidence'}),
            ('scalar', 'legacy scalar child evidence'),
            ('mixed', {
                'attendance_ids': [attendance.id, 'mixed'],
                'entry_ids': [987654, {'id': 987655}],
                'label': 'mixed-child-evidence',
            }),
            ('nested', {
                'nested': {
                    'attendance_ids': [attendance.id],
                    'entry_ids': [987656],
                },
                'label': 'nested-child-evidence',
            }),
            ('removed_native_lines', {
                'removed_native_lines': [{'date': '2026-11-02', 'duration': 2}],
                'label': 'removed-native-child-evidence',
            }),
        )
        day_paths = (
            (self.env['sl.shift.day'], day, 'audit_ids/evidence'),
            (self.env['sl.shift.day'], day, 'audit_ids/evidence/punches'),
        )
        audit_paths = (
            (self.env['sl.shift.audit'], audit, 'day_id/evidence'),
            (self.env['sl.shift.audit'], audit, 'day_id/evidence/punches'),
        )

        for variant, evidence in child_evidence_variants:
            with self.subTest(root='sl.shift.day', variant=variant):
                self.env.cr.execute(
                    'UPDATE sl_shift_day SET evidence = %s::jsonb WHERE id = %s',
                    (json.dumps(clean_day_evidence), day.id),
                )
                self.env.cr.execute(
                    'UPDATE sl_shift_audit SET evidence = %s::jsonb WHERE id = %s',
                    (json.dumps(evidence), audit.id),
                )
                self.env['sl.shift.day'].invalidate_model(['evidence'])
                self.env['sl.shift.audit'].invalidate_model(['evidence'])

                for model, record, path in day_paths:
                    with self.subTest(user='restricted', path=path):
                        with self.assertRaises(AccessError):
                            model.with_user(restricted).browse(record.id).export_data([path])
                for model, record, path in day_paths:
                    with self.subTest(user='manager', path=path):
                        self.assertTrue(model.with_user(manager).browse(record.id).export_data([path])['datas'])

            with self.subTest(root='sl.shift.audit', variant=variant):
                self.env.cr.execute(
                    'UPDATE sl_shift_day SET evidence = %s::jsonb WHERE id = %s',
                    (json.dumps(evidence), day.id),
                )
                self.env.cr.execute(
                    'UPDATE sl_shift_audit SET evidence = %s::jsonb WHERE id = %s',
                    (json.dumps(clean_audit_evidence), audit.id),
                )
                self.env['sl.shift.day'].invalidate_model(['evidence'])
                self.env['sl.shift.audit'].invalidate_model(['evidence'])

                for model, record, path in audit_paths:
                    with self.subTest(user='restricted', path=path):
                        with self.assertRaises(AccessError):
                            model.with_user(restricted).browse(record.id).export_data([path])
                for model, record, path in audit_paths:
                    with self.subTest(user='manager', path=path):
                        self.assertTrue(model.with_user(manager).browse(record.id).export_data([path])['datas'])

    def test_combined_officer_raw_evidence_stays_within_native_employee_scope(self):
        own_attendance = self._punch(start='2026-11-02 19:00:00')
        own_day = own_attendance.sl_shift_day_id
        other_employee = self.env['hr.employee'].create({'name': 'Synthetic other evidence employee'})
        self.env['sl.shift.assignment'].create({
            'employee_id': other_employee.id, 'shift_id': self.shift.id,
            'date_from': '2026-11-01', 'date_to': '2026-11-30',
            'attendance_policy': 'shift', 'schedule_tz': 'UTC',
            'workdays': '0,1,2,3,4,5,6', 'break_window_set': True, 'break_start': 22,
        })
        other_attendance = self.env['hr.attendance'].create({
            'employee_id': other_employee.id, 'check_in': '2026-11-02 19:00:00',
            'check_out': '2026-11-03 05:00:00',
        })
        other_day = other_attendance.sl_shift_day_id
        combined = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-combined-evidence-officer',
            email='synthetic-combined-evidence-officer@example.invalid',
            groups='base.group_user,hr_attendance.group_hr_attendance_officer,'
                   'sl_employee_shift_attendance.group_shift_approver',
        )
        self.employee.attendance_manager_id = combined
        manager = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-company-evidence-manager',
            email='synthetic-company-evidence-manager@example.invalid',
            groups='base.group_user,hr_attendance.group_hr_attendance_manager',
        )

        own_evidence = own_day.with_user(combined).read(['evidence'])[0]['evidence']
        self.assertTrue(own_evidence['punches'])
        other_evidence = other_day.with_user(combined).read(['evidence'])[0]['evidence']
        self.assertNotIn('punches', other_evidence)
        company_evidence = other_day.with_user(manager).read(['evidence'])[0]['evidence']
        self.assertEqual(company_evidence['punches'][0][0], other_attendance.id)

    def test_audit_payload_replaces_child_identifiers_with_counts_and_digests(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        self.assignment.with_user(self.admin).action_repair_attendance(False, 'Identifier-free repair audit')
        audit = day.audit_ids.filtered(lambda record: record.event == 'repair')[-1]
        evidence = audit.sudo().evidence
        self.assertNotIn('attendance_ids', evidence)
        self.assertEqual(evidence['attendance_count'], 1)
        self.assertTrue(evidence['attendance_digest'])

    def test_legacy_audit_identifier_evidence_is_redacted_at_read_time(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        legacy_evidence = {
            'attendance_ids': [attendance.id],
            'entry_ids': [987654],
            'nested': {
                'attendance_ids': [attendance.id, attendance.id + 1],
                'entry_ids': [987654, 987655],
            },
            'label': 'legacy-audit-row',
        }
        now = fields.Datetime.now()
        self.env.cr.execute(
            """
                INSERT INTO sl_shift_audit (
                    day_id, company_id, actor_id, occurred_at, event, reason, evidence,
                    create_uid, create_date, write_uid, write_date
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                RETURNING id
            """,
            (
                day.id, self.env.company.id, self.env.uid, now, 'legacy',
                'Legacy raw identifier evidence', json.dumps(legacy_evidence),
                self.env.uid, now, self.env.uid, now,
            ),
        )
        legacy_audit_id = self.env.cr.fetchone()[0]
        self.env['sl.shift.audit'].invalidate_model()

        restricted = self.env['sl.shift.audit'].with_user(self.approver).browse(legacy_audit_id)
        manager = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-legacy-evidence-manager',
            email='synthetic-legacy-evidence-manager@example.invalid',
            groups='base.group_user,hr_attendance.group_hr_attendance_manager',
        )
        restricted_rows = [
            restricted.read(['evidence'])[0],
            restricted.search_read([('id', '=', legacy_audit_id)], ['evidence'])[0],
            restricted.web_read({'evidence': {}})[0],
        ]
        self.assertEqual(restricted_rows[0]['evidence'], restricted_rows[1]['evidence'])
        self.assertEqual(restricted_rows[0]['evidence'], restricted_rows[2]['evidence'])
        for row in restricted_rows:
            evidence = row['evidence']
            self.assertNotIn('attendance_ids', evidence)
            self.assertNotIn('entry_ids', evidence)
            self.assertEqual(evidence['attendance_count'], 1)
            self.assertRegex(evidence['attendance_digest'], r'^[0-9a-f]{64}$')
            self.assertEqual(evidence['entry_count'], 1)
            self.assertRegex(evidence['entry_digest'], r'^[0-9a-f]{64}$')
            self.assertEqual(evidence['nested']['attendance_count'], 2)
            self.assertRegex(evidence['nested']['attendance_digest'], r'^[0-9a-f]{64}$')
            self.assertEqual(evidence['nested']['entry_count'], 2)
            self.assertRegex(evidence['nested']['entry_digest'], r'^[0-9a-f]{64}$')
            self.assertEqual(evidence['label'], 'legacy-audit-row')

        # Read-time fallback is idempotent and does not change native manager scope.
        manager_evidence = self.env['sl.shift.audit'].with_user(manager).browse(legacy_audit_id).read(['evidence'])[0]['evidence']
        self.assertEqual(manager_evidence['attendance_ids'], [attendance.id])
        self.assertEqual(manager_evidence['entry_ids'], [987654])
        self.assertEqual(manager_evidence['nested']['attendance_ids'], [attendance.id, attendance.id + 1])
        self.assertEqual(manager_evidence['nested']['entry_ids'], [987654, 987655])

    def test_restricted_scalar_legacy_evidence_uses_a_safe_marker_on_all_json_reads(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        audit = day.audit_ids[:1]
        scalar = 'legacy scalar evidence must not be disclosed'
        self.env.cr.execute(
            'UPDATE sl_shift_day SET evidence = %s::jsonb WHERE id = %s',
            (json.dumps(scalar), day.id),
        )
        self.env.cr.execute(
            'UPDATE sl_shift_audit SET evidence = %s::jsonb WHERE id = %s',
            (json.dumps(scalar), audit.id),
        )
        self.env['sl.shift.day'].invalidate_model(['evidence'])
        self.env['sl.shift.audit'].invalidate_model(['evidence'])

        manager = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-scalar-evidence-manager',
            email='synthetic-scalar-evidence-manager@example.invalid',
            groups='base.group_user,hr_attendance.group_hr_attendance_manager',
        )
        for model, record in ((self.env['sl.shift.day'], day), (self.env['sl.shift.audit'], audit)):
            restricted = model.with_user(self.approver).browse(record.id)
            for path, value in (
                ('read', restricted.read(['evidence'])[0]['evidence']),
                ('search_read', restricted.search_read([('id', '=', record.id)], ['evidence'])[0]['evidence']),
                ('web_read', restricted.web_read({'evidence': {}})[0]['evidence']),
            ):
                with self.subTest(model=model._name, path=path):
                    self.assertEqual(value, {'redacted': True})
                    self.assertNotIn(scalar, repr(value))

            manager_value = model.with_user(manager).browse(record.id).read(['evidence'])[0]['evidence']
            self.assertEqual(manager_value, scalar)

    def test_mixed_identifier_lists_are_recursively_canonicalized_and_idempotent(self):
        from odoo.addons.sl_employee_shift_attendance.models.summary import _sanitize_audit_evidence

        attendance = self._punch()
        day = attendance.sl_shift_day_id
        audit = day.audit_ids[:1]
        legacy_evidence = {
            'attendance_ids': [attendance.id, '2'],
            'entry_ids': [1, {'id': 2}],
            'nested': {
                'attendance_ids': [{'id': attendance.id}, 1],
                'entry_ids': ['2', 1],
            },
            'label': 'mixed-legacy-audit-row',
        }
        self.env.cr.execute(
            'UPDATE sl_shift_audit SET evidence = %s::jsonb WHERE id = %s',
            (json.dumps(legacy_evidence), audit.id),
        )
        self.env['sl.shift.audit'].invalidate_model(['evidence'])

        sanitized = _sanitize_audit_evidence(legacy_evidence)
        self.assertEqual(sanitized, _sanitize_audit_evidence(sanitized))

        restricted = self.env['sl.shift.audit'].with_user(self.approver).browse(audit.id)
        values = [
            restricted.read(['evidence'])[0]['evidence'],
            restricted.search_read([('id', '=', audit.id)], ['evidence'])[0]['evidence'],
            restricted.web_read({'evidence': {}})[0]['evidence'],
        ]
        self.assertEqual(values[0], values[1])
        self.assertEqual(values[0], values[2])
        evidence = values[0]
        self.assertEqual(evidence['attendance_count'], 2)
        self.assertRegex(evidence['attendance_digest'], r'^[0-9a-f]{64}$')
        self.assertEqual(evidence['entry_count'], 2)
        self.assertRegex(evidence['entry_digest'], r'^[0-9a-f]{64}$')
        self.assertEqual(evidence['nested']['attendance_count'], 2)
        self.assertRegex(evidence['nested']['attendance_digest'], r'^[0-9a-f]{64}$')
        self.assertEqual(evidence['nested']['entry_count'], 2)
        self.assertRegex(evidence['nested']['entry_digest'], r'^[0-9a-f]{64}$')
        self.assertEqual(evidence['label'], 'mixed-legacy-audit-row')

    def test_nested_forbidden_evidence_denies_officer_raw_reads_but_not_manager_reads(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        audit = day.audit_ids[:1]
        legacy_evidence = {
            'nested': {
                'attendance_ids': [attendance.id],
                'entry_ids': [987654],
                'removed_native_lines': [{'duration': 11}],
            },
            'label': 'nested-forbidden-evidence',
        }
        self.env.cr.execute(
            'UPDATE sl_shift_day SET evidence = %s::jsonb WHERE id = %s',
            (json.dumps(legacy_evidence), day.id),
        )
        self.env.cr.execute(
            'UPDATE sl_shift_audit SET evidence = %s::jsonb WHERE id = %s',
            (json.dumps(legacy_evidence), audit.id),
        )
        self.env['sl.shift.day'].invalidate_model(['evidence'])
        self.env['sl.shift.audit'].invalidate_model(['evidence'])

        native_reader = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-nested-evidence-native-reader',
            email='synthetic-nested-evidence-native-reader@example.invalid',
            groups='base.group_user,hr_attendance.group_hr_attendance_officer',
        )
        self.employee.attendance_manager_id = native_reader
        manager = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-nested-evidence-manager',
            email='synthetic-nested-evidence-manager@example.invalid',
            groups='base.group_user,hr_attendance.group_hr_attendance_manager',
        )

        for model, record in ((self.env['sl.shift.day'], day), (self.env['sl.shift.audit'], audit)):
            officer = model.with_user(native_reader).browse(record.id)
            for path, value in (
                ('read', officer.read(['evidence'])[0]['evidence']),
                ('search_read', officer.search_read([('id', '=', record.id)], ['evidence'])[0]['evidence']),
                ('web_read', officer.web_read({'evidence': {}})[0]['evidence']),
            ):
                with self.subTest(model=model._name, path=path):
                    self.assertNotIn('attendance_ids', value['nested'])
                    self.assertNotIn('entry_ids', value['nested'])
                    self.assertNotIn('removed_native_lines', value['nested'])
                    self.assertEqual(value['nested']['attendance_count'], 1)
                    self.assertEqual(value['nested']['entry_count'], 1)
                    self.assertEqual(value['label'], 'nested-forbidden-evidence')

            manager_value = model.with_user(manager).browse(record.id).read(['evidence'])[0]['evidence']
            self.assertEqual(manager_value, legacy_evidence)

    def test_malformed_punch_structures_fail_closed_for_officers_and_stay_raw_for_managers(self):
        attendance = self._punch()
        day = attendance.sl_shift_day_id
        native_reader = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-malformed-punch-native-reader',
            email='synthetic-malformed-punch-native-reader@example.invalid',
            groups='base.group_user,hr_attendance.group_hr_attendance_officer',
        )
        self.employee.attendance_manager_id = native_reader
        manager = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-malformed-punch-manager',
            email='synthetic-malformed-punch-manager@example.invalid',
            groups='base.group_user,hr_attendance.group_hr_attendance_manager',
        )
        malformed_values = (
            42,
            None,
            {'id': attendance.id},
            [[True]],
            [[attendance.id], {'id': attendance.id}],
        )
        for malformed_punches in malformed_values:
            with self.subTest(punches=repr(malformed_punches)):
                evidence = {'punches': malformed_punches, 'label': 'malformed-punch'}
                self.env.cr.execute(
                    'UPDATE sl_shift_day SET evidence = %s::jsonb WHERE id = %s',
                    (json.dumps(evidence), day.id),
                )
                self.env['sl.shift.day'].invalidate_model(['evidence'])
                restricted = self.env['sl.shift.day'].with_user(native_reader).browse(day.id)
                values = [
                    restricted.read(['evidence'])[0]['evidence'],
                    restricted.search_read([('id', '=', day.id)], ['evidence'])[0]['evidence'],
                    restricted.web_read({'evidence': {}})[0]['evidence'],
                ]
                self.assertTrue(all('punches' not in value for value in values))
                self.assertTrue(all(value['label'] == 'malformed-punch' for value in values))
                manager_value = self.env['sl.shift.day'].with_user(manager).browse(day.id).read(['evidence'])[0]['evidence']
                self.assertEqual(manager_value, evidence)

    def test_attendance_officer_scope_matches_native_employee_assignment(self):
        employee = self.env['hr.employee'].create({'name': 'Synthetic unassigned shift employee'})
        self.env['sl.shift.assignment'].create({
            'employee_id': employee.id, 'shift_id': self.shift.id,
            'date_from': '2026-11-01', 'date_to': '2026-11-30',
            'attendance_policy': 'shift', 'schedule_tz': 'UTC',
            'workdays': '0,1,2,3,4,5,6', 'break_window_set': True, 'break_start': 22,
        })
        attendance = self.env['hr.attendance'].create({
            'employee_id': employee.id, 'check_in': '2026-11-02 18:00:00',
            'check_out': '2026-11-03 05:00:00',
        })
        day = attendance.sl_shift_day_id
        audit = day.audit_ids[:1]

        with self.assertRaises(AccessError):
            self.env['sl.shift.day'].with_user(self.officer).browse(day.id).read(['net_hours'])
        with self.assertRaises(AccessError):
            self.env['sl.shift.audit'].with_user(self.officer).browse(audit.id).read(['event'])

        attendance_admin = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-attendance-admin-only',
            email='synthetic-attendance-admin@example.invalid',
            groups='base.group_user,hr_attendance.group_hr_attendance_manager',
        )
        self.assertTrue(attendance_admin.has_group('hr_attendance.group_hr_attendance_manager'))
        self.assertFalse(attendance_admin.has_group('sl_employee_shift_attendance.group_shift_approver'))
        self.assertEqual(
            self.env['sl.shift.day'].with_user(attendance_admin).browse(day.id).read(['net_hours'])[0]['net_hours'],
            10,
        )
        self.assertEqual(
            self.env['sl.shift.audit'].with_user(attendance_admin).browse(audit.id).read(['event'])[0]['event'],
            'recomputed',
        )

        combined_approver = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-attendance-approver',
            email='synthetic-attendance-approver@example.invalid',
            groups='base.group_user,hr_attendance.group_hr_attendance_officer,'
                   'sl_employee_shift_attendance.group_shift_approver',
        )
        self.assertTrue(combined_approver.has_group('hr_attendance.group_hr_attendance_officer'))
        self.assertTrue(combined_approver.has_group('sl_employee_shift_attendance.group_shift_approver'))
        self.assertEqual(
            self.env['sl.shift.day'].with_user(combined_approver).browse(day.id).read(['net_hours'])[0]['net_hours'],
            10,
        )
        self.assertEqual(
            self.env['sl.shift.audit'].with_user(combined_approver).browse(audit.id).read(['event'])[0]['event'],
            'recomputed',
        )

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

    def test_shift_approver_cannot_approve_own_employee_shift_day(self):
        self.employee.user_id = self.approver
        day = self._punch().sl_shift_day_id.with_user(self.approver)

        with self.assertRaises(AccessError):
            day.action_approve(2, 'Self approval must be denied')

        self.assertEqual(day.state, 'pending')
        self.assertFalse(day.approver_id)

    def test_standalone_approver_can_open_summary_without_original_punches(self):
        from odoo.tests import Form

        day = self._punch().sl_shift_day_id.with_user(self.approver)
        view = day.get_view(view_ref='sl_employee_shift_attendance.view_shift_day_form', view_type='form')
        self.assertNotIn('Original Punches', view['arch'])

        form = Form(day)
        self.assertEqual(form.employee_id, self.employee)
        self.assertEqual(form.raw_overtime_hours, 2)

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
        # A real empty calendar makes all elapsed time native daily overtime.
        # Only this synthetic employee is changed, never the company calendar.
        calendar = self.env['resource.calendar'].create({
            'name': 'Synthetic empty native daily calendar', 'tz': 'UTC',
            'attendance_ids': [Command.clear()],
        })
        self.employee.resource_calendar_id = calendar
        # Native18 has no legacy overtime enable/start flags.

    def _flexible_weekly_calendar(self):
        calendar = self.env['resource.calendar'].create({
            'name': 'Synthetic flexible weekly calendar', 'tz': 'UTC',
            'hours_per_day': 8, 'flexible_hours': True,
            'full_time_required_hours': 40,
        })
        self.employee.resource_calendar_id = calendar
        return calendar

    def test_flexible_weekly_overtime_outside_assignment_dates_is_allowed(self):
        self._flexible_weekly_calendar()
        try:
            attendance = self._punch('2026-12-07 09:00:00', '2026-12-07 17:00:00')
        except UserError as error:
            self.fail('A disjoint native weekly range was blocked by an unrelated shift assignment: %s' % error)
        self.assertTrue(attendance.exists())

    def test_flexible_weekly_overtime_rejects_mixed_overlapping_week(self):
        self._flexible_weekly_calendar()
        self.assignment.workdays = '0,1,2,3,4'
        managed = self._punch('2026-11-02 18:00:00', '2026-11-03 05:00:00')
        self.assertTrue(managed.sl_shift_day_id)

        with self.assertRaises(UserError):
            self._punch('2026-11-08 09:00:00', '2026-11-08 12:00:00')

    def test_flexible_weekly_managed_overnight_stays_out_of_native_overtime(self):
        self._flexible_weekly_calendar()
        self.assignment.workdays = '0,1,2,3,4'
        attendance = self._punch('2026-11-06 18:00:00', '2026-11-07 05:00:00')
        self.assertTrue(attendance.sl_shift_day_id)
        self.assertEqual(attendance.sl_shift_day_id.raw_overtime_hours, 2)
        self.assertFalse(self.env['hr.attendance.overtime'].search([
            ('employee_id', '=', self.employee.id), ('adjustment', '=', False),
        ]))

    def test_pending_native_history_is_reconciled_to_one_authoritative_engine(self):
        self.assignment.attendance_policy = 'off'
        self.env.company.attendance_overtime_validation = 'by_manager'
        self._explicit_native_wrong_ruleset()
        attendance = self._punch()
        native = self.env['hr.attendance.overtime'].search([('employee_id', '=', self.employee.id)])
        self.assertTrue(native)
        self.assertEqual(set(attendance.mapped('overtime_status')), {'to_approve'})
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
        native = self.env['hr.attendance.overtime'].search([('employee_id', '=', self.employee.id)])
        original_ids = native.ids
        self.assertEqual(set(attendance.mapped('overtime_status')), {'approved'})
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
        self.assertFalse(self.env['hr.attendance.overtime'].search([('employee_id', '=', self.employee.id), ('date', '=', friday.check_in.date()), ('adjustment', '=', False)]))

    def test_check_in_must_be_inside_scheduled_interval(self):
        outside = self._punch('2026-11-02 09:00:00', '2026-11-02 10:00:00')
        self.assertFalse(outside.sl_shift_day_id)
        self.assertEqual(outside.worked_hours, 1)

    def test_overtime_checkout_after_scheduled_stop_remains_managed(self):
        overtime = self._punch('2026-11-02 18:00:00', '2026-11-03 05:00:00')
        self.assertTrue(overtime.sl_shift_day_id)
        self.assertEqual(overtime.sl_shift_day_id.shift_date, fields.Date.to_date('2026-11-02'))
        self.assertEqual((overtime.sl_shift_day_id.net_hours, overtime.sl_shift_day_id.raw_overtime_hours), (10, 2))

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

    def test_shared_shift_time_change_rejects_unallowed_historical_company_assignment(self):
        company_b = self.env['res.company'].create({'name': 'Synthetic shared shift company B'})
        employee_b = self.env['hr.employee'].with_company(company_b).create({
            'name': 'Synthetic shared shift employee B', 'company_id': company_b.id,
        })
        assignment_b = self.env['sl.shift.assignment'].with_company(company_b).create({
            'employee_id': employee_b.id, 'shift_id': self.shift.id,
            'date_from': '2025-01-01', 'date_to': '2025-01-31',
            'attendance_policy': 'off',
        })
        self.assertEqual(assignment_b.company_id, company_b)
        restricted = new_test_user(
            self.env, login='slshift-company-a-shift-config',
            company_id=self.env.company.id,
            company_ids=[Command.set([self.env.company.id])],
            groups='base.group_user,hr.group_hr_manager,hr_attendance.group_hr_attendance_manager',
        )
        before = self.shift.read(['start_time', 'end_time', 'break_minutes'])

        with self.assertRaises(AccessError):
            self.shift.with_user(restricted).with_context(
                allowed_company_ids=[self.env.company.id],
            ).write({'start_time': 19})

        self.assertEqual(before, self.shift.read(['start_time', 'end_time', 'break_minutes']))

    def test_authorized_same_company_manager_can_change_shared_shift_time(self):
        before = self.shift.start_time

        self.shift.with_user(self.admin).with_context(
            allowed_company_ids=[self.env.company.id],
        ).write({'start_time': 19})

        self.assertEqual(self.shift.start_time, 19)
        self.assertNotEqual(self.shift.start_time, before)

    def test_opted_template_metadata_writes_require_both_admin_roles(self):
        hr_manager = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-hr-only-metadata',
            email='synthetic-hr-only-metadata@example.invalid',
            groups='base.group_user,hr.group_hr_manager',
        )
        self.assertTrue(hr_manager.has_group('hr.group_hr_manager'))
        self.assertFalse(hr_manager.has_group('hr_attendance.group_hr_attendance_manager'))
        self.shift.with_user(hr_manager).check_access('write')

        # Archived assignments remain authoritative references for this gate.
        self.assignment.active = False
        self.assertTrue(self.env['sl.shift.assignment'].with_context(active_test=False).search_count([
            ('id', '=', self.assignment.id), ('attendance_policy', '=', 'shift'),
            ('shift_id', '=', self.shift.id),
        ]))

        metadata_edits = (
            ('name', 'Synthetic renamed opted template'),
            ('code', 'META-RENAMED'),
            ('color', 7),
            ('active', False),
        )
        for field_name, value in metadata_edits:
            self.env.cr.execute(
                'SELECT name, code, color, active FROM sl_shift WHERE id = %s',
                (self.shift.id,),
            )
            before = self.env.cr.fetchone()
            with self.env.cr.savepoint():
                try:
                    self.shift.with_user(hr_manager).write({field_name: value})
                except AccessError as error:
                    self.assertIn('HR and Attendance administrator roles', str(error))
                else:
                    self.fail('HR-only manager edited opted-in template field %s' % field_name)
                self.env.flush_all()
                self.env.cr.execute(
                    'SELECT name, code, color, active FROM sl_shift WHERE id = %s',
                    (self.shift.id,),
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
            self.shift.with_user(self.admin).write({field_name: value})
            self.assertEqual(self.shift.with_user(self.admin)[field_name], value)

        # The role gate is opt-in scoped, not a blanket restriction on shifts.
        unassigned = self.env['sl.shift'].create({
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
            unassigned.with_user(hr_manager).write({field_name: value})
            self.assertEqual(unassigned.with_user(hr_manager)[field_name], value)

        non_opted_employee = self.env['hr.employee'].create({'name': 'Synthetic non-opted metadata control'})
        non_opted = self.env['sl.shift'].create({
            'name': 'Synthetic non-opted metadata template', 'code': 'META-OFF',
            'color': 3, 'start_time': 8, 'end_time': 16,
        })
        self.env['sl.shift.assignment'].create({
            'employee_id': non_opted_employee.id, 'shift_id': non_opted.id,
            'date_from': '2026-11-01', 'attendance_policy': 'off',
        })
        non_opted_edits = (
            ('name', 'Synthetic edited non-opted template'),
            ('code', 'META-OFF-EDITED'),
            ('color', 6),
            ('active', False),
        )
        for field_name, value in non_opted_edits:
            non_opted.with_user(hr_manager).write({field_name: value})
            self.assertEqual(non_opted.with_user(hr_manager)[field_name], value)

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

    def test_opted_assignment_reparent_without_history_requires_roles_and_enabled_destination(self):
        company_b = self.env['res.company'].create({'name': 'Synthetic assignment destination company'})
        hr_only = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-assignment-reparent-hr-only',
            email='synthetic-assignment-reparent-hr-only@example.invalid',
            company_id=self.env.company.id,
            company_ids=[Command.set([self.env.company.id, company_b.id])],
            groups='base.group_user,hr.group_hr_manager',
        )
        dual_role = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-assignment-reparent-dual-role',
            email='synthetic-assignment-reparent-dual-role@example.invalid',
            company_id=self.env.company.id,
            company_ids=[Command.set([self.env.company.id, company_b.id])],
            groups='base.group_user,hr.group_hr_manager,hr_attendance.group_hr_attendance_manager',
        )

        for active in (True, False):
            with self.subTest(active=active):
                source = self.env['hr.employee'].create({'name': 'Synthetic reparent source %s' % active})
                same_company_target = self.env['hr.employee'].create({'name': 'Synthetic reparent same-company target %s' % active})
                foreign_target = self.env['hr.employee'].with_company(company_b).create({
                    'name': 'Synthetic reparent foreign target %s' % active,
                    'company_id': company_b.id,
                })
                assignment = self.env['sl.shift.assignment'].create({
                    'employee_id': source.id, 'shift_id': self.shift.id,
                    'date_from': '2026-11-01', 'date_to': '2026-11-30',
                    'attendance_policy': 'shift', 'schedule_tz': 'UTC',
                    'workdays': '0,1,2,3,4,5,6', 'break_window_set': True, 'break_start': 22,
                    'active': active,
                })
                assignment = assignment.with_context(active_test=False)

                def persisted_state():
                    self.env.flush_all()
                    self.env.cr.execute(
                        'SELECT employee_id, company_id, active FROM sl_shift_assignment WHERE id = %s',
                        (assignment.id,),
                    )
                    return self.env.cr.fetchone()

                before = persisted_state()
                with self.assertRaises(AccessError):
                    assignment.with_user(hr_only).with_context(
                        allowed_company_ids=[self.env.company.id, company_b.id],
                    ).write({'employee_id': same_company_target.id})
                self.assertEqual(persisted_state(), before)

                assignment.with_user(dual_role).with_context(
                    allowed_company_ids=[self.env.company.id, company_b.id],
                ).write({'employee_id': same_company_target.id})
                self.assertEqual(assignment.employee_id, same_company_target)
                self.assertEqual(assignment.company_id, self.env.company)

                before = persisted_state()
                with self.assertRaises(AccessError):
                    assignment.with_user(dual_role).with_context(
                        allowed_company_ids=[self.env.company.id],
                    ).write({'employee_id': foreign_target.id})
                self.assertEqual(persisted_state(), before)

                assignment.with_user(dual_role).with_context(
                    allowed_company_ids=[self.env.company.id, company_b.id],
                ).write({'employee_id': foreign_target.id})
                self.assertEqual(assignment.employee_id, foreign_target)
                self.assertEqual(assignment.company_id, company_b)

    def test_opted_employee_company_change_without_history_requires_roles_and_enabled_destination(self):
        company_b = self.env['res.company'].create({'name': 'Synthetic employee destination company'})
        hr_only = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-employee-company-hr-only',
            email='synthetic-employee-company-hr-only@example.invalid',
            company_id=self.env.company.id,
            company_ids=[Command.set([self.env.company.id, company_b.id])],
            groups='base.group_user,hr.group_hr_manager',
        )
        dual_role = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-employee-company-dual-role',
            email='synthetic-employee-company-dual-role@example.invalid',
            company_id=self.env.company.id,
            company_ids=[Command.set([self.env.company.id, company_b.id])],
            groups='base.group_user,hr.group_hr_manager,hr_attendance.group_hr_attendance_manager',
        )

        for active in (True, False):
            with self.subTest(active=active):
                employee = self.env['hr.employee'].create({'name': 'Synthetic company source %s' % active})
                assignment = self.env['sl.shift.assignment'].create({
                    'employee_id': employee.id, 'shift_id': self.shift.id,
                    'date_from': '2026-11-01', 'date_to': '2026-11-30',
                    'attendance_policy': 'shift', 'schedule_tz': 'UTC',
                    'workdays': '0,1,2,3,4,5,6', 'break_window_set': True, 'break_start': 22,
                    'active': active,
                }).with_context(active_test=False)

                def persisted_state():
                    self.env.flush_all()
                    self.env.cr.execute('SELECT company_id FROM hr_employee WHERE id = %s', (employee.id,))
                    employee_company = self.env.cr.fetchone()[0]
                    self.env.cr.execute('SELECT company_id FROM sl_shift_assignment WHERE id = %s', (assignment.id,))
                    assignment_company = self.env.cr.fetchone()[0]
                    return employee_company, assignment_company

                before = persisted_state()
                with self.assertRaises(AccessError):
                    employee.with_user(hr_only).with_context(
                        allowed_company_ids=[self.env.company.id, company_b.id],
                    ).write({'company_id': company_b.id})
                self.assertEqual(persisted_state(), before)

                before = persisted_state()
                with self.assertRaises(AccessError):
                    employee.with_user(dual_role).with_context(
                        allowed_company_ids=[self.env.company.id],
                    ).write({'company_id': company_b.id})
                self.assertEqual(persisted_state(), before)

                employee.with_user(dual_role).with_context(
                    allowed_company_ids=[self.env.company.id, company_b.id],
                ).write({'company_id': company_b.id})
                self.assertEqual(employee.company_id, company_b)
                self.assertEqual(assignment.company_id, company_b)
