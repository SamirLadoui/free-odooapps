# -*- coding: utf-8 -*-
{
    'name': 'Quality Management',
    'version': '14.0.1.0.0',
    'category': 'Manufacturing/Quality',
    'summary': 'Non-conformities, root cause analysis and corrective actions',
    'description': """
Quality Management
==================

The core of a quality system: something went wrong, why did it go wrong, and
what are we doing about it.

A workflow that cannot be short-circuited
-----------------------------------------
Reported, under analysis, actions in progress, closed. Two gates make the record
worth keeping:

* You cannot raise actions without a **root cause**. An action without a cause
  is a guess.
* You cannot **close** without a root cause and with actions still open. Closing
  a non-conformity is the claim that it will not happen again, so it has to be
  earned.

Cancelled actions do not block closing - deciding not to do something is a
decision, not an omission.

Actions that chase themselves
-----------------------------
Each action has an owner, a deadline and a type: **corrective** fixes what went
wrong, **preventive** stops it happening somewhere it has not yet. Overdue
actions colour red in the list, are counted on the non-conformity, and can be
filtered on. Finishing late clears the flag, because finishing late is still
finishing.

An action due before the non-conformity was reported is refused, since that is
always a typo.

Also
----
* Origin (internal, customer complaint, supplier, audit) and severity, both
  filterable and groupable.
* Immediate containment recorded separately from the root cause: what you did in
  the first hour is not the same as what you concluded in the first week.
* Two access levels: users report and work, managers close.
* The list opens on what is still open.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/quality_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'views/quality_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
