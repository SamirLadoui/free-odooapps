# SPDX-License-Identifier: LGPL-3.0-or-later
{
    'name': 'Employee Shift Attendance',
    'version': '14.0.1.0.0',
    'summary': 'Opt-in historical shift attendance and module-owned overtime approval',
    'license': 'LGPL-3', 'author': 'Samir Ladoui',
    'depends': ['sl_employee_shift', 'hr_attendance', 'base_import'],
    'data': ['security/security.xml', 'security/ir.model.access.csv', 'views/shift_attendance_views.xml'], 'installable': True, 'auto_install': False,
}
