from odoo import api, models


class ProductProduct(models.Model):
    _inherit = 'product.product'


    @api.model
    def get_product_stock_for_pos(self, product_ids, location_ids):
        """
        Fetches the available quantity for a list of products in specified locations.
        Returns a dictionary {product_id: quantity}
        """
        if not product_ids or not location_ids:
            return {prod_id: 0 for prod_id in product_ids}

        products = self.browse(product_ids).filtered(lambda p: p.type == 'product')
        if not products:
             return {prod_id: 0 for prod_id in product_ids}

        res = {prod.id: 0 for prod in products}
        domain = [
            ('product_id', 'in', products.ids),
            ('location_id', 'in', location_ids),
        ]

        quants = self.env['stock.quant'].read_group(
            domain,
            ['product_id', 'quantity'],
            ['product_id'],
        )

        for quant_data in quants:
            res[quant_data['product_id'][0]] = quant_data['quantity']
        
        for prod_id in product_ids:
            if prod_id not in res:
                res[prod_id] = 0
        return res