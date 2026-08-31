# -*- coding: utf-8 -*-
{
    'name': 'Invoice Format Editor',
    'version': '15.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Choose which columns and headings appear on the printed invoice',
    'description': """
Invoice Format Editor
=====================

Change what the printed invoice shows, from Settings, without editing a QWeb
template or writing a module.

Columns
-------
Show or hide the quantity, unit price and taxes columns, and optionally print
the product image on each line.

Quantity and unit price cannot both be hidden. If they were, the customer would
have no way to check how the subtotal was arrived at, and that is not a layout
choice - it is a broken invoice.

Headings
--------
Rename the description, quantity, unit price and subtotal headings. "Qty" and
"Rate" instead of "Quantity" and "Unit Price", if that is your house style.
Leave a heading empty and Odoo's own wording is used, translations included.

Footer note
-----------
A block of text printed under every invoice, above the company footer. Payment
terms, a bank reference, a legal notice - whatever needs to be on every one,
maintained by the person who cares about it rather than a developer.

All settings are per company, so a multi-company database can print differently
for each.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': ['views/report_invoice_format.xml'],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
