# -*- coding: utf-8 -*-
{
    'name': 'REST API',
    'version': '15.0.1.0.0',
    'category': 'Technical',
    'summary': 'A small REST API over any Odoo model, authenticated by API key',
    'description': """
REST API
========

Read and write Odoo records over plain HTTP, from anything that can send a
request.

The endpoints
-------------
::

    GET     /api/v1/<model>              search, with domain, fields, order,
                                         limit and offset
    GET     /api/v1/<model>/<id>         read one record
    POST    /api/v1/<model>              create, JSON body
    PUT     /api/v1/<model>/<id>         update, JSON body
    DELETE  /api/v1/<model>/<id>         delete

Every response is JSON. A list response carries both the page of ``results`` and
the total ``count``, so a caller can page without guessing.

Authentication
--------------
Send the key in an ``X-Api-Key`` header. Keys are created in Odoo, shown **once**
at the moment they are generated, and stored only as a SHA-256 hash. A lost key
is regenerated, not recovered.

Security is the user's, not the key's
-------------------------------------
Every request runs as the user the key names, with exactly that user's access
rights and record rules. A key cannot reach anything its user could not already
reach through the interface.

Naming models on a key narrows it further - useful for giving a warehouse
scanner a key that can only touch stock - but it never widens anything.

Unknown, revoked and expired keys all return the same 401. A caller learns
whether their key works, not why it does not.

Keys can be given an expiry date, revoked at any moment, and each one records
when it was last used and how many calls it has made.

Versions
--------
14.0 through 19.0.

On **14.0 and 15.0** Odoo hands any request carrying ``Content-Type:
application/json`` to its own JSON-RPC dispatcher before a REST route ever sees
it, and answers 400. Send the same JSON body with ``Content-Type: text/plain``
on those two versions and everything else is identical - the endpoints, the
keys, the responses and the status codes are the same.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/api_key_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
