"""Synthetic video-shaped regression, not the unavailable client file."""
import csv
import io

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'slshift_baseline')
class TestNightImport(TransactionCase):
    def _import_shift(self, checkout='2026-11-03 03:00:00', external_id='slshift_qa_ordinary'):
        employee = self.env['hr.employee'].create({'name': 'QA synthetic night import'})
        employee.resource_id.tz = 'UTC'
        employee.resource_calendar_id.tz = 'UTC'
        shift = self.env['sl.shift'].create({
            'name': 'QA 18-03', 'start_time': 18, 'end_time': 3, 'break_minutes': 60,
        })
        self.env['sl.shift.assignment'].create({
            'employee_id': employee.id, 'shift_id': shift.id,
            'date_from': '2026-11-01', 'date_to': '2026-11-30',
            'attendance_policy': 'shift', 'schedule_tz': 'UTC',
            'workdays': '0,1,2,3,4,5,6', 'break_window_set': True, 'break_start': 22,
        })
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(['External ID', 'Employee Database ID', 'Check In', 'Check Out'])
        writer.writerow([external_id, employee.id, '2026-11-02 18:00:00', checkout])
        wizard = self.env['base_import.import'].create({
            'res_model': 'hr.attendance', 'file': stream.getvalue().encode(),
            'file_type': 'text/csv', 'file_name': 'synthetic-night.csv',
        })
        result = wizard.with_context(tz='UTC').execute_import(
            ['id', 'employee_id/.id', 'check_in', 'check_out'],
            ['External ID', 'Employee Database ID', 'Check In', 'Check Out'],
            {'has_headers': True, 'separator': ',', 'quoting': '"', 'encoding': 'utf-8',
             'date_format': '%Y-%m-%d', 'datetime_format': '%Y-%m-%d %H:%M:%S'},
        )
        self.assertFalse([m for m in result['messages'] if m['type'] == 'error'], result)
        attendance = self.env['hr.attendance'].browse(result['ids'])
        self.assertEqual(len(attendance), 1)
        return attendance

    def _repeat_native_import(self, attendance, checkout, kind='csv', dry_run=False):
        columns = ['External ID', 'Employee Database ID', 'Check In', 'Check Out']
        rows = [['slshift_qa_ordinary', attendance.employee_id.id, '2026-11-02 18:00:00', checkout]]
        if kind == 'xlsx':
            from xlsxwriter import Workbook
            stream = io.BytesIO()
            book = Workbook(stream, {'in_memory': True})
            sheet = book.add_worksheet()
            sheet.write_row(0, 0, columns)
            for index, row in enumerate(rows, 1):
                sheet.write_row(index, 0, row)
            book.close()
            payload = stream.getvalue()
            mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(columns)
            writer.writerows(rows)
            payload = stream.getvalue().encode()
            mime = 'text/csv'
        wizard = self.env['base_import.import'].create({'res_model': 'hr.attendance', 'file': payload,
                                                       'file_type': mime, 'file_name': 'synthetic-update.' + kind})
        return wizard.with_context(tz='UTC').execute_import(['id', 'employee_id/.id', 'check_in', 'check_out'], columns,
            {'has_headers': True, 'separator': ',', 'quoting': '"', 'encoding': 'utf-8',
             'date_format': '%Y-%m-%d', 'datetime_format': '%Y-%m-%d %H:%M:%S'}, dryrun=dry_run)

    def test_csv_update_and_reimport_by_external_id_keep_one_punch_and_one_anchor(self):
        attendance = self._import_shift()
        day = attendance.sl_shift_day_id
        for unused in range(2):
            result = self._repeat_native_import(attendance, '2026-11-03 05:00:00')
            self.assertFalse([m for m in result['messages'] if m['type'] == 'error'], result)
            self.assertEqual(result['ids'], attendance.ids)
        self.assertEqual(self.env['hr.attendance'].search_count([('employee_id', '=', attendance.employee_id.id)]), 1)
        self.assertEqual(attendance.sl_shift_day_id, day)
        self.assertEqual((attendance.worked_hours, attendance.overtime_hours, day.presence_days), (10, 2, 1))

    def test_actual_xlsx_import_update_and_repeat_are_idempotent(self):
        attendance = self._import_shift()
        for unused in range(2):
            result = self._repeat_native_import(attendance, '2026-11-03 04:00:00', 'xlsx')
            self.assertFalse([m for m in result['messages'] if m['type'] == 'error'], result)
            self.assertEqual(result['ids'], attendance.ids)
        self.assertEqual((attendance.worked_hours, attendance.overtime_hours, attendance.sl_shift_day_id.presence_days), (9, 1, 1))

    def test_native_import_dry_run_rolls_back_punch_and_approval_effects(self):
        attendance = self._import_shift()
        original = attendance.read(['check_in', 'check_out', 'worked_hours', 'overtime_hours'])
        summary = attendance.sl_shift_day_id.read(['digest', 'state', 'net_hours', 'raw_overtime_hours'])
        result = self._repeat_native_import(attendance, '2026-11-03 05:00:00', dry_run=True)
        self.assertFalse([m for m in result['messages'] if m['type'] == 'error'], result)
        # Native execute_import(dryrun=True) rolls back SQL but leaves record
        # caches in this cursor populated; a real next RPC has a fresh cache.
        # Inspect stored rows BEFORE invalidation, without flushing the cache.
        self.env.cr.execute('SELECT check_out, worked_hours, overtime_hours FROM hr_attendance WHERE id = %s', (attendance.id,))
        self.assertEqual(self.env.cr.fetchone(), (original[0]['check_out'], 8, 0))
        self.env.cr.execute('SELECT net_hours, raw_overtime_hours FROM sl_shift_day WHERE id = %s', (summary[0]['id'],))
        self.assertEqual(self.env.cr.fetchone(), (8, 0))
        self.env.invalidate_all(flush=False)
        self.assertEqual(original, attendance.read(['check_in', 'check_out', 'worked_hours', 'overtime_hours']))
        self.assertEqual(summary, attendance.sl_shift_day_id.read(['digest', 'state', 'net_hours', 'raw_overtime_hours']))

    def test_ordinary_night_native_csv_net_hours(self):
        attendance = self._import_shift()
        self.assertEqual(str(attendance.check_out), '2026-11-03 03:00:00')
        self.assertAlmostEqual(attendance.worked_hours, 8, msg='18-03 / 60min break must be 8 net, not 9')

    def test_extended_night_native_csv_net_hours(self):
        attendance = self._import_shift('2026-11-03 05:00:00', 'slshift_qa_extended')
        self.assertAlmostEqual(attendance.worked_hours, 10, msg='18-05 / 60min break must be 10 net, not 11')
        self.assertAlmostEqual(attendance.overtime_hours, 2, msg='Only two hours exceed the assigned eight net hours')
