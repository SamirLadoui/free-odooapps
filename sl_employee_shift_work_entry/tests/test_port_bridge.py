# SPDX-License-Identifier: LGPL-3.0-or-later
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestNative14Bridge(TransactionCase):
    def test_approved_shift_exports_only_net_real_intervals(self):
        employee = self.env['hr.employee'].create({'name': 'Synthetic native14 bridge'})
        shift = self.env['sl.shift'].create({'name': 'Synthetic bridge night', 'start_time': 18, 'end_time': 3, 'break_minutes': 60})
        assignment = self.env['sl.shift.assignment'].create({
            'employee_id': employee.id, 'shift_id': shift.id, 'date_from': '2026-11-01', 'date_to': '2026-11-30',
            'attendance_policy': 'shift', 'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6',
            'break_window_set': True, 'break_start': 22,
        })
        punch = self.env['hr.attendance'].create({'employee_id': employee.id, 'check_in': '2026-11-02 18:00:00', 'check_out': '2026-11-03 05:00:00'})
        day = punch.sl_shift_day_id
        self.assertTrue(callable(getattr(day, 'action_generate_work_entries', None)),
                        'The native14 approved/net work-entry bridge is missing')
        employee.sl_shift_work_entry_source = 'sl_shift_manual'
        overtime = self.env['hr.work.entry.type'].create({'name': 'Explicit synthetic extra hours', 'code': 'SL_QA_OT14'})
        assignment.write({'work_entry_enabled': True, 'regular_type_id': self.env.ref('hr_work_entry.work_entry_type_attendance').id,
                          'overtime_type_id': overtime.id})
        actor = new_test_user(self.env['res.users'].with_context(no_reset_password=True).env,
                              email='synthetic@example.invalid', login='slshift-14-bridge-port',
                              groups='base.group_user,hr.group_hr_manager,hr_attendance.group_hr_attendance_manager,sl_employee_shift_attendance.group_shift_approver')
        day = day.with_user(actor)
        day.action_approve(2, 'Synthetic authorized decision')
        entries = day.action_generate_work_entries()
        self.assertEqual(sorted((str(e.date_start), str(e.date_stop), e.sl_shift_kind, e.duration) for e in entries), [
            ('2026-11-02 18:00:00', '2026-11-02 22:00:00', 'regular', 4),
            ('2026-11-02 23:00:00', '2026-11-03 00:00:00', 'regular', 1),
            ('2026-11-03 00:00:00', '2026-11-03 03:00:00', 'regular', 3),
            ('2026-11-03 03:00:00', '2026-11-03 05:00:00', 'overtime', 2)])
        self.assertEqual((sum(entries.mapped('duration')), day.presence_days), (10, 1))
        self.assertEqual(str(punch.check_out), '2026-11-03 05:00:00')
