# -*- coding: utf-8 -*-
{
    'name': 'Employee Shifts',
    'version': '14.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Define work shifts and assign employees to them over time',
    'description': """
Employee Shifts
===============

Define your shifts once, assign people to them, and see at a glance who is on
which.

Overnight shifts, done properly
-------------------------------
A shift that ends earlier than it starts runs past midnight. 22:00 to 06:00 is
**eight hours**, not minus sixteen, and the paid hours are worked out
accordingly. Getting that wrong is how a night shift quietly ends up unpaid.

Unpaid breaks come off the total, on overnight shifts as well as ordinary ones.

One shift at a time
-------------------
An employee cannot hold two overlapping assignments. Two at once means no report
can say which shift somebody was actually on, so the second is refused with a
message naming the first.

Assignments can be open ended for a permanent shift, or given an end date for a
temporary one. Consecutive assignments are fine; overlapping ones are not.

Also
----
* The current shift shows on the employee form, worked out from today's date.
* Shift codes are unique, so two spellings of one shift cannot split reporting.
* A break as long as the shift, a zero-length shift, or times outside the day
  are all refused at entry.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['hr', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/shift_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
