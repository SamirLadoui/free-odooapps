# -*- coding: utf-8 -*-
import base64

from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, tagged

# 1x1 transparent PNG
PIXEL = base64.b64encode(base64.b64decode(
    b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='))


@tagged('post_install', '-at_install')
class TestWebLogin(HttpCase):

    def setUp(self):
        super().setUp()
        self.company = self.env['res.company']._sl_login_company()

    def test_defaults_render(self):
        css = self.env['res.company']._sl_login_css()
        self.assertIn('background-color', css)
        self.assertIn('.o_database_list', css)

    def test_colors_reach_the_stylesheet(self):
        self.company.write({
            'login_background_color': '#123456',
            'login_button_color': '#abcdef',
        })
        css = self.env['res.company']._sl_login_css()
        self.assertIn('#123456', css)
        self.assertIn('#abcdef', css)

    def test_invalid_color_rejected(self):
        """A colour goes straight into a stylesheet, so it must be validated."""
        for bad in ('red; } body { display:none', 'nonsense', '#12345', 'url(javascript:1)'):
            with self.assertRaises(ValidationError, msg='accepted %r' % bad):
                self.company.login_background_color = bad

    def test_sizes_bounded(self):
        for field, bad in (('login_card_width', 50), ('login_card_width', 5000),
                           ('login_logo_height', 0), ('login_background_blur', 100)):
            with self.assertRaises(ValidationError, msg='accepted %s=%s' % (field, bad)):
                self.company.write({field: bad})

    def test_background_only_when_uploaded(self):
        self.company.login_background = False
        self.assertNotIn('background-image', self.env['res.company']._sl_login_css())
        self.company.login_background = PIXEL
        self.assertIn('/sl_web_login/background', self.env['res.company']._sl_login_css())

    def test_blur_uses_a_backdrop_layer(self):
        """Blurring the body would blur the login card with it."""
        self.company.write({'login_background': PIXEL, 'login_background_blur': 8})
        css = self.env['res.company']._sl_login_css()
        self.assertIn('body::before', css)
        self.assertIn('blur(8px)', css)

    def test_branding_dict_is_plain(self):
        branding = self.env['res.company']._sl_login_branding()
        self.assertEqual(
            set(branding), {'logo_url', 'hide_db_manager', 'hide_footer',
                            'footer_text', 'logo_height'})
        self.assertFalse(branding['logo_url'], "no custom logo uploaded yet")
        self.company.login_logo = PIXEL
        self.assertEqual(self.env['res.company']._sl_login_branding()['logo_url'],
                         '/sl_web_login/logo')

    def test_style_route_is_public(self):
        response = self.url_open('/sl_web_login/style.css')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/css', response.headers['Content-Type'])

    def test_image_routes_404_when_unset(self):
        self.company.write({'login_background': False, 'login_logo': False})
        self.env.cr.flush()
        for url in ('/sl_web_login/background', '/sl_web_login/logo'):
            self.assertEqual(self.url_open(url).status_code, 404, url)

    def test_login_page_still_renders(self):
        self.company.write({
            'login_background': PIXEL,
            'login_footer_text': 'Need help? support@example.com',
        })
        self.env.cr.flush()
        response = self.url_open('/web/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn('/sl_web_login/style.css', response.text)
        self.assertIn('Need help? support@example.com', response.text)

    def test_hide_footer_removes_powered_by(self):
        self.company.login_hide_powered_by = True
        self.env.cr.flush()
        self.assertNotIn('Powered by', self.url_open('/web/login').text)
