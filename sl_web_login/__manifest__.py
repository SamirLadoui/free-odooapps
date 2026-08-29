# -*- coding: utf-8 -*-
{
    'name': 'Login Screen Branding',
    'version': '15.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Brand the Odoo login screen: background image, logo, colours, footer text',
    'description': """
Login Screen Branding
=====================

Make the login screen look like your company instead of a stock Odoo install,
without touching a single template.

Everything is configured from **Settings > General Settings > Login Screen**:

* Full-bleed background image, with an optional blur so the login card stays readable.
* Background colour, used on its own or behind the image while it loads.
* A login-only logo, so you can use a wordmark on the login page and a compact
  mark everywhere else.
* Card width, logo height and primary button colour.
* Your own footer text, e.g. an internal support address.
* Hide the "Manage Databases" link, or the whole footer.

Notes
-----
Hiding the "Manage Databases" link removes it from the page. It does not block
the route: set ``list_db = False`` in your Odoo configuration file if you need
the database manager actually disabled.

Colours are validated as hex values before they reach the stylesheet, and image
and size settings are range-checked.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base_setup', 'web'],
    'data': [
        'views/login_templates.xml',
        'views/res_config_settings_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
