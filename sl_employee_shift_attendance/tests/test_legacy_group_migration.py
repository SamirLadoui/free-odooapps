# SPDX-License-Identifier: LGPL-3.0-or-later
import importlib.util
import json
from pathlib import Path

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestLegacyAttendanceOfficerMigration(TransactionCase):
    officer_xmlid = 'hr_attendance.group_hr_attendance_user'
    approver_xmlid = 'sl_employee_shift_attendance.group_shift_approver'
    preserve_param = 'sl_employee_shift_attendance.legacy_attendance_officer_preserve'

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().search([
            ('key', '=', self.preserve_param),
        ]).unlink()

    def _materialize_legacy_officer_membership(self, login):
        approver = self.env.ref(self.approver_xmlid)
        officer = self.env.ref(self.officer_xmlid)
        existing_users = self.env['res.users'].sudo().search([
            ('groups_id', 'in', approver.id),
        ])
        original_officer_ids = set(
            existing_users.filtered(lambda user: officer in user.groups_id).ids
        )
        user = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login=login,
            groups='base.group_user,%s' % self.approver_xmlid,
        )

        # Reproduce the old implication and the Odoo 15 materialized row left
        # behind when the implication is removed by module data.
        approver.write({'implied_ids': [Command.link(officer.id)]})
        approver.write({'implied_ids': [Command.unlink(officer.id)]})
        leaked_existing = existing_users.filtered(
            lambda existing: (
                existing.id not in original_officer_ids
                and officer in existing.groups_id
            )
        )
        if leaked_existing:
            leaked_existing.write({'groups_id': [Command.unlink(officer.id)]})
        self.assertTrue(user.has_group(self.officer_xmlid))
        return user

    def _cleanup_legacy_memberships(self):
        cleanup = getattr(
            self.env['res.groups'],
            '_sl_cleanup_legacy_attendance_officer_memberships',
            None,
        )
        self.assertTrue(cleanup, 'The upgrade cleanup entry point is missing.')
        return cleanup()

    def test_missing_decision_fails_closed_for_ambiguous_users(self):
        user = self._materialize_legacy_officer_membership('slshift-legacy-ambiguous')

        with self.assertRaises(UserError):
            self._cleanup_legacy_memberships()

        self.assertTrue(user.has_group(self.officer_xmlid))

    def test_explicit_decision_revokes_only_legacy_memberships_and_replays_safely(self):
        legacy_user = self._materialize_legacy_officer_membership('slshift-legacy-revoke')
        preserved_user = self._materialize_legacy_officer_membership('slshift-legacy-preserve')
        native_admin = new_test_user(
            self.env['res.users'].with_context(no_reset_password=True).env,
            login='slshift-native-attendance-admin',
            groups='base.group_user,%s,hr_attendance.group_hr_attendance_manager' % self.approver_xmlid,
        )
        params = self.env['ir.config_parameter'].sudo()
        params.set_param(
            self.preserve_param,
            json.dumps({'preserve_user_ids': [preserved_user.id]}),
        )

        self.assertEqual(self._cleanup_legacy_memberships(), 1)
        self.assertFalse(legacy_user.has_group(self.officer_xmlid))
        self.assertTrue(preserved_user.has_group(self.officer_xmlid))
        self.assertTrue(native_admin.has_group(self.officer_xmlid))

        self.assertEqual(self._cleanup_legacy_memberships(), 0)
        self.assertFalse(legacy_user.has_group(self.officer_xmlid))
        self.assertTrue(preserved_user.has_group(self.officer_xmlid))
        self.assertTrue(native_admin.has_group(self.officer_xmlid))

    def test_post_migration_hook_executes_the_native_cleanup(self):
        user = self._materialize_legacy_officer_membership('slshift-legacy-hook')
        self.env['ir.config_parameter'].sudo().set_param(
            self.preserve_param,
            json.dumps({'preserve_user_ids': []}),
        )
        migration_path = (
            Path(__file__).resolve().parents[1]
            / 'migrations' / '15.0.1.1.0'
            / 'post-remove-legacy-attendance-officer.py'
        )
        self.assertTrue(migration_path.is_file(), 'Post-migration hook is missing.')
        spec = importlib.util.spec_from_file_location('legacy_attendance_migration', migration_path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.migrate(self.env.cr, '15.0.1.0.0')
        self.assertFalse(user.has_group(self.officer_xmlid))
