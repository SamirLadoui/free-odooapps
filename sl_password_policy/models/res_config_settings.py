# -*- coding: utf-8 -*-
"""The policy, beside Odoo's own minimum length in the settings."""
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sl_password_uppercase = fields.Boolean(
        string='Require A Capital Letter',
        config_parameter='sl_password_policy.uppercase')
    sl_password_lowercase = fields.Boolean(
        string='Require A Small Letter',
        config_parameter='sl_password_policy.lowercase')
    sl_password_digit = fields.Boolean(
        string='Require A Digit',
        config_parameter='sl_password_policy.digit')
    sl_password_special = fields.Boolean(
        string='Require A Symbol',
        config_parameter='sl_password_policy.special')
    sl_password_history = fields.Integer(
        string='Passwords Remembered',
        config_parameter='sl_password_policy.history',
        help='A password cannot be reused while it is one of the last this '
             'many. Zero remembers nothing.')
    sl_password_expiry_days = fields.Integer(
        string='Password Expires After (Days)',
        config_parameter='sl_password_policy.expiry_days',
        help='Zero means passwords do not expire. Members of "Password Never '
             'Expires" are not asked either way.')
