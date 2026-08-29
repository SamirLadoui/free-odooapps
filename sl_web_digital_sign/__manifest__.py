# -*- coding: utf-8 -*-
{
    'name': 'Web Digital Signature',
    'version': '18.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Capture a hand-drawn signature on any record, with a full audit trail',
    'description': """
Web Digital Signature
=====================

Make any model signable, then capture a hand-drawn signature straight from its
list or form view.

How it works
------------
1. An administrator marks a model as signable and names the menu entry.
2. **Sign this record** appears in that model's **Action** menu.
3. A user selects one or more records, draws the signature, and confirms.

What gets recorded
------------------
Every signature is a permanent record holding who signed, their email, the
signature image, the exact timestamp, the originating IP address, and which
Odoo user captured it. Nothing is editable after the fact.

On the signed record
--------------------
* A PNG copy of the signature is attached, so it travels with the record - into
  exports, into emails, wherever the record goes.
* A line is posted in the record's chatter naming the signer and the date.

Guardrails
----------
* Signing requires **write** access on the record. Someone who cannot edit a
  record cannot sign it either.
* The signature log survives deletion of the record it refers to, which is the
  point of an audit trail: entries show "(deleted)" rather than disappearing.
* Email addresses and model names are validated before anything is stored.
* Signatures are read-only for ordinary users; only Settings administrators can
  amend or delete them.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/signature_wizard_views.xml',
        'views/signature_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
