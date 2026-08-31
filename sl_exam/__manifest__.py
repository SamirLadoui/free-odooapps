# -*- coding: utf-8 -*-
{
    'name': 'School Exams',
    'version': '16.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Exams, mark sheets, grades and pass rates',
    'description': """
School Exams
============

Plan an exam, mark it, publish it. Grades and pass rates work themselves out.

Marking
-------
**Start Marking** loads every enrolled student onto the mark sheet, unmarked.
Enter the marks and the percentage, letter grade and pass or fail follow.

An unmarked paper is **empty, not zero**. A paper nobody has looked at yet must
not read as a fail, and it is left out of the averages until it is marked.

A student who sat no paper is marked **absent**, which is not the same as
scoring nothing: absences are excluded from the exam's average and from the
student's own.

Publishing has to be earned
---------------------------
An exam cannot be published while any paper is unmarked. Publishing is telling
students their result, so a partial mark sheet is not something to publish.

Numbers that hold up
--------------------
Pass rate, average and highest mark per exam, over the papers actually marked.
Every student carries an average across **published** exams.

Guards
------
* Marks above what the exam is worth, or below zero, are refused.
* A pass mark above the total is refused: nobody could pass, so it is a typo.
* An exam dated outside its academic year is refused.
* A student from another class cannot be added to a mark sheet, and nobody can
  appear on one twice.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['sl_school'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/exam_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
