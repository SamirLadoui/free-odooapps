# -*- coding: utf-8 -*-
"""Cost, for the people who are meant to see it.

Odoo already keeps the cost away from portal and public users - the field
carries groups="base.group_user" out of the box. What it has no answer for is
the salesperson, the stock clerk or the shop assistant who is an internal user
and has no business knowing what the company pays.

The same mechanism is used, narrowed to a group of its own. That matters: a
field restricted this way is gone from every form, list, kanban, export and
RPC call at once, rather than merely hidden on the screens somebody remembered
to edit.
"""
from odoo import fields, models

GROUP = 'sl_hide_cost.group_show_cost'


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Only the groups attribute is given: everything else about the field -
    # its compute, its inverse, its digits - is whatever this release says.
    standard_price = fields.Float(groups=GROUP)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    standard_price = fields.Float(groups=GROUP)
