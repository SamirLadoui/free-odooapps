# SPDX-License-Identifier: LGPL-3.0-or-later
{
    'name': 'Employee Shift Work Entries',
    'version': '18.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Explicit manual native contract intervals for regular and approved shift hours',
    'description': """
Employee Shift Work Entries for Odoo 18
======================================
Provider-neutral optional bridge using the native hr.contract and start/stop
hr.work.entry APIs. Requires two explicit opt-ins: assignment/type mapping and
historical contract source Shift Summary (Explicit Manual Generation). Automatic
native generation is excluded for that source. Explicit authorized generation
exports nonoverlapping net regular intervals plus approved overtime only, with
source links, digest, local-midnight allocation and native generation coverage.
Repeated generation is idempotent; unrelated native entries are never deleted.
Finalized entry/source/date/parent/company mutation paths are guarded.

No payroll dependency, statutory rate, salary-rule or wage change is supplied.
Leave/holiday ambiguity fails closed. Licensed client payroll and UAE Monthly Pay
payslip results remain separate provider-specific acceptance work.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['sl_employee_shift_attendance', 'hr_work_entry_contract', 'hr_holidays'],
    'data': ['views/shift_work_entry_views.xml'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
