# -*- coding: utf-8 -*-
{
    'name': 'Sale Rental',
    'version': '14.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Hire products out by the day, week or month, on ordinary sale orders',
    'description': """
Sale Rental
===========

Rent products out on the same sale orders you already use. Tick a line as a
rental, give it a hire date and a return date, and it prices itself.

Pricing that makes sense to a customer
--------------------------------------
Set a daily, weekly and monthly rate on the product. A hire is priced using the
largest rates first, so 38 days is a month plus a week plus a day rather than 38
separate days. A longer hire is never dearer than a shorter one - there is a test
that walks every duration from one day to two months to prove it.

A rate you have not set is skipped, not treated as free: if you only have a
weekly rate, a nine-day hire still costs more than a week.

Availability that holds
-----------------------
Each product records how many units you own. Confirming an order checks the
window against every other confirmed hire and refuses the booking once they are
all out, naming how many are free and when.

Quotations deliberately hold nothing. If a draft blocked stock, one abandoned
quotation would take an item off the market forever.

Details
-------
* Both ends are inclusive: out and back on the same day is one day's hire, not
  zero.
* A line marked rental must have both dates, and a return cannot precede the
  collection.
* A product not marked rentable cannot be put on a rental line.
* A product marked rentable with no rate at all is refused, because it would go
  out for nothing.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['sale_management'],
    'data': ['views/rental_views.xml'],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
