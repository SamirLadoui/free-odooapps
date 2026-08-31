# -*- coding: utf-8 -*-
from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def _sl_google_maps_key(self):
        """The Maps key to hand this user's browser, or '' for none.

        Split out of session_info so it can be tested without an HTTP request.
        A Maps JavaScript key is public by design - the browser sends it to
        Google on every request - but it is still only given to internal users,
        and should be restricted by HTTP referrer in the Google console.
        """
        if not self.env.user._is_internal():
            return ''
        return self.env.company.google_maps_api_key or ''

    def session_info(self):
        info = super().session_info()
        info['sl_google_maps_key'] = self._sl_google_maps_key()
        return info
