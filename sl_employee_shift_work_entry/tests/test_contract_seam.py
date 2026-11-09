# SPDX-License-Identifier: LGPL-3.0-or-later
from datetime import date
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestContractIntervalSeam(TransactionCase):
    def test_manual_source_exports_nonoverlapping_net_intervals(self):
        Contract = self.env['hr.contract']
        self.assertIn('sl_shift_manual', dict(Contract._fields['work_entry_source']._description_selection(self.env)),
                      'The optional bridge must add an explicit mutually exclusive legacy contract source')
        employee = self.env['hr.employee'].create({'name': 'Synthetic legacy contract seam'})
        contract = Contract.create({
            'name': 'Synthetic interval contract', 'employee_id': employee.id,
            'date_start': '2026-01-01', 'wage': 1, 'state': 'open',
            'resource_calendar_id': employee.resource_calendar_id.id,
            'work_entry_source': 'sl_shift_manual',
        })
        shift = self.env['sl.shift'].create({'name': 'Interval seam 18-03', 'start_time': 18, 'end_time': 3, 'break_minutes': 60})
        self.env['sl.shift.assignment'].create({
            'employee_id': employee.id, 'shift_id': shift.id,
            'date_from': '2026-11-01', 'date_to': '2026-11-30',
            'attendance_policy': 'shift', 'schedule_tz': 'UTC', 'workdays': '0,1,2,3,4,5,6',
            'break_window_set': True, 'break_start': 22, 'work_entry_enabled': True,
            'regular_type_id': self.env.ref('hr_work_entry.work_entry_type_attendance').id,
            'overtime_type_id': self.env.ref('hr_work_entry.overtime_work_entry_type').id,
        })
        attendance = self.env['hr.attendance'].create({'employee_id': employee.id,
            'check_in': '2026-11-02 18:00:00', 'check_out': '2026-11-03 05:00:00'})
        actor = new_test_user(self.env, login='sl-contract-seam-approver',
                              groups='base.group_user,hr.group_hr_manager,hr_attendance.group_hr_attendance_manager,sl_employee_shift_attendance.group_shift_approver')
        day = attendance.sl_shift_day_id.with_user(actor)
        day.action_approve(2, 'Synthetic seam approval')
        entries = day.action_generate_work_entries().sorted('date_start')
        expected = [
            ('2026-11-02 18:00:00', '2026-11-02 22:00:00', 'regular', 4),
            ('2026-11-02 23:00:00', '2026-11-03 00:00:00', 'regular', 1),
            ('2026-11-03 00:00:00', '2026-11-03 03:00:00', 'regular', 3),
            ('2026-11-03 03:00:00', '2026-11-03 05:00:00', 'overtime', 2),
        ]
        self.assertEqual([(str(e.date_start), str(e.date_stop), e.sl_shift_kind, e.duration) for e in entries], expected)
        self.assertTrue(all(e.contract_id == contract for e in entries))
        self.assertFalse(contract.generate_work_entries(date(2026, 11, 1), date(2026, 11, 30), force=True))
        self.assertEqual(day.action_generate_work_entries().ids, entries.ids)
        self.assertEqual((day.presence_days, sum(entries.mapped('duration'))), (1, 10))
