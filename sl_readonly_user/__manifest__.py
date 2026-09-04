# -*- coding: utf-8 -*-
{
    'name': 'Read Only User',
    'version': '15.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'One group that lets a user see everything and change nothing',
    'description': """
Read Only User
==============

The auditor, the accountant's assistant, the owner who wants to look at the
numbers without the risk of nudging one. Odoo can express this only by going
through every model in the access rights table and unticking three boxes on
each, which nobody finishes and nobody maintains afterwards.

This is one group. A user who has it is refused every create, every write and
every delete, whatever the access rights say, on every model at once.

Nothing to route around
-----------------------
The check sits where Odoo already asks whether an operation is allowed, so
the web client, an import, an automated action and an XML-RPC call all pass
through the same refusal. There is no screen that was forgotten.

What they can still do
----------------------
Everything they could read before, they can still read: their groups decide
what they see, and this decides what they can change. Their own preferences -
language, timezone, signature, password - still work, because Odoo handles
those itself, and it is the one thing a read-only account genuinely needs.

What it will not let them do
----------------------------
Give themselves another group. That goes through the same refusal as anything
else, so a read-only account cannot quietly stop being one.

Odoo's own machinery is unaffected
----------------------------------
Server code that runs as superuser - logging in, scheduled actions, the
client's own housekeeping - is not touched, because refusing that would break
the session rather than protect anything.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'support': 'samir.odoo.apps2325@gmail.com',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/readonly_groups.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
