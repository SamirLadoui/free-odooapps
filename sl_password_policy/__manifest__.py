# -*- coding: utf-8 -*-
{
    'name': 'Password Policy',
    'version': '18.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Complexity rules, no reuse of old passwords, and expiry',
    'description': """
Password Policy
===============

Odoo ships a minimum password length and nothing else. Every security
questionnaire asks for more than that, and the usual answer is a policy
written in a document that nothing enforces.

What it adds
------------
* A password can be made to contain a capital letter, a small letter, a digit
  or a symbol, in any combination.
* The last few passwords on an account can be remembered, so the same one
  cannot come back round again.
* Passwords can be made to expire after a number of days.

One place, not four
-------------------
The rules hang off the hook Odoo already has, so they are checked wherever a
password is set: the user form, the change password wizard, the signup page
and the reset link alike. There is nothing to remember to call.

Nothing is stored in the clear
------------------------------
Previous passwords are kept as hashes, using the same hashing Odoo uses for
the live password. The table can say "you have had this one before" without
being worth stealing.

A way back in
-------------
Expiry has locked people out of more systems than it has protected. Members of
the "Password Never Expires" group are never asked, so the account that has to
keep working keeps working - and a password with no recorded change date is
treated as fresh, so turning the setting on does not lock out everybody at
once.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'support': 'samir.odoo.apps2325@gmail.com',
    'license': 'LGPL-3',
    'depends': ['auth_password_policy'],
    'data': [
        'security/password_policy_groups.xml',
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
