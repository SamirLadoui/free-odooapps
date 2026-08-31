# -*- coding: utf-8 -*-
{
    'name': 'Automatic Developer Mode',
    'version': '15.0.1.0.0',
    'category': 'Technical',
    'summary': 'Keep developer mode on for the users who always want it',
    'description': """
Automatic Developer Mode
========================

If you work in developer mode, you turn it on several times a day: after a
logout, after clearing the cache, in every new browser, in every incognito
window. This makes it stick.

Set it once on your user and developer mode is on whenever you log in, with the
choice of plain developer mode or developer mode with assets.

Restricted on purpose
---------------------
Only **Settings administrators** can be put into automatic developer mode.
Developer mode exposes technical menus and internal fields, and someone who is
not already an administrator has no business being dropped into it by a setting
they may not understand.

The check runs whenever the setting is written, so an administrator who later
loses those rights cannot keep it.

The setting lives on the user's own preferences, so a developer can turn it on
for themselves without asking anyone.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': ['views/res_users_views.xml'],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
