# -*- coding: utf-8 -*-
{
    'name': 'Connector Base',
    'version': '14.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'The shared half of any integration: links, log and retries',
    'description': """
Connector Base
==============

Connecting Odoo to something else is mostly not about the something else. It
is retries, back-off, timeouts, knowing what was already imported, and being
able to say afterwards what happened. Every integration writes that part
again, slightly differently, and gets it slightly wrong.

This is that part, written once.

The link table
--------------
Which Odoo record is which record over there, stored rather than guessed at.
Without it, the second sync creates a second copy of everything - which is the
failure people actually hit: the orders imported fine on Monday and there were
two of each on Tuesday. Names change and references get edited, so an
integration that re-identifies records by matching text will eventually match
the wrong ones.

The log
-------
An integration that fails quietly is worse than one that does not run: the
orders stop arriving and nobody notices until a customer asks where their
parcel is. Every run leaves a line, and failures carry the message the other
side actually sent rather than a paraphrase. The log is written, never
rewritten.

Asking politely
---------------
Requests are retried when the answer says it is worth retrying - a 429, a 502,
a dropped connection - and left alone when it is not, because asking again
will not turn a 401 into a 200. The other side's own Retry-After is preferred
over a guess.

Testable without a shop
-----------------------
Every real HTTP call goes through one method, so an integration built on this
can be tested against recorded answers rather than against a live shop and a
working network.

For developers
--------------
Install this on its own and the link table and the log are yours to use from
your own code: inherit sl.connector.backend and you have the transport, the
logging and the mapping helpers.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'support': 'samir.odoo.apps2325@gmail.com',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/connector_views.xml',
        'data/connector_cron.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
