# -*- coding: utf-8 -*-
{
    'name': 'Product Reference Numbering',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Give products an internal reference from a sequence',
    'description': """
Product Reference Numbering
===========================

The internal reference is what everyone types into a search box, reads down
the phone and writes on a shelf label. Odoo leaves it blank and lets people
invent one per product, which is how a catalogue ends up holding CH-001,
ch002 and "Chair 3" by the end of the month.

A sequence settles it. Point a product category at one and everything created
in it is numbered as it is created.

Categories inherit
------------------
A category with no numbering of its own uses the nearest parent that has one,
so "Furniture" can number everything beneath it while "Furniture / Office
Chairs" keeps its own if it earns one. Anything left over falls back to the
company's default.

What you typed is kept
----------------------
A reference entered by hand is never overwritten. A manufacturer's part number
is worth more than one we invented, and the numbering knows to stay out of the
way.

The products already there
--------------------------
Turning numbering on does nothing for the eight hundred products already in
the database, which is usually the reason people went looking for it. Select
them and assign in one go; the ones that already have a reference are skipped.

Off until you point it somewhere
--------------------------------
A sequence is provided, attached to nothing. Until a category or the company
points at one, products are created exactly as they were before.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'support': 'samir.odoo.apps2325@gmail.com',
    'license': 'LGPL-3',
    'depends': ['product'],
    'data': [
        'security/ir.model.access.csv',
        'data/product_sequence.xml',
        'views/product_sequence_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
