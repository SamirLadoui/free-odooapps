# -*- coding: utf-8 -*-
{
    'name': 'Product Brands',
    'version': '18.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Group products by brand, then filter and report on them',
    'description': """
Product Brands
==============

A brand is not a product category. Categories are how you account for a product;
brands are who made it. Trying to express both in one hierarchy is where product
data usually goes wrong.

This adds brands as their own thing:

* A **Brand** field on the product, with its own filter and group-by in the
  product search.
* Brands with a logo, a short code, a website and an optional link to the
  manufacturer's contact record.
* A product count on each brand, and a button through to those products.

Brand names and codes are unique, so the same brand cannot be typed in twice
under two spellings and quietly split your reporting in half.

A brand that still has products cannot be deleted, only archived, so historical
orders keep meaning what they meant.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['product', 'sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_brand_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
