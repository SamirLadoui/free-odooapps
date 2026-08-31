# -*- coding: utf-8 -*-
{
    'name': 'School Fees',
    'version': '16.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Fee structures, student charges and invoices',
    'description': """
School Fees
===========

Define what a year costs, charge it to students, and raise the invoices.

Fee structures
--------------
A structure belongs to an academic year and lists its items - tuition, books,
transport - which add up to the total. Name the classes it applies to, or leave
that empty and it covers **every** class in the year: empty means everyone, not
nobody.

Charging a student a structure that does not apply to their class is refused. It
is always a mistake, and it is the kind that is discovered months later.

Invoices
--------
A fee raises a normal Odoo invoice against the student's own contact record, so
the rest of Accounting - payments, reminders, statements - works with no extra
setup. A student who has not been enrolled has no contact yet, and the module
says so rather than failing quietly.

Overdue is honest
-----------------
A fee past its due date shows as overdue on the list and on its own form. Paying
late clears it, because paying late is still paying, and cancelling clears it too.

Per student
-----------
Every student carries their total charged and their outstanding balance, with
cancelled fees excluded from both.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['sl_school', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/fees_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
