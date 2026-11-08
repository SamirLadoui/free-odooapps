# SPDX-License-Identifier: LGPL-3.0-or-later
"""Native 16 seam counterexample, retained for repeatable port evidence."""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPort16Seam(TransactionCase):
    def test_ordinary_overnight_uses_net_not_raw_elapsed(self):
        employee = self.env['hr.employee'].create({'name': 'Synthetic Odoo16 seam'})
        shift = self.env['sl.shift'].create({'name': '16 seam 18-03', 'start_time': 18, 'end_time': 3, 'break_minutes': 60})
        values = {'employee_id': employee.id, 'shift_id': shift.id, 'date_from': '2026-11-01', 'date_to': '2026-11-30'}
        if 'attendance_policy' in self.env['sl.shift.assignment']._fields:
            values.update(attendance_policy='shift', schedule_tz='UTC', workdays='0,1,2,3,4,5,6', break_window_set=True, break_start=22)
        self.env['sl.shift.assignment'].create(values)
        attendance = self.env['hr.attendance'].create({'employee_id': employee.id, 'check_in': '2026-11-02 18:00:00', 'check_out': '2026-11-03 03:00:00'})
        self.assertEqual(attendance.worked_hours, 8, 'ordinary 18-03 / explicit one-hour break must be eight net hours')
        self.assertEqual(str(attendance.check_out), '2026-11-03 03:00:00')
