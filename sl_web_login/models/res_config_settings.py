# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    login_background = fields.Image(related='company_id.login_background', readonly=False)
    login_background_color = fields.Char(related='company_id.login_background_color', readonly=False)
    login_background_blur = fields.Integer(related='company_id.login_background_blur', readonly=False)
    login_logo = fields.Image(related='company_id.login_logo', readonly=False)
    login_logo_height = fields.Integer(related='company_id.login_logo_height', readonly=False)
    login_card_width = fields.Integer(related='company_id.login_card_width', readonly=False)
    login_button_color = fields.Char(related='company_id.login_button_color', readonly=False)
    login_hide_db_manager = fields.Boolean(related='company_id.login_hide_db_manager', readonly=False)
    login_hide_powered_by = fields.Boolean(related='company_id.login_hide_powered_by', readonly=False)
    login_footer_text = fields.Char(related='company_id.login_footer_text', readonly=False)
