# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    invoice_show_quantity = fields.Boolean(
        related='company_id.invoice_show_quantity', readonly=False)
    invoice_show_price_unit = fields.Boolean(
        related='company_id.invoice_show_price_unit', readonly=False)
    invoice_show_taxes = fields.Boolean(
        related='company_id.invoice_show_taxes', readonly=False)
    invoice_show_product_code = fields.Boolean(
        related='company_id.invoice_show_product_code', readonly=False)
    invoice_show_product_image = fields.Boolean(
        related='company_id.invoice_show_product_image', readonly=False)
    invoice_label_description = fields.Char(
        related='company_id.invoice_label_description', readonly=False)
    invoice_label_quantity = fields.Char(
        related='company_id.invoice_label_quantity', readonly=False)
    invoice_label_price_unit = fields.Char(
        related='company_id.invoice_label_price_unit', readonly=False)
    invoice_label_subtotal = fields.Char(
        related='company_id.invoice_label_subtotal', readonly=False)
    invoice_footer_note = fields.Text(
        related='company_id.invoice_footer_note', readonly=False)
