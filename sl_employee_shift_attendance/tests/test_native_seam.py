# SPDX-License-Identifier: LGPL-3.0-or-later
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestLegacyNativeSeam(TransactionCase):
    def test_explicit_authoritative_engine_controls_native_daily_overtime(self):
        employee = self.env['hr.employee'].create({'name': 'Synthetic legacy seam'})
        shift = self.env['sl.shift'].create({'name': 'Native seam 18-03', 'start_time': 18, 'end_time': 3, 'break_minutes': 60})
        Assignment = self.env['sl.shift.assignment']
        self.assertIn('attendance_policy', Assignment._fields,
                      'Missing explicit default-off custom engine port for legacy daily overtime')
        assignment = Assignment.create({
            'employee_id': employee.id, 'shift_id': shift.id,
            'date_from': '2026-11-01', 'date_to': '2026-11-30',
            'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6',
            'break_window_set': True, 'break_start': 22,
        })
        self.assertEqual(assignment.attendance_policy, 'off')
        assignment.attendance_policy = 'shift'
        attendance = self.env['hr.attendance'].create({
            'employee_id': employee.id, 'check_in': '2026-11-02 18:00:00',
            'check_out': '2026-11-03 05:00:00',
        })
        self.assertEqual((attendance.worked_hours, attendance.overtime_hours), (10, 2))
        self.assertEqual((attendance.sl_shift_day_id.regular_hours,
                          attendance.sl_shift_day_id.raw_overtime_hours,
                          attendance.sl_shift_day_id.presence_days), (8, 2, 1))
        self.assertFalse(self.env['hr.attendance.overtime'].search([
            ('employee_id', '=', employee.id), ('adjustment', '=', False),
        ]))
