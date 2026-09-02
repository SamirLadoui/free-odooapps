# -*- coding: utf-8 -*-
{
    'name': 'Invoice Line Numbers',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Number the lines of an invoice, on screen and on paper',
    'description': """
Invoice Line Numbers
====================

"The second line is wrong" is how people talk about an invoice on the phone,
and Odoo gives them nothing to count with. Customers count the lines
themselves, the supplier counts them differently, and the call goes round in
circles.

Every invoice and bill line gets a number, in the form and on the printed
document alike, so both sides of the conversation are looking at the same
numbers.

Headings are not numbered
-------------------------
Sections and notes are headings. Numbering them would mean the fifth line on
paper is not line five, which is exactly the confusion this is meant to end.

Worked out, not stored
----------------------
The number is the line's position as it is shown, so moving a line up
renumbers the rest at once and there is nothing to go stale or to repair after
an import.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'support': 'samir.odoo.apps2325@gmail.com',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'views/account_move_views.xml',
        'report/report_invoice.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
