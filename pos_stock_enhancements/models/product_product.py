# -*- coding: utf-8 -*-
from odoo import api, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _pos_stock_storable_domain(self):
        """18.0 replaced the 'product' product type with consu + is_storable."""
        if 'is_storable' in self._fields:
            return [('is_storable', '=', True)]
        return [('type', '=', 'product')]

    @api.model
    def get_product_stock_for_pos(self, product_ids, location_ids):
        """Available quantity per product across the given locations.

        Returns {product_id: quantity} covering every id asked for, so the
        caller never has to guess whether a missing key means zero or an error.
        """
        result = {product_id: 0 for product_id in (product_ids or [])}
        if not product_ids or not location_ids:
            return result

        storable = self.browse(product_ids).exists().filtered_domain(
            self._pos_stock_storable_domain())
        if not storable:
            return result

        grouped = self.env['stock.quant'].read_group(
            [('product_id', 'in', storable.ids),
             ('location_id', 'in', location_ids)],
            ['product_id', 'quantity'],
            ['product_id'])
        for row in grouped:
            if row.get('product_id'):
                result[row['product_id'][0]] = row['quantity'] or 0
        return result
