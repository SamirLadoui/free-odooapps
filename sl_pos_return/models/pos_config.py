# -*- coding: utf-8 -*-
from odoo import fields, models

# res.config.settings has no pos_config_id before 16.0, so there is nowhere to
# mirror this setting into the Settings page. The switch lives on the point of
# sale itself instead - same setting, edited on the till's own form.


class PosConfig(models.Model):
    _inherit = 'pos.config'

    sl_allow_returns = fields.Boolean(
        string='Allow Returns',
        help='Show the Return button in this point of sale, so a cashier can '
             'call up a past receipt and give items back against it.')
