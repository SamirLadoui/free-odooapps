# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    sl_allow_returns = fields.Boolean(
        string='Allow Returns',
        help='Show the Return button in this point of sale, so a cashier can '
             'call up a past receipt and give items back against it.')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_sl_allow_returns = fields.Boolean(
        related='pos_config_id.sl_allow_returns', readonly=False)
