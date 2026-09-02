# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PosConfig(models.Model):
    _inherit = 'pos.config'

    available_stock_location_ids = fields.Many2many(
        'stock.location',
        string='Available Stock Locations',
        domain="[('usage', '=', 'internal')]",
        help="Locations checked for product availability in this Point of Sale. "
             "Stock anywhere else is ignored.")
    enforce_pos_stock_check = fields.Boolean(
        string="Enforce Stock Check in POS",
        default=True,
        help="Verify stock availability before a product is added to an order.")

    @api.onchange('enforce_pos_stock_check')
    def _onchange_enforce_pos_stock_check(self):
        """Clear the locations only when the check is switched off.

        The original cleared them on every change, which wiped the locations
        you had just chosen the moment you ticked the box.
        """
        if not self.enforce_pos_stock_check:
            self.available_stock_location_ids = False

    @api.constrains('enforce_pos_stock_check', 'available_stock_location_ids')
    def _check_stock_locations(self):
        """Enforcing the check with no locations makes everything read as out
        of stock, which looks like the module is broken. Catch it here instead."""
        for config in self:
            if config.enforce_pos_stock_check and not config.available_stock_location_ids:
                raise ValidationError(_(
                    "%s enforces the stock check, so it needs at least one "
                    "available stock location. Without one, every product would "
                    "be treated as out of stock.") % config.name)
