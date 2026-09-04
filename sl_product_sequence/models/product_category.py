# -*- coding: utf-8 -*-
"""Where a product's reference number comes from.

The internal reference is what everyone types into a search box, reads down
the phone and writes on a shelf label, and Odoo leaves it blank. What people
do instead is invent one per product by hand, which gives CH-001, ch002 and
Chair 3 in the same catalogue by the end of the month.

A sequence on the category settles it. Categories inherit from their parents,
so "Furniture" can number everything under it and "Furniture / Office Chairs"
can still have its own if it earns one.
"""
from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = 'product.category'

    sl_sequence_id = fields.Many2one(
        'ir.sequence', string='Reference Numbering', copy=False,
        help='Products in this category are numbered from here. Left empty, '
             'the nearest parent category that has one is used, and failing '
             'that the company default.')

    def _sl_sequence(self):
        """The numbering for this category, inherited from its parents."""
        self.ensure_one()
        category = self
        while category:
            if category.sl_sequence_id:
                return category.sl_sequence_id
            category = category.parent_id
        return self.env['ir.sequence'].browse()


class ResCompany(models.Model):
    _inherit = 'res.company'

    sl_product_sequence_id = fields.Many2one(
        'ir.sequence', string='Product Reference Numbering', copy=False,
        help='Used for products whose category has no numbering of its own. '
             'Empty means products are not numbered automatically at all.')
