# SPDX-License-Identifier: LGPL-3.0-or-later
{
    'name': 'Employee Shift Attendance',
    'version': '18.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'summary': 'Opt-in historical shift net hours and separately approved overtime',
    'description': """
Employee Shift Attendance for Odoo 18
====================================
Default-off historical shift integration using explicit timezone, workdays and
unpaid break windows. Original punches are preserved. Eligible assignments select
one custom authoritative overtime engine instead of duplicate native daily
calculation. Logical presence, raw overtime, approval and immutable source audit
remain separate. Real native CSV/XLSX import and stable external-ID updates use
the same ORM path. Restricted approval and guarded historical preview/repair are
included; native attendance access rights are not widened.

This addon does not create payslips or statutory premiums. The optional Employee
Shift Work Entries bridge exports regular and approved overtime intervals. Client
payroll/localization acceptance is required; no UAE salary certification is made.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['sl_employee_shift', 'hr_attendance', 'base_import'],
    'data': ['security/security.xml', 'security/ir.model.access.csv', 'views/shift_attendance_views.xml'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
