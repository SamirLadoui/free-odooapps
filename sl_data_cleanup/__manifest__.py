# -*- coding: utf-8 -*-
{
    'name': 'Remove Data',
    'version': '16.0.1.0.0',
    'category': 'Technical',
    'summary': 'Clear transactional data before you go live',
    'description': """
Remove Data
===========

Clear the orders, invoices, transfers and test records out of a database
before you start using it for real, without rebuilding it from scratch.

Safeguards
----------
Removing data is not undoable, so this module is deliberately hard to fire
by accident:

* Settings administrators only. Nobody else sees the menu or the wizard.
* **Count First** tells you exactly how many records each switch would remove
  before anything is touched.
* You have to type the database name in full to confirm. A tick box is too
  easy to click.
* Every removal is written to the server log with the user who ran it.

What it keeps
-------------
* The contacts of your companies and of every user. Removing those breaks the
  database rather than cleaning it - a company needs its partner and a user
  needs theirs to log in.
* Anything belonging to a module that is not installed is skipped quietly,
  so the wizard works on a small database as well as a full one.

Documents that refuse to be deleted while posted or done are set back to
draft or cancelled first, rather than the removal failing halfway through.

**Take a backup before you use this.**
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/data_cleanup_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
