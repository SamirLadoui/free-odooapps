# -*- coding: utf-8 -*-
{
    'name': 'Hide Cost Price',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Keep product cost to the people who are meant to see it',
    'description': """
Hide Cost Price
===============

Odoo already keeps the cost of a product away from portal and public users.
What it has no answer for is the salesperson, the stock clerk or the shop
assistant who is a perfectly ordinary internal user and has no business
knowing what the company pays for what it sells.

This adds a group, "Show Cost Price". Members see the cost as they always
did. Everybody else gets a product with no cost on it at all.

Properly gone, not merely hidden
--------------------------------
The cost is restricted with the same mechanism Odoo itself uses for the
portal, so it disappears from every form, list, kanban, export and RPC call at
once - not only from the screens somebody remembered to edit. There is no view
left over where it shows up again, and no export that quietly includes it.

Who sees it after installing
----------------------------
Settings administrators, and nobody else. Add the group to whoever else needs
it - a purchase manager, an accountant - from their user form.

What it covers
--------------
The cost of a product, on the template and on each variant. Prices that are
not cost - the sales price, the price on a purchase order line - are left
exactly as they were, because hiding those breaks the work rather than
protecting anything.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'support': 'samir.odoo.apps2325@gmail.com',
    'license': 'LGPL-3',
    'depends': ['product'],
    'data': [
        'security/hide_cost_groups.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
