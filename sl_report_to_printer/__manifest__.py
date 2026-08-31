# -*- coding: utf-8 -*-
{
    'name': 'Report to Printer',
    'version': '14.0.1.0.0',
    'category': 'Technical',
    'summary': 'Send Odoo reports straight to a CUPS printer instead of downloading a PDF',
    'description': """
Report to Printer
=================

Press Print and the paper comes out, instead of a PDF landing in your downloads
folder.

How printing is decided
-----------------------
Most specific wins:

1. **The report** - e.g. delivery slips always go to the warehouse label printer.
2. **The user** - e.g. reception prints, everyone else downloads.
3. **The company** - the fallback for everything else.

A report set to print with no printer configured anywhere falls back to a normal
download, because silently printing nowhere is worse than a PDF you can see.

Printers
--------
Add a CUPS server and press **Update Printers** to pull in its queues, with make
and model, location and live status. Re-running it refreshes them rather than
creating duplicates. One printer can be marked the default, and only one.

Also
----
* A **Print Test Page** button, so a new printer is proved before anyone relies
  on it.
* Per-report copy count.
* Users pick their own printer and behaviour from their preferences.

Requirements
------------
Printing needs the ``pycups`` Python package on the Odoo server::

    pip install pycups

Odoo talks to CUPS, so the printer has to be a queue the **Odoo server** can
reach, not one attached to the user's own machine. Without pycups the module
installs and configures cleanly and tells you exactly what is missing the first
time you try to print.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/printing_views.xml',
    ],
    'external_dependencies': {'python': []},
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
