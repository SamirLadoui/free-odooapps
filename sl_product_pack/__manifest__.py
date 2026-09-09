# -*- coding: utf-8 -*-
{
    'name': 'Product Packs',
    'version': '16.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Sell one product and put its contents on the order',
    'description': """
Product Packs
=============

The starter kit, the gift set, the hamper, the "buy the whole shelf" bundle.
Odoo can already do this with a manufacturing bill of materials marked as a
kit, which means installing Manufacturing in order to sell a hamper.

A pack here is simply a product with a list of what is in it.

What happens when you sell one
------------------------------
Confirming the order puts the parts on it. The warehouse picks the parts, and
the customer's paperwork says what they are actually getting.

Not while the quotation is being written
----------------------------------------
A quotation should read the way it was sold - one line saying Starter Kit.
Confirming is the moment the salesperson's view and the warehouse's view stop
being the same thing, so that is when the parts appear. There is a button if
you want to see them sooner.

Two ways to price one
---------------------
One price for the pack shows the parts at no charge, which is what a fixed
price bundle looks like on an invoice. Priced line by line charges for each
part and leaves the pack line at nothing, which is what people expect when
the bundle is a convenience rather than a discount.

A pack is not stock
-------------------
A pack cannot be a product you count, and the module refuses to let you make
one. If it were counted, the order would reserve the pack and its contents at
the same time and the same goods would go out twice.

Exploded once, not every time
-----------------------------
A pack line that already has its parts is left alone, so an order that is
cancelled and confirmed again does not end up with the contents on it twice.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'support': 'samir.odoo.apps2325@gmail.com',
    'license': 'LGPL-3',
    'depends': ['sale_stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_pack_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
