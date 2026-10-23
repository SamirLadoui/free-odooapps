# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


def punch(user, when):
    return {'device_user_id': user, 'timestamp': when}


@tagged('post_install', '-at_install')
class TestBiometricAttendance(TransactionCase):

    def setUp(self):
        # 14.0 has no class-level env: setUpClass cannot build fixtures.
        super().setUp()
        self.device = self.env['sl.biometric.device'].create({
            'name': 'Main Entrance', 'address': '10.0.0.9',
            'debounce_seconds': 60,
        })
        self.alice = self.env['hr.employee'].create({
            'name': 'Alice', 'sl_device_user_id': '1'})
        self.bob = self.env['hr.employee'].create({
            'name': 'Bob', 'sl_device_user_id': '2'})
        self.day = datetime(2026, 4, 1, 8, 0, 0)

    # -- cleaning ----------------------------------------------------------

    def test_punches_are_sorted(self):
        raw = [punch('1', self.day + timedelta(hours=8)),
               punch('1', self.day)]
        cleaned = self.device._clean_punches(raw, 60)
        self.assertEqual([p['timestamp'] for p in cleaned],
                         [self.day, self.day + timedelta(hours=8)])

    def test_double_press_is_ignored(self):
        """People press twice when the beep is not obvious."""
        raw = [punch('1', self.day),
               punch('1', self.day + timedelta(seconds=5))]
        self.assertEqual(len(self.device._clean_punches(raw, 60)), 1)

    def test_punch_outside_the_window_is_kept(self):
        raw = [punch('1', self.day),
               punch('1', self.day + timedelta(seconds=90))]
        self.assertEqual(len(self.device._clean_punches(raw, 60)), 2)

    def test_debounce_is_per_user(self):
        """Two people punching together must both be recorded."""
        raw = [punch('1', self.day), punch('2', self.day + timedelta(seconds=2))]
        self.assertEqual(len(self.device._clean_punches(raw, 60)), 2)

    def test_zero_debounce_keeps_everything(self):
        raw = [punch('1', self.day), punch('1', self.day + timedelta(seconds=1))]
        self.assertEqual(len(self.device._clean_punches(raw, 0)), 2)

    # -- pairing -----------------------------------------------------------

    def test_two_punches_make_one_shift(self):
        pairs = self.device._pair_punches([
            punch('1', self.day), punch('1', self.day + timedelta(hours=8))])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]['check_in'], self.day)
        self.assertEqual(pairs[0]['check_out'], self.day + timedelta(hours=8))

    def test_four_punches_make_two_shifts(self):
        """Morning, lunch out, lunch back, home."""
        stamps = [self.day, self.day + timedelta(hours=4),
                  self.day + timedelta(hours=5), self.day + timedelta(hours=9)]
        pairs = self.device._pair_punches([punch('1', s) for s in stamps])
        self.assertEqual(len(pairs), 2)
        self.assertEqual(pairs[0]['check_out'], stamps[1])
        self.assertEqual(pairs[1]['check_in'], stamps[2])

    def test_odd_punch_leaves_an_open_shift(self):
        """Somebody is still inside; inventing a check-out would be a lie."""
        pairs = self.device._pair_punches([punch('1', self.day)])
        self.assertEqual(len(pairs), 1)
        self.assertFalse(pairs[0]['check_out'])

    def test_users_are_paired_independently(self):
        pairs = self.device._pair_punches([
            punch('1', self.day),
            punch('2', self.day + timedelta(minutes=5)),
            punch('1', self.day + timedelta(hours=8)),
            punch('2', self.day + timedelta(hours=8, minutes=5)),
        ])
        self.assertEqual(len(pairs), 2)
        self.assertTrue(all(pair['check_out'] for pair in pairs),
                        "neither user's punches should be mixed with the other's")

    # -- storing -----------------------------------------------------------

    def test_attendance_is_created_for_a_mapped_employee(self):
        created = self.device._process_punches([
            punch('1', self.day), punch('1', self.day + timedelta(hours=8))])
        self.assertEqual(created, 1)
        attendance = self.env['hr.attendance'].search([
            ('employee_id', '=', self.alice.id)])
        self.assertEqual(len(attendance), 1)
        self.assertEqual(attendance.check_in, self.day)

    def test_unmapped_device_user_is_reported_not_guessed(self):
        created = self.device._process_punches([
            punch('99', self.day), punch('99', self.day + timedelta(hours=8))])
        self.assertEqual(created, 0)
        self.assertIn('99', self.device.last_message)

    def test_downloading_twice_does_not_duplicate(self):
        punches = [punch('1', self.day), punch('1', self.day + timedelta(hours=8))]
        self.device._process_punches(punches)
        self.device._process_punches(punches)
        self.assertEqual(
            len(self.env['hr.attendance'].search([('employee_id', '=', self.alice.id)])),
            1, "re-importing the same punches must not create a second record")

    def test_open_shift_is_stored_without_a_check_out(self):
        self.device._process_punches([punch('1', self.day)])
        attendance = self.env['hr.attendance'].search([
            ('employee_id', '=', self.alice.id)])
        self.assertEqual(len(attendance), 1)
        self.assertFalse(attendance.check_out)

    def test_later_download_closes_open_shift(self):
        """Check-in and check-out may arrive in separate device downloads."""
        self.device._process_punches([punch('1', self.day)])
        attendance = self.env['hr.attendance'].search([
            ('employee_id', '=', self.alice.id)])
        self.assertEqual(len(attendance), 1)
        self.assertFalse(attendance.check_out)
        original_id = attendance.id
        check_out = self.day + timedelta(hours=8)

        created = self.device._process_punches([
            punch('1', self.day), punch('1', check_out)])

        attendance = self.env['hr.attendance'].search([
            ('employee_id', '=', self.alice.id)])
        self.assertEqual(created, 0, "closing a shift must not count as a new one")
        self.assertEqual(attendance.ids, [original_id])
        self.assertEqual(attendance.check_out, check_out)

    def test_result_is_recorded_on_the_device(self):
        self.device._process_punches([
            punch('1', self.day), punch('1', self.day + timedelta(hours=8))])
        self.assertEqual(self.device.last_state, 'ok')
        self.assertTrue(self.device.last_download)
        self.assertIn('1 attendance', self.device.last_message)

    def test_later_download_preserves_existing_check_out(self):
        """Do not replace a completed or manually corrected shift."""
        check_out = self.day + timedelta(hours=7)
        attendance = self.env['hr.attendance'].create({
            'employee_id': self.alice.id,
            'check_in': self.day, 'check_out': check_out})
        created = self.device._process_punches([
            punch('1', self.day), punch('1', self.day + timedelta(hours=8))])
        self.assertEqual(created, 0)
        self.assertEqual(attendance.check_out, check_out)
        self.assertEqual(self.env['hr.attendance'].search_count([
            ('employee_id', '=', self.alice.id)]), 1)

    def test_partial_replay_does_not_reopen_completed_shift(self):
        check_out = self.day + timedelta(hours=8)
        self.device._process_punches([
            punch('1', self.day), punch('1', check_out)])
        self.device._process_punches([punch('1', self.day)])
        attendance = self.env['hr.attendance'].search([
            ('employee_id', '=', self.alice.id)])
        self.assertEqual(len(attendance), 1)
        self.assertEqual(attendance.check_out, check_out)

    def test_incremental_downloads_complete_both_daily_shifts(self):
        stamps = [self.day, self.day + timedelta(hours=4),
                  self.day + timedelta(hours=5), self.day + timedelta(hours=9)]
        for count in range(1, 5):
            self.device._process_punches([punch('1', s) for s in stamps[:count]])
        self.device._process_punches([punch('1', s) for s in stamps])
        attendance = self.env['hr.attendance'].search([
            ('employee_id', '=', self.alice.id)], order='check_in')
        self.assertEqual(len(attendance), 2)
        self.assertEqual(attendance.mapped('check_in'), [stamps[0], stamps[2]])
        self.assertEqual(attendance.mapped('check_out'), [stamps[1], stamps[3]])

    def test_later_checkout_does_not_close_another_employee(self):
        self.device._process_punches([
            punch('1', self.day), punch('2', self.day)])
        self.device._process_punches([
            punch('1', self.day), punch('1', self.day + timedelta(hours=8)),
            punch('2', self.day)])
        alice = self.env['hr.attendance'].search([
            ('employee_id', '=', self.alice.id)])
        bob = self.env['hr.attendance'].search([
            ('employee_id', '=', self.bob.id)])
        self.assertEqual(alice.check_out, self.day + timedelta(hours=8))
        self.assertFalse(bob.check_out)
        self.assertEqual(len(alice | bob), 2)

    def test_manual_download_completes_and_replays_open_shift(self):
        """Mock only the terminal; use real import and attendance ORM."""
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        check_in = SimpleNamespace(user_id='1', timestamp=self.day)
        check_out = SimpleNamespace(
            user_id='1', timestamp=self.day + timedelta(hours=8))
        connection = Mock()
        connection.get_attendance.side_effect = [
            [check_in], [check_in, check_out], [check_in, check_out]]
        with patch.object(type(self.device), '_connect', return_value=connection):
            self.device.action_download()
            original = self.env['hr.attendance'].search([
                ('employee_id', '=', self.alice.id)])
            self.assertFalse(original.check_out)
            self.device.action_download()
            self.device.action_download()
        attendance = self.env['hr.attendance'].search([
            ('employee_id', '=', self.alice.id)])
        self.assertEqual(attendance.ids, original.ids)
        self.assertEqual(attendance.check_out, check_out.timestamp)
        self.assertEqual(connection.disconnect.call_count, 3)

    def test_cron_completes_shift_when_another_device_is_offline(self):
        """A failed terminal must not roll back a successful late checkout."""
        from types import SimpleNamespace
        from unittest.mock import Mock, patch

        from odoo.addons.sl_biometric_attendance.models import biometric_device
        offline = self.env['sl.biometric.device'].create({
            'name': 'Offline warehouse', 'address': '192.0.2.99'})
        # Isolate the cron's device selection inside this rollback-only test.
        self.env['sl.biometric.device'].search([
            ('id', 'not in', (self.device | offline).ids),
        ]).write({'active': False})
        check_in = SimpleNamespace(user_id='1', timestamp=self.day)
        check_out = SimpleNamespace(
            user_id='1', timestamp=self.day + timedelta(hours=8))
        connection = Mock()
        connection.get_attendance.side_effect = [[check_in], [check_in, check_out]]

        def connect(device):
            if device.id == offline.id:
                raise UserError('Simulated offline QA terminal')
            return connection

        connection_patch = patch.object(
            type(self.device), '_connect', autospec=True, side_effect=connect)
        with connection_patch, self.assertLogs(
                biometric_device.__name__, level='WARNING'):
            self.env['sl.biometric.device']._cron_download()
            self.env['sl.biometric.device']._cron_download()
        attendance = self.env['hr.attendance'].search([
            ('employee_id', '=', self.alice.id)])
        self.assertEqual(len(attendance), 1)
        self.assertEqual(attendance.check_out, check_out.timestamp)
        self.assertEqual(self.device.last_state, 'ok')
        self.assertEqual(offline.last_state, 'fail')
        self.assertEqual(connection.disconnect.call_count, 2)

    # -- guards ------------------------------------------------------------

    def test_biometric_id_is_unique(self):
        """Two employees sharing an id would silently mix their hours."""
        with self.assertRaises(ValidationError):
            self.env['hr.employee'].create({
                'name': 'Impostor', 'sl_device_user_id': '1'})

    def test_port_is_validated(self):
        for bad in (0, -5, 70000):
            with self.assertRaises(ValidationError, msg='accepted port %s' % bad):
                self.device.port = bad

    def test_debounce_cannot_be_negative(self):
        with self.assertRaises(ValidationError):
            self.device.debounce_seconds = -1

    def test_connecting_without_pyzk_says_so(self):
        from odoo.addons.sl_biometric_attendance.models import biometric_device
        if biometric_device.ZK is not None:
            self.skipTest('pyzk is installed on this machine')
        with self.assertRaises(UserError) as caught:
            self.device._connect()
        self.assertIn('pyzk', str(caught.exception))
