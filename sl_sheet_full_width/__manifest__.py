# -*- coding: utf-8 -*-
{
    'name': 'Full Width Form Sheets',
    'version': '14.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Use the whole window for form views instead of a narrow column',
    'description': """
Full Width Form Sheets
======================

Odoo caps the width of a form sheet so that long documents stay readable. On a
wide monitor, and on a database full of forms with many columns, that cap wastes
half the screen and forces horizontal scrolling inside one-to-many lists.

This lifts the cap. Form views use the full window width.

Settings pages are deliberately left alone: they are laid out in fixed columns
and stretching them makes them harder to read, not easier.

There is nothing to configure. Install it and the forms are wider; uninstall it
and they are not.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'data': ['views/assets.xml'],
    'depends': ['web'],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
