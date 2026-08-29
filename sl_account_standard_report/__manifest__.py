# -*- coding: utf-8 -*-
{
    'name': 'Standard Accounting Report',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'General ledger, trial balance and partner ledger, as PDF or Excel',
    'description': """
Standard Accounting Report
==========================

The three reports every accountant asks for on day one, with the filters they
actually use, as a PDF or a spreadsheet.

Reports
-------
* **General Ledger** - every account with its opening balance and each entry in
  the period.
* **Trial Balance** - one summary line per account: opening, debit, credit,
  closing.
* **Partner Ledger** - the same detail, split by partner as well as by account.

Filters
-------
Date range, posted entries only or posted plus draft, and any combination of
journals, accounts and partners. You can also choose which accounts appear:
those with movement in the period, those with a non-zero balance, or all of them.

Opening balances done properly
------------------------------
Everything dated before the start of the period is summed into an opening
balance rather than dropped or mixed into the period's figures, so the closing
balance is the real one. An account with an opening balance and no movement
still appears when you asked for it.

Output
------
* **PDF** through Odoo's own report engine, so it picks up your layout, header
  and paper format.
* **Excel** with a frozen header row, ready to sort and pivot.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'report/account_standard_report_templates.xml',
        'views/account_report_wizard_views.xml',
    ],
    'external_dependencies': {'python': ['xlsxwriter']},
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
