# -*- coding: utf-8 -*-
{
    'name': 'Attachment Preview',
    'version': '18.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Open any attachment in a preview page instead of downloading it',
    'description': """
Attachment Preview
==================

Adds a **Preview** button to every attachment. Instead of downloading a file to
find out what is in it, you get a page that shows it.

Handles
-------
* **Images** - fitted to the window, on a neutral background.
* **PDF** - rendered inline, fitted to the page width.
* **Text** - .txt, .csv, .log, .json, .xml, .sql, .yaml and friends, shown in a
  scrollable pane. This is the useful part: browsers download most of these
  rather than displaying them.
* **Video and audio** - with the browser's own player.
* **Anything else** - a clear "no preview for this type" card with a download
  button, rather than a broken embed.

Also
----
* A **Preview** column and button in the attachment list, so you can tell at a
  glance which files can be looked at.
* Previous / next arrows walk the other attachments of the same record, so you
  can page through everything attached to an order or an invoice.
* Large text files are truncated at 200 KB, with a note, so opening a big log
  does not hang the browser.

Access
------
The preview page reads the attachment as the logged-in user, with no elevation
of privilege anywhere. Normal Odoo attachment access rules decide what each user
may open, and anonymous visitors are sent to the login page.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [
        'views/preview_templates.xml',
        'views/ir_attachment_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'sl_attachment_preview/static/src/css/preview.css',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
