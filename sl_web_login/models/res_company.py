# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Accepts #rgb, #rrggbb and #rrggbbaa. Anything else is rejected rather than
# injected into a stylesheet.
HEX_COLOR = re.compile(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$')

DEFAULTS = {
    'login_background_color': '#f1f3f5',
    'login_card_width': 300,
    'login_logo_height': 120,
    'login_button_color': '#714B67',
}


class ResCompany(models.Model):
    _inherit = 'res.company'

    login_background = fields.Image(
        string='Login Background',
        help="Shown full-bleed behind the login card. Leave empty for a plain colour.")
    login_background_color = fields.Char(
        string='Login Background Colour', default=DEFAULTS['login_background_color'],
        help="Used on its own, or behind the background image while it loads.")
    login_background_blur = fields.Integer(
        string='Background Blur (px)', default=0,
        help="Blurs the background image so the login card stays readable. 0 disables it.")
    login_logo = fields.Image(
        string='Login Logo', max_width=1024, max_height=1024,
        help="Replaces the company logo on the login screen only. "
             "Leave empty to keep using the company logo.")
    login_logo_height = fields.Integer(
        string='Logo Height (px)', default=DEFAULTS['login_logo_height'])
    login_card_width = fields.Integer(
        string='Card Width (px)', default=DEFAULTS['login_card_width'])
    login_button_color = fields.Char(
        string='Button Colour', default=DEFAULTS['login_button_color'])
    login_hide_db_manager = fields.Boolean(
        string='Hide "Manage Databases"',
        help="Removes the database manager link from the login footer. "
             "This hides the link, it does not block the route.")
    login_hide_powered_by = fields.Boolean(string='Hide the Whole Footer')
    login_footer_text = fields.Char(
        string='Footer Text',
        help="Shown under the login form, e.g. a support phone number.")

    @api.constrains('login_background_color', 'login_button_color')
    def _check_login_colors(self):
        for company in self:
            for value in (company.login_background_color, company.login_button_color):
                if value and not HEX_COLOR.match(value.strip()):
                    raise ValidationError(_(
                        "'%s' is not a valid hex colour. Use #rgb, #rrggbb or #rrggbbaa.")
                        % value)

    @api.constrains('login_card_width', 'login_logo_height', 'login_background_blur')
    def _check_login_sizes(self):
        for company in self:
            if not 200 <= company.login_card_width <= 900:
                raise ValidationError(_("Card width must be between 200 and 900 pixels."))
            if not 20 <= company.login_logo_height <= 400:
                raise ValidationError(_("Logo height must be between 20 and 400 pixels."))
            if not 0 <= company.login_background_blur <= 40:
                raise ValidationError(_("Background blur must be between 0 and 40 pixels."))

    # -- rendering ---------------------------------------------------------

    @api.model
    def _sl_login_company(self):
        """The company the login screen is branded with.

        The login page is reached before authentication, so there is no active
        company yet: fall back to the oldest one, which is the main company on
        every single-company database and the sensible default otherwise.
        """
        return self.sudo().search([], order='id', limit=1)

    @api.model
    def _sl_login_branding(self):
        """Plain dict for the login template - no recordset leaks into QWeb."""
        company = self._sl_login_company()
        if not company:
            return {'logo_url': False, 'hide_db_manager': False,
                    'hide_footer': False, 'footer_text': False}
        return {
            'logo_url': '/sl_web_login/logo' if company.login_logo else False,
            'hide_db_manager': company.login_hide_db_manager,
            'hide_footer': company.login_hide_powered_by,
            'footer_text': company.login_footer_text,
            'logo_height': company.login_logo_height or DEFAULTS['login_logo_height'],
        }

    @api.model
    def _sl_login_css(self):
        """The login stylesheet, served by the public /sl_web_login/style.css route."""
        company = self._sl_login_company()
        if not company:
            return ''

        def color(value, fallback):
            value = (value or '').strip()
            return value if HEX_COLOR.match(value) else fallback

        bg = color(company.login_background_color, DEFAULTS['login_background_color'])
        button = color(company.login_button_color, DEFAULTS['login_button_color'])
        width = company.login_card_width or DEFAULTS['login_card_width']
        logo_height = company.login_logo_height or DEFAULTS['login_logo_height']

        rules = [
            'body { background-color: %s; }' % bg,
        ]
        if company.login_background:
            rules.append(
                'body { background-image: url("/sl_web_login/background");'
                ' background-size: cover; background-position: center;'
                ' background-repeat: no-repeat; background-attachment: fixed; }')
            if company.login_background_blur:
                # Blurring the body would blur the card too, so blur a fixed
                # pseudo-element sitting behind everything instead.
                rules.append(
                    'body { background-image: none; }\n'
                    'body::before { content: ""; position: fixed; inset: -%(pad)dpx;'
                    ' z-index: -1; background-image: url("/sl_web_login/background");'
                    ' background-size: cover; background-position: center;'
                    ' filter: blur(%(blur)dpx); }'
                    % {'blur': company.login_background_blur,
                       'pad': company.login_background_blur * 2})
        rules += [
            '.o_database_list { max-width: %dpx !important; }' % width,
            '.o_database_list img[alt="Logo"] { max-height: %dpx; }' % logo_height,
            '.oe_login_buttons .btn-primary { background-color: %(c)s;'
            ' border-color: %(c)s; }' % {'c': button},
        ]
        return '\n'.join(rules) + '\n'
