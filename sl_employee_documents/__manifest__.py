# -*- coding: utf-8 -*-
{
    'name': 'Employee Documents',
    'version': '15.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Track employee documents and their expiry dates, with reminders',
    'description': """
Employee Documents
==================

Passports, visas, work permits, driving licences, contracts and certificates,
with the dates that matter and a reminder before anything lapses.

The status is the point
-----------------------
Every document works out for itself whether it is **valid**, **expiring soon**,
**expired**, or has no expiry at all. "Expiring soon" is defined per document
type: passports might warn 90 days ahead while a parking permit warns 7.

Reminders
---------
A daily scheduled action finds every document that is expiring or already
expired, notes it in the document's own log, and raises an activity for whoever
is responsible - or the employee's manager if nobody is named. Each document is
chased once a day at most, so nobody drowns in duplicates.

The default view opens on exactly the documents that need attention.

Also
----
* A Documents button on the employee form.
* Document types you define yourself, each with its own warning window and its
  own answer to "does this even expire?".
* A document that expires before it was issued is refused.

The reminder scheduled action ships disabled. Turn it on once your documents are
loaded and you have checked the list.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['hr', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/employee_document_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
