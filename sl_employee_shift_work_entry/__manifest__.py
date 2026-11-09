{
    'name': 'Employee Shift Work Entries',
    'version': '15.0.1.0.0',
    'summary': 'Provider-neutral manual bridge for regular and approved overtime intervals',
    'license': 'LGPL-3',
    'author': 'Samir Ladoui',
    'depends': ['sl_employee_shift_attendance', 'hr_work_entry_contract'],
    'data': ['views/shift_work_entry_views.xml'],
    'installable': True,
    'auto_install': False,
}
