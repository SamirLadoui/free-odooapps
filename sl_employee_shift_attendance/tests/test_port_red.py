# SPDX-License-Identifier: LGPL-3.0-or-later
"""Native-14 business counterexample before the net-time adapter exists."""
import csv
import io

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'slshift_port_red')
class TestNative14NightPort(TransactionCase):
    def _import(self, checkout):
        employee = self.env['hr.employee'].create({'name': 'Synthetic native14 RED'})
        shift = self.env['sl.shift'].create({'name': 'Synthetic 18-03', 'start_time': 18, 'end_time': 3, 'break_minutes': 60})
        values = {'employee_id': employee.id, 'shift_id': shift.id, 'date_from': '2026-11-01', 'date_to': '2026-11-30'}
        # This branch is absent in the retained RED and exercises explicit opt-in
        # after the port registers its actual fields.
        if 'attendance_policy' in self.env['sl.shift.assignment']._fields:
            values.update(attendance_policy='shift', schedule_tz='UTC', workdays='0,1,2,3,4,5,6', break_window_set=True, break_start=22)
        self.env['sl.shift.assignment'].create(values)
        stream = io.StringIO()
        writer = csv.writer(stream)
        columns = ['External ID', 'Employee Database ID', 'Check In', 'Check Out']
        writer.writerow(columns)
        writer.writerow(['native14_red', employee.id, '2026-11-02 18:00:00', checkout])
        wizard = self.env['base_import.import'].create({'res_model': 'hr.attendance', 'file': stream.getvalue().encode(), 'file_type': 'text/csv', 'file_name': 'synthetic.csv'})
        result = wizard.with_context(tz='UTC').do(['id', 'employee_id/.id', 'check_in', 'check_out'], columns,
            {'headers': True, 'separator': ',', 'quoting': '"', 'encoding': 'utf-8', 'date_format': '%Y-%m-%d', 'datetime_format': '%Y-%m-%d %H:%M:%S'})
        self.assertFalse([m for m in result['messages'] if m['type'] == 'error'], result)
        return self.env['hr.attendance'].browse(result['ids'])

    def test_module_owned_regular_raw_and_pending_presence(self):
        self.assertNotIn('hr.attendance.overtime', self.env.registry)
        self.assertNotIn('hr.attendance.overtime.line', self.env.registry)
        self.assertIn('sl_shift_day_id', self.env['hr.attendance']._fields,
                      'Odoo14 needs module-owned logical-day quantities, not fictional native overtime')
        punch = self._import('2026-11-03 05:00:00')
        day = punch.sl_shift_day_id
        self.assertEqual((day.regular_hours, day.raw_overtime_hours, day.approved_overtime_hours, day.presence_days), (8, 2, 0, 1))

    def test_native_csv_ordinary_net_is_eight(self):
        punch = self._import('2026-11-03 03:00:00')
        self.assertEqual(str(punch.check_out), '2026-11-03 03:00:00')
        self.assertEqual(punch.worked_hours, 8, '18-03 with 1h explicit break: 8 net, not 9')

    def test_native_csv_extended_net_is_ten(self):
        punch = self._import('2026-11-03 05:00:00')
        self.assertEqual(punch.worked_hours, 10, '18-05 with 1h explicit break: 10 net, not 11')
