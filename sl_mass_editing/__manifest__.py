# -*- coding: utf-8 -*-
{
    'name': 'Mass Editing',
    'version': '14.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Change the same fields on many records at once, from the Action menu',
    'description': """
Mass Editing
============

Select a hundred records in any list view and change the same fields on all of
them in one step, without a developer and without a server action full of code.

How it works
------------
1. An administrator defines a **bulk edit**: a model, and the list of fields that
   may be changed through it.
2. That entry appears in the **Action** menu of the model's list view.
3. A user selects records, picks the entry, and gets a form offering exactly the
   fields the administrator allowed.

Operations
----------
* **Set to** - give the field a new value.
* **Clear** - empty the field.
* **Add** / **Remove** - on tag-style fields, add or take away one linked record
  without disturbing the rest. Stack several lines to add several tags at once.

Guardrails
----------
* The configured field list is the boundary, enforced on the server: a request
  naming any other field is rejected, not silently applied.
* Records are written as the user who pressed Apply, with no elevation of
  privilege, so normal Odoo access rights still decide what may change.
* Selection values are checked against the field's real options, so a typo is
  refused instead of writing a value that breaks the record later.
* Odoo's own bookkeeping fields (create date, write user, and so on) can never be
  added to a bulk edit.
* The form states how many records are about to change, and asks for confirmation.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/mass_editing_wizard_views.xml',
        'views/mass_editing_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
