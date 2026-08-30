# -*- coding: utf-8 -*-
{
    'name': 'Mass Label Reporting',
    'version': '15.0.1.0.0',
    'category': 'Technical',
    'summary': 'Print label sheets for any records you select',
    'description': """
Mass Label Reporting
====================

Select records in any list, choose a grid, and print a sheet of labels.

Odoo prints product labels in a fixed layout. This prints labels for **any**
model - products, product variants, contacts - on a grid you decide, so the
sheet matches the label paper you actually bought.

Details worth knowing
---------------------
* Labels per row and rows per page are yours to set, within sensible bounds
  (up to 10 across and 30 down). Beyond that the text stops fitting.
* Copies of each: print ten of one product without selecting it ten times.
* Internal reference, barcode and price are optional, and are simply skipped
  on models that do not have them. The same wizard works on a contact.
* The last row is padded with empty cells so the labels stay aligned with the
  sheet. Without the padding the final row stretches and every label on it is
  printed in the wrong place.
* Records deleted between opening the wizard and printing are dropped rather
  than raising, and your access rights are checked before anything is read.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base', 'product'],
    'data': [
        'security/ir.model.access.csv',
        'report/label_templates.xml',
        'views/label_wizard_views.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'sl_mass_label/static/src/css/label.css',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
