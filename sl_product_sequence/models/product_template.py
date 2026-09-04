# -*- coding: utf-8 -*-
"""Giving a product its reference the moment it is created.

Only when the field was left empty. Somebody who typed a reference meant it,
and a manufacturer's part number is worth more than a number we invented.
"""
from odoo import api, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _sl_sequence(self):
        """The numbering that applies to this product, if any."""
        self.ensure_one()
        sequence = self.categ_id._sl_sequence() if self.categ_id \
            else self.env['ir.sequence'].browse()
        if sequence:
            return sequence
        company = self.company_id or self.env.company
        return company.sl_product_sequence_id

    def _sl_next_reference(self):
        self.ensure_one()
        sequence = self._sl_sequence()
        return sequence.sudo().next_by_id() if sequence else False

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        for template, values in zip(templates, vals_list):
            if values.get('default_code'):
                continue
            reference = template._sl_next_reference()
            if reference:
                template.default_code = reference
        return templates
