# SPDX-License-Identifier: LGPL-3.0-or-later
{
    'name': 'Employee Shift Work Entries',
    'version': '14.0.1.0.0',
    'summary': 'Provider-neutral explicit manual bridge for approved shift hours',
    'license': 'LGPL-3', 'author': 'Samir Ladoui',
    'depends': ['sl_employee_shift_attendance', 'hr_work_entry'],
    'data': ['security/security.xml', 'views/shift_work_entry_views.xml'], 'installable': True, 'auto_install': False,
}
