# -*- coding: utf-8 -*-
{
    'name': 'Approval Tiers',
    'version': '14.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Somebody has to agree before a record moves on - on any model, without code',
    'description': """
Approval Tiers
==============

Somebody has to agree before a purchase order is confirmed, before a discount
is given, before a holiday is granted. Odoo has no general way to say so, and
most add-ons that add one need a developer for every model they apply to.

This needs none. An administrator picks the model, the field whose change has
to be agreed to, the value that needs agreeing, and who agrees. That is the
whole setup.

Tiers, in order
---------------
Several tiers on one model are asked **in sequence**, and the record cannot
move until every one of them has agreed. The sequence is what makes it a
hierarchy rather than a crowd.

Only when it matters
--------------------
A tier can carry a condition, so approval is asked for the orders above a
certain amount rather than for all of them. The usual reason anybody wants
this at all.

What is kept
------------
Approvals stay after they are answered - who agreed, when, and what a rejection
said. A record whose approvals were tidied away is a record nobody can account
for. Asking again starts a fresh round and the old ones remain, so a document
that went round twice shows that it did.

A rejection has to say why. A refusal with no reason sends the document back
with nothing to act on.

Held, not hidden
----------------
While approval is outstanding the change is refused with the names of the
people it is waiting on, rather than failing quietly or letting it through.

Costs nothing when unused
-------------------------
The models under approval are cached, and a model with no tier on it does no
extra work at all.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/tier_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
