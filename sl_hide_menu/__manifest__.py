# -*- coding: utf-8 -*-
{
    'name': 'Hide Menus Per User',
    'version': '17.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Remove menus a particular user does not need to see',
    'description': """
Hide Menus Per User
===================

Pick the menus a user should not see and they disappear from their interface.

Hiding a parent takes its sub-menus with it. Otherwise the children are left
stranded in the app switcher with no route back to them, which is worse than
leaving the whole branch alone.

It is per user, so tidying one person's interface never touches anybody else's,
and it is reversible: untick and the menu comes back.

What this is not
----------------
This is **not** a security control. Hiding a menu removes it from the interface
and nothing else. The user keeps every access right they had, and anything they
could reach another way - a direct link, a related record, the API - they can
still reach.

If you need somebody genuinely unable to see data, change their groups or add a
record rule. Use this to make a cluttered interface manageable, which is the
problem it actually solves.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': ['views/res_users_views.xml'],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
