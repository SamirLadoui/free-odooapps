# -*- coding: utf-8 -*-
"""What a password has to look like, and how long it lasts.

Odoo ships a minimum length and nothing else. Every security questionnaire
asks for more than that, and the usual answer is a policy written in a
document that nothing enforces.

The rules hang off the hook Odoo already has: _check_password_policy is called
whenever a password is set, from the user form, the change-password wizard,
signup and the reset link alike, so there is one place to check rather than
four places to remember.
"""
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessDenied, UserError

PARAM = 'sl_password_policy.%s'
# A space is not a symbol for this purpose: a rule met by pressing
# the space bar is not a rule.
SPECIAL = re.compile(r'[^A-Za-z0-9\s]')


class ResUsers(models.Model):
    _inherit = 'res.users'

    sl_password_date = fields.Datetime(
        string='Password Set On', readonly=True, copy=False,
        help='When this password was last changed. Empty means it has not '
             'been changed since the policy was turned on, and it does not '
             'expire until it is.')

    # -- the rules ---------------------------------------------------------

    @api.model
    def _sl_policy(self):
        params = self.env['ir.config_parameter'].sudo()

        def flag(name):
            return params.get_param(PARAM % name) in ('True', 'true', '1')

        def number(name):
            try:
                return int(params.get_param(PARAM % name) or 0)
            except ValueError:
                return 0

        return {
            'uppercase': flag('uppercase'),
            'lowercase': flag('lowercase'),
            'digit': flag('digit'),
            'special': flag('special'),
            'history': number('history'),
            'expiry_days': number('expiry_days'),
        }

    def _check_password_policy(self, passwords):
        """Odoo's own hook, called wherever a password is set."""
        result = super()._check_password_policy(passwords)
        policy = self._sl_policy()
        failures = []
        for password in passwords:
            if not password:
                continue
            if policy['uppercase'] and not any(c.isupper() for c in password):
                failures.append(_('a capital letter'))
            if policy['lowercase'] and not any(c.islower() for c in password):
                failures.append(_('a small letter'))
            if policy['digit'] and not any(c.isdigit() for c in password):
                failures.append(_('a digit'))
            if policy['special'] and not SPECIAL.search(password):
                failures.append(_('a punctuation or symbol character'))
        if failures:
            raise UserError(_(
                'That password is missing %s.', ', '.join(failures)))
        return result

    # -- not one of the last few -------------------------------------------

    def _sl_used_before(self, password):
        """Whether this user has had this password recently."""
        self.ensure_one()
        keep = self._sl_policy()['history']
        if not keep:
            return False
        history = self.env['sl.password.history'].sudo().search(
            [('user_id', '=', self.id)], limit=keep)
        context = self._crypt_context()
        return any(context.verify(password, entry.password_hash)
                   for entry in history)

    def _set_password(self):
        policy = self._sl_policy()
        # Read before super(): setting the password replaces what the field
        # holds with the hash, and a hash of a hash remembers nothing.
        plaintext = {user.id: user.password for user in self}
        for user in self:
            password = plaintext.get(user.id)
            if password and user.id and user._sl_used_before(password):
                raise UserError(_(
                    'That is one of the last %d passwords on this account. '
                    'Choose one that has not been used.', policy['history']))
        result = super()._set_password()
        now = fields.Datetime.now()
        for user in self:
            password = plaintext.get(user.id)
            if not password:
                continue
            user.sudo().write({'sl_password_date': now})
            if policy['history']:
                self.env['sl.password.history'].sudo()._record(
                    user, password, policy['history'])
        return result

    # -- how long it lasts -------------------------------------------------

    def _sl_password_expired(self):
        """Whether this password is past the age the policy allows."""
        self.ensure_one()
        days = self._sl_policy()['expiry_days']
        if not days:
            return False
        if self.sudo().has_group('sl_password_policy.group_password_never_expires'):
            # The way back in when a policy locks everybody out.
            return False
        # No date means the policy arrived after this password did. Treating
        # that as expired would lock out every user the moment the setting is
        # saved, so it counts as fresh until the next change.
        if not self.sl_password_date:
            return False
        return fields.Datetime.now() - self.sl_password_date > timedelta(days=days)

    def _check_credentials(self, *args, **kwargs):
        # The signature changed in 18.0, so it is passed straight through.
        result = super()._check_credentials(*args, **kwargs)
        # Odoo checks the password of the user the environment belongs to, so
        # that is the one whose age is the question here.
        user = self.env['res.users'].sudo().browse(self.env.uid) or self.sudo()
        if user.exists() and user._sl_password_expired():
            raise AccessDenied(_(
                'This password has expired. Use "Reset password" on the login '
                'page to set a new one.'))
        return result
