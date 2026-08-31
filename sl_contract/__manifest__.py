# -*- coding: utf-8 -*-
{
    'name': 'Recurring Contracts',
    'version': '15.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Recurring customer contracts that invoice themselves on schedule',
    'description': """
Recurring Contracts
===================

Retainers, subscriptions, maintenance agreements and rentals: set the lines and
the recurrence once, and the invoices generate themselves.

The recurrence
--------------
Every N days, weeks, months or years, invoiced either **in advance** (the period
about to start) or **in arrears** (the period just finished). Every invoice line
carries the exact service period it covers, so the customer can see what they are
paying for.

The next invoice date is a field you can see and correct, not a hidden
calculation. It advances only when an invoice is actually created.

Lines with their own dates
--------------------------
A line can start later or stop earlier than the contract. Add a service in month
four and it appears from month four; end one early and it drops off, while the
rest of the contract carries on.

Ends when it should
-------------------
Give a contract an end date and it invoices the last period, then closes itself
and says so in the log. No end date means it runs until you close it.

Automatic or on demand
----------------------
A daily scheduled action invoices everything that has come due, isolating each
contract so one bad configuration cannot stop the rest of the run. There is also
an **Invoice Now** button for when you do not want to wait.

The scheduled action ships disabled. Turn it on once you have created a contract
and pressed Invoice Now to confirm the output.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'data/contract_data.xml',
        'views/contract_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
