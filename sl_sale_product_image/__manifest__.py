# -*- coding: utf-8 -*-
{
    'name': 'Product Images On Quotations',
    'version': '16.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Print each product picture beside its line on the quotation',
    'description': """
Product Images On Quotations
============================

Print the product picture beside its description on quotations and sale orders,
so a customer can see what they are buying rather than reading a code.

Switched on from Settings, with a size you choose. Off by default: turning it on
is a decision, and installing a module should not silently change the look of
every quotation you send.

Details worth knowing
---------------------
* A product with no image is simply skipped. No empty boxes, no broken image
  icons, no gap where a picture should be.
* The image sits **above the description** rather than in a new column. Adding a
  column reflows every other one and breaks the layouts other modules have
  already adjusted.
* The size is capped between 16 and 200 pixels. Larger and one line fills a page;
  smaller and it is a smudge.
* Per company, so a multi-company database can print differently for each.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['sale_management'],
    'data': ['views/report_sale_image.xml'],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
