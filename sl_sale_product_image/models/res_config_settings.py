# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sale_report_show_image = fields.Boolean(
        related='company_id.sale_report_show_image', readonly=False)
    sale_report_image_size = fields.Integer(
        related='company_id.sale_report_image_size', readonly=False)
