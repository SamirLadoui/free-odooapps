# -*- coding: utf-8 -*-
{
    'name': 'Configuration Recorder',
    'version': '14.0.1.0.0',
    'category': 'Technical',
    'summary': 'Record configuration changes and download them as an installable module',
    'description': """
Configuration Recorder
======================

Set up something in the Odoo interface, then take that configuration away as a
proper module you can put in version control or install on another database.

How it works
------------
1. Pick the models you are about to change.
2. Press **Start Recording**.
3. Go and configure whatever you were going to configure, anywhere in Odoo.
4. Come back and press **Stop Recording**.
5. Review what was caught, untick anything you do not want, and download a zip.

The zip is a real module: a manifest, an ``__init__.py`` and a data file of XML
records, ready to drop into an addons path.

Recorded by timestamp, not by patching
--------------------------------------
Changes are found by comparing write timestamps in the window you defined.
Nothing patches the ORM, nothing is slowed down while you are not recording, and
a recording survives a server restart.

Honest about what it can export
-------------------------------
* Scalar fields are written out as you would write them by hand.
* A link to another record becomes ``ref="module.xml_id"`` when the target has
  an external ID.
* When the target has **no** external ID the link is **left out**, because a raw
  database id would not survive an install on another database. Better a field
  you can see is missing than one that silently points at the wrong row.
* Lists of records and binary fields are not exported.
* Odoo's own bookkeeping fields are never exported.

Review the generated XML before you rely on it. This is a very good first draft
of a configuration module, not a substitute for reading it.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/module_record_views.xml',
    ],
    'external_dependencies': {'python': ['lxml']},
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
