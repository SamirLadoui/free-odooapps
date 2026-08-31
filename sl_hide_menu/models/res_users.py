# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    hidden_menu_ids = fields.Many2many(
        'ir.ui.menu', 'sl_hidden_menu_user_rel', 'user_id', 'menu_id',
        string='Hidden Menus',
        help="Menus this user will not see. Hiding a menu only removes it from "
             "the interface; it never grants or removes any access right.")
