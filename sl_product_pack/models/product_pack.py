# -*- coding: utf-8 -*-
"""A product that is really several products.

The starter kit, the gift set, the "buy the whole shelf" bundle. Odoo can do
this with a manufacturing bill of materials marked as a kit, which means
installing Manufacturing to sell a hamper.

A pack is a product with a list of what is in it. Sell the pack and the order
carries the parts, so the warehouse picks the parts and the customer reads
what they are getting.

A pack cannot itself be stocked. If it were, the order would reserve the pack
and its contents at once and the same goods would go out twice.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

PACK_TYPES = [
    ('fixed', 'One Price For The Pack'),
    ('detailed', 'Priced Line By Line'),
]


def is_storable(template):
    """Whether Odoo counts this product, on any release.

    18.0 split being counted out of the product type; before it, a counted
    product is simply of type 'product'.
    """
    if 'is_storable' in template._fields:
        return bool(template.is_storable)
    return template.type == 'product'


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    sl_pack_ok = fields.Boolean(
        string='Is A Pack',
        help='Selling this puts its contents on the order instead.')
    sl_pack_type = fields.Selection(
        PACK_TYPES, string='Pack Pricing', default='fixed', required=True,
        help='One price for the pack shows the parts at no charge. Priced '
             'line by line charges for each part and leaves the pack itself '
             'at nothing.')
    sl_pack_line_ids = fields.One2many(
        'sl.product.pack.line', 'pack_tmpl_id', string='What Is In It',
        copy=True)

    @api.constrains('sl_pack_ok', 'type')
    def _check_pack_is_not_stocked(self):
        for template in self:
            if template.sl_pack_ok and is_storable(template):
                raise ValidationError(_(
                    'A pack cannot be a product you count. The parts are what '
                    'leaves the warehouse; counting the pack as well would '
                    'send the same goods out twice. Make %s a service or an '
                    'uncounted product.', template.display_name))

    @api.constrains('sl_pack_ok', 'sl_pack_line_ids')
    def _check_pack_has_contents(self):
        for template in self:
            if template.sl_pack_ok and not template.sl_pack_line_ids:
                raise ValidationError(_(
                    'A pack with nothing in it would put nothing on the '
                    'order. Add what %s contains.', template.display_name))


class ProductPackLine(models.Model):
    _name = 'sl.product.pack.line'
    _description = 'Pack Content'
    _order = 'sequence, id'

    pack_tmpl_id = fields.Many2one(
        'product.template', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        'product.product', string='Part', required=True,
        help='What goes in the pack.')
    quantity = fields.Float(
        string='How Many', default=1.0, required=True,
        digits='Product Unit of Measure')

    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_(
                    'A pack part with no quantity does nothing. Give %s a '
                    'quantity above zero.', line.product_id.display_name))

    @api.constrains('product_id', 'pack_tmpl_id')
    def _check_not_a_pack_inside_a_pack(self):
        """Packs do not nest.

        Allowing it means allowing a pack that eventually contains itself,
        and an order that never finishes exploding. One level, and a plain
        refusal, is worth more than a clever cycle check nobody trusts.
        """
        for line in self:
            if line.product_id.product_tmpl_id.sl_pack_ok:
                raise ValidationError(_(
                    '%s is itself a pack. Packs do not go inside packs: list '
                    'the parts directly.', line.product_id.display_name))
            if line.product_id.product_tmpl_id == line.pack_tmpl_id:
                raise ValidationError(_('A pack cannot contain itself.'))
