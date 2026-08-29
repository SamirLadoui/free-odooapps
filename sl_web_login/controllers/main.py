# -*- coding: utf-8 -*-
import base64

from odoo import http
from odoo.http import request

# The login screen is public, so these routes are too. They expose only what an
# administrator has explicitly uploaded to be shown on it.
CACHE = 300


class SlWebLogin(http.Controller):

    def _company(self):
        return request.env['res.company']._sl_login_company()

    def _image(self, field):
        company = self._company()
        data = company and company[field]
        if not data:
            return request.not_found()
        return request.make_response(
            base64.b64decode(data),
            [('Content-Type', 'image/png'), ('Cache-Control', 'public, max-age=%d' % CACHE)])

    @http.route('/sl_web_login/style.css', type='http', auth='public', sitemap=False)
    def login_style(self, **kw):
        css = request.env['res.company']._sl_login_css()
        return request.make_response(
            css,
            [('Content-Type', 'text/css; charset=utf-8'),
             ('Cache-Control', 'public, max-age=%d' % CACHE)])

    @http.route('/sl_web_login/background', type='http', auth='public', sitemap=False)
    def login_background(self, **kw):
        return self._image('login_background')

    @http.route('/sl_web_login/logo', type='http', auth='public', sitemap=False)
    def login_logo(self, **kw):
        return self._image('login_logo')
