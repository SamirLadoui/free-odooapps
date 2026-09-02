# -*- coding: utf-8 -*-
{
    'name': 'Negative Stock Rules',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Say where stock may not go below zero, and where it may',
    'description': """
Negative Stock Rules
====================

Odoo lets stock go negative on purpose: a shop that receives goods after it
sells them would otherwise be unable to trade. The trouble is that it is
allowed **everywhere**, so a genuine mistake in a warehouse looks exactly like
the intended behaviour in a shop, and nobody finds it until a stock count.

A rule draws the line: which location, which products, and whether going under
is refused outright or allowed and noted. Anywhere without a rule behaves
exactly as Odoo always did.

Checked when the stock actually leaves
--------------------------------------
Not when the move is planned. A move created today for next week should not be
refused because the goods have not arrived yet - the question only means
anything at the moment the stock is being taken, which is where the check sits.

On hand, not forecast
---------------------
What is counted is the quantity actually on the shelf. A forecast includes what
is expected to arrive, and stock that has not arrived cannot be picked.

Refuse or record
----------------
Refusing is right in a warehouse that counts. Allowing it and writing it on the
transfer is right where going under is normal but worth knowing about.

The first rule that fits
------------------------
Rules are ordered, and the first one that matches a move is the one applied.
Two rules disagreeing about the same shelf is a question the order answers -
applying both would mean the stricter always won, whatever anybody intended.

What is left alone
------------------
Goods arriving from a supplier, or moving out of a scrap or inventory location,
are not coming off anybody's shelf and are never refused. Neither are services
or non-storable products, which have no quantity to go under.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'support': 'samir.odoo.apps2325@gmail.com',
    'license': 'LGPL-3',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/negative_stock_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
