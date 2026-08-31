# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = 'res.users'

    auto_developer_mode = fields.Selection(
        [('off', 'Off'), ('on', 'Developer mode'), ('assets', 'Developer mode with assets')],
        string='Automatic Developer Mode', default='off', required=True,
        help="Turn developer mode on automatically when this user logs in, so "
             "it survives every logout, cache clear and new browser.")

    @api.constrains('auto_developer_mode')
    def _check_developer_mode_rights(self):
        """Developer mode exposes technical menus. Only somebody who already
        has Settings access has any business being put into it automatically."""
        for user in self.filtered(lambda u: u.auto_developer_mode != 'off'):
            if not user.has_group('base.group_system'):
                raise ValidationError(_(
                    "%s is not a Settings administrator, so automatic developer "
                    "mode cannot be enabled for them.") % user.name)

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['auto_developer_mode']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['auto_developer_mode']
