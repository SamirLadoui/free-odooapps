# -*- coding: utf-8 -*-
"""The passwords an account has already had.

Hashes, never the passwords themselves: the point of the table is to say "you
have used this one before", and a hash answers that without the table becoming
worth stealing. It is written with the same hashing Odoo uses for the live
password, so it is no weaker than the account itself.
"""
from odoo import fields, models


class PasswordHistory(models.Model):
    _name = 'sl.password.history'
    _description = 'Previous Password'
    _order = 'create_date desc, id desc'
    _rec_name = 'user_id'

    user_id = fields.Many2one(
        'res.users', required=True, ondelete='cascade', index=True)
    password_hash = fields.Char(required=True)

    def _record(self, user, password, keep):
        """Remember this password, and forget the ones past the limit."""
        self.sudo().create({
            'user_id': user.id,
            'password_hash': user._crypt_context().hash(password),
        })
        stale = self.sudo().search(
            [('user_id', '=', user.id)], offset=keep)
        stale.unlink()
        return True
