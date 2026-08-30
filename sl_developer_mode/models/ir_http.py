# -*- coding: utf-8 -*-
from odoo import models
from odoo.http import request

# What Odoo's own debug parameter expects for each of our settings.
DEBUG_VALUES = {'on': '1', 'assets': 'assets'}


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """Put the user into developer mode as their session is described.

        session_info runs on every page load, so this survives a logout, a
        cleared cache or a brand new browser, which is the whole point: the
        alternative is re-enabling it by hand several times a day.
        """
        info = super().session_info()
        setting = self.env.user.auto_developer_mode
        if setting and setting != 'off' and self.env.user.has_group('base.group_system'):
            debug = DEBUG_VALUES.get(setting, '1')
            if request and not request.session.debug:
                request.session.debug = debug
            info['is_admin'] = info.get('is_admin', True)
            info['debug'] = debug
        return info
