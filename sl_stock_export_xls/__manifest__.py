# -*- coding: utf-8 -*-
{
    'name': 'Export Product Stock to Excel',
    'version': '16.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Export on-hand, reserved and forecasted stock to a filtered .xlsx file',
    'description': """
Export Product Stock to Excel
=============================

One wizard that turns your stock into a spreadsheet you can actually work with.

Two shapes
----------
* **One row per product** - a stock summary: on hand, reserved, available and
  forecasted, per product.
* **One row per product and location** - the same quantities broken down by
  where the goods physically are, optionally down to the lot or serial number.

Filters
-------
Warehouses, internal locations, product categories, or an explicit list of
products. Filters combine, they never widen: naming a product outside your
chosen category will not pull it back into the export.

Options
-------
* Include products with no stock, for a full catalogue listing.
* Break down by lot / serial number.
* Include unit cost and stock value columns.

The generated file has a frozen header row and an autofilter already applied, so
it is ready to sort and pivot the moment it opens.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_export_wizard_views.xml',
    ],
    'external_dependencies': {'python': ['xlsxwriter']},
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
