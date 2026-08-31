# -*- coding: utf-8 -*-
{
    'name': 'School Attendance',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Daily attendance registers per class, with rates per student',
    'description': """
School Attendance
=================

A register per class per day, and an attendance rate that means something.

Marking the exceptions
----------------------
Press **Load Students** and every enrolled student appears, marked **present**.
In a normal class most people are there, so the teacher marks the handful who
are not. That is a few clicks rather than thirty.

Four states: present, late, absent, excused. Late counts as present for the
rate, because the child was in the room.

Numbers you can trust
---------------------
* One register per class per day, enforced. Two registers for one day means one
  of them is wrong and no report can tell you which.
* A student from another class cannot be added to a register.
* Nobody can appear on a register twice.
* A register dated outside its academic year is refused.
* Only **enrolled** students are loaded. An application is not an enrolment.

Per student
-----------
Every student carries an attendance rate and their full history, counting
**confirmed** registers only. A draft register is not yet a fact about anybody.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['sl_school'],
    'data': [
        'security/ir.model.access.csv',
        'views/attendance_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
