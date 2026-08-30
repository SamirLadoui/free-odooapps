# -*- coding: utf-8 -*-
{
    'name': 'Sticky List Headers',
    'version': '17.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Keep list column headings and totals visible while you scroll',
    'description': """
Sticky List Headers
===================

Scroll a few hundred rows down a list and the column headings are long gone. You
are left guessing which column is the quantity and which is the price, and
scrolling back up to check.

This pins them. The heading row stays at the top of the list while the rows move
under it, and the totals row stays at the bottom, which on a long list is just as
useful as the headings.

There is nothing to configure. Install it and the headers stay put.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['web'],
    'assets': {
        'web.assets_backend': [
            'sl_listview_sticky_header/static/src/scss/sticky_header.scss',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
