# -*- coding: utf-8 -*-
{
    'name': 'Product Return In POS',
    'version': '17.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Give items back against a past receipt, from the till',
    'description': """
Product Return In POS
=====================

A customer comes back with a receipt and two of the four things they bought.
The cashier types the receipt number, ticks those two lines, and the return is
recorded against the original order.

How it works
------------
* Find the order by receipt reference **or** order name, because which one is
  printed depends on how the shop is set up.
* Only what is left is offered. Bring three of five back today and two of five
  next week, and the screen shows two remaining, not five.
* A return is an ordinary point of sale order carrying negative quantities -
  the way the point of sale already records a refund - with a link back to the
  order it came from.
* A return cannot itself be returned, and an order cannot be a return of
  itself. Both are refused rather than quietly producing nonsense.

Turned on per point of sale, so a shop that does not take returns at the till
does not get the button.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['point_of_sale'],
    'data': [
        'views/pos_config_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'sl_pos_return/static/src/js/pos_return.js',
            'sl_pos_return/static/src/xml/pos_return.xml',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
