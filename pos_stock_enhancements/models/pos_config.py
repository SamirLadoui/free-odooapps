from odoo import fields, models, api


class PosConfig(models.Model):
    _inherit = 'pos.config'

    available_stock_location_ids = fields.Many2many(
        'stock.location',
        string='Available Stock Locations',
        help="Locations to check for product availability in this POS. "
             "If empty, it might default to main stock location or all locations (depending on implementation).",
        domain="[('usage', '=', 'internal')]" # Only allow internal locations
    )
    # Boolean to enable/disable the feature per POS config
    enforce_pos_stock_check = fields.Boolean(
        string="Enforce Stock Check in POS",
        default=True,
        help="If checked, stock availability will be verified before adding products to order."
    )


    @api.onchange('enforce_pos_stock_check')
    def _onchange_enforce_pos_stock_check(self):
        self.available_stock_location_ids = False