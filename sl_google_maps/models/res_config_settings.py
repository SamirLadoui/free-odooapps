# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    google_maps_api_key = fields.Char(
        related='company_id.google_maps_api_key', readonly=False)
    google_maps_zoom = fields.Integer(
        related='company_id.google_maps_zoom', readonly=False)
