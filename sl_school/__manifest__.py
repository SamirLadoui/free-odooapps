# -*- coding: utf-8 -*-
{
    'name': 'School',
    'version': '16.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Academic years, classes, subjects, teachers and student enrolment',
    'description': """
School
======

The core record-keeping a school runs on: who is in which class, who teaches
what, and who has a seat.

Academic years
--------------
Everything hangs off an academic year with a start and an end. Only one year can
be running over a given period, so "the current class list" always means one
thing.

Classes
-------
A grade and an optional division (Grade 5 - A), belonging to one academic year,
with a class teacher, its subjects, and a **capacity**. The seat count is live:
enrolling past capacity is refused, and a student leaving frees their seat
immediately.

Students
--------
Students start as applications and are enrolled into a class. Enrolment checks
the class has room and creates a contact record so the student can be emailed or
invoiced. Roll numbers are unique within a class but reusable across classes,
student numbers are generated from a sequence, and age is computed from the date
of birth.

Also included
-------------
* Teachers with staff numbers, subjects, qualifications and the classes they manage.
* Subjects with codes, credits, theory / practical type, and an elective flag.
* Guardian details on every student.
* Two access levels: School User (read, plus student data entry) and School
  Administrator (everything).
* Kanban, list, form and search views throughout, with grouping by class,
  academic year and status.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/school_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/academic_year_views.xml',
        'views/subject_views.xml',
        'views/teacher_views.xml',
        'views/school_standard_views.xml',
        'views/student_views.xml',
        'views/school_menus.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
