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

    # 14.0 keeps these as plain class attributes; they only became properties
    # in 15.0, so the list is extended once when the registry is built.
    def __init__(self, pool, cr):
        super().__init__(pool, cr)
        model = type(self)
        for name in ('SELF_READABLE_FIELDS', 'SELF_WRITEABLE_FIELDS'):
            current = list(getattr(model, name, []))
            if 'auto_developer_mode' not in current:
                setattr(model, name, current + ['auto_developer_mode'])
