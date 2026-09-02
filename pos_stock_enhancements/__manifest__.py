# -*- coding: utf-8 -*-
{
    'name': 'POS Stock Enhancements',
    'version': '15.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Real-time stock checks in the Point of Sale, by configurable location',
    'description': """
POS Stock Enhancements
======================

Stop the Point of Sale selling what you do not have.

Choose which stock locations a Point of Sale should count, and every line added
to an order is checked against them:

* A product with no stock in those locations is **refused**, with a message
  naming it.
* A quantity beyond what is left is **reduced to what is actually available**,
  and the cashier is told why rather than silently corrected.
* Quantities already on the order count against the total, so adding the same
  product twice cannot walk past the limit.

Configurable per Point of Sale
------------------------------
The check is switched on per POS, with its own list of locations. A shop counts
its own shelves; a warehouse counter counts the warehouse.

A Point of Sale that enforces the check with **no** locations chosen is refused
at save time. Without one, every product would read as out of stock and the
module would look broken.

Where the check happens
-----------------------
Every route into an order - clicking a product, scanning a barcode, typing a
quantity - passes through the same point, so none of them can slip past the
check.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['point_of_sale', 'stock'],
    'data': ['views/pos_config_views.xml'],
    'assets': {
        'point_of_sale.assets': [
            'pos_stock_enhancements/static/src/js/pos_stock.js',
        ],
    },
    'images': ['static/description/banner.gif'],
    'installable': True,
    'application': False,
}
