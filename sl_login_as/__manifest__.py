# -*- coding: utf-8 -*-
{
    'name': 'Log In As Another User',
    'version': '15.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'See what a user sees, with a reason and a record that cannot be erased',
    'description': """
Log In As Another User
======================

Somebody reports that a button is missing, and the only way to see what they
see is to be them. The usual answer is to reset their password, which locks
them out and tells you nothing afterwards.

This opens a session as that user instead, and writes down that it happened.

What is refused
---------------
Somebody cannot take an account with rights their own does not already have.
The rule is not seniority, it is containment: every right the target has, the
person taking it must already hold. A support account that could become
somebody more powerful has effectively granted itself that power, and this
would be a way around the access rights the database already has rather than a
support tool.

The reason is asked first
-------------------------
Before the session starts, not remembered afterwards. It is the only part of
the record that says what the session was for.

The record cannot be tidied away
--------------------------------
Who did it, whose account, when and why - and the entry cannot be edited or
deleted by anybody, including whoever created it. A log an administrator can
clean up is not a log.

Not by url
----------
The address that hands over the session checks the same rule again and refuses
unless a reason was recorded for that pair moments before, so pasting the link
is not a way around the question.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/login_as_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
