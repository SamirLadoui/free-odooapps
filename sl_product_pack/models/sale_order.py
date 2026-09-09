# -*- coding: utf-8 -*-
"""Putting the parts on the order.

At confirmation rather than while the quotation is being typed: a quotation
should read the way it was sold - one line saying "Starter Kit" - and the
warehouse needs the parts. Confirming is the moment those two stop being the
same thing.

Exploding is done once. A pack line that already has its parts is left alone,
so confirming an order that was cancelled and confirmed again does not put
the contents on twice.
"""
from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        self._sl_explode_packs()
        return super().action_confirm()

    def action_sl_explode_packs(self):
        """The same thing, from a button, for anyone who wants to see it
        before they confirm."""
        self._sl_explode_packs()
        return True

    def _sl_explode_packs(self):
        for order in self:
            for line in order.order_line:
                if not line._sl_is_pack() or line.sl_pack_parent_id:
                    continue
                if line.sl_pack_child_ids:
                    continue
                order._sl_explode_line(line)
        return True

    def _sl_explode_line(self, line):
        """One pack line becomes itself plus its parts."""
        self.ensure_one()
        template = line.product_id.product_tmpl_id
        contents = template.sl_pack_line_ids
        if not contents:
            raise UserError(_(
                '%s is a pack with nothing in it, so there is nothing to '
                'deliver. Add its parts, or take it off the order.',
                line.product_id.display_name))
        detailed = template.sl_pack_type == 'detailed'
        created = self.env['sale.order.line']
        for content in contents:
            created |= self.env['sale.order.line'].create(
                line._sl_component_values(content, detailed))
        if detailed:
            # The parts carry the money, so the pack line must not as well.
            line.price_unit = 0.0
        return created


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    sl_pack_parent_id = fields.Many2one(
        'sale.order.line', string='Part Of', ondelete='cascade',
        index=True, copy=False,
        help='The pack line this part came from.')
    sl_pack_child_ids = fields.One2many(
        'sale.order.line', 'sl_pack_parent_id', string='Parts', copy=False)

    def _sl_is_pack(self):
        self.ensure_one()
        return bool(self.product_id
                    and self.product_id.product_tmpl_id.sl_pack_ok)

    def _sl_component_price(self, product, quantity):
        """What a part costs on this order, asked of the pricelist.

        The signature moved in 16.0, so the newer one is preferred and the
        older is the fallback rather than the other way round.
        """
        self.ensure_one()
        pricelist = self.order_id.pricelist_id
        if not pricelist:
            return product.lst_price
        if hasattr(pricelist, '_get_product_price'):
            return pricelist._get_product_price(product, quantity)
        return pricelist.get_product_price(
            product, quantity, self.order_id.partner_id)

    def _sl_component_values(self, content, detailed):
        """One part of a pack, as an order line."""
        self.ensure_one()
        quantity = self.product_uom_qty * content.quantity
        values = {
            'order_id': self.order_id.id,
            'product_id': content.product_id.id,
            'name': content.product_id.display_name,
            'product_uom_qty': quantity,
            'sequence': self.sequence,
            'sl_pack_parent_id': self.id,
            # Set outright rather than left to the pricelist: a part of a
            # fixed-price pack is already paid for by the pack.
            'price_unit': (self._sl_component_price(content.product_id,
                                                    quantity)
                           if detailed else 0.0),
        }
        if 'product_uom' in self._fields and content.product_id.uom_id:
            values['product_uom'] = content.product_id.uom_id.id
        return values
