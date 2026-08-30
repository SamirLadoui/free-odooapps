# -*- coding: utf-8 -*-
import hashlib
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

KEY_BYTES = 32
PREFIX_LENGTH = 8


class ApiKey(models.Model):
    _name = 'sl.api.key'
    _description = 'REST API Key'
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True, help="What this key is for, in plain words.")
    user_id = fields.Many2one(
        'res.users', string='Acts As', required=True,
        default=lambda self: self.env.user,
        help="Requests with this key run as this user, with exactly their "
             "access rights. There is no way to exceed them.")
    key_prefix = fields.Char(readonly=True, copy=False, index=True)
    key_hash = fields.Char(readonly=True, copy=False)
    key_preview = fields.Char(
        string='Key', readonly=True, copy=False, store=False,
        help="Shown once, when the key is generated. It is stored hashed and "
             "cannot be shown again.")

    active = fields.Boolean(default=True)
    expires_on = fields.Date(
        help="Leave empty for a key that does not expire on its own.")
    last_used = fields.Datetime(readonly=True)
    use_count = fields.Integer(readonly=True, default=0)

    allowed_model_ids = fields.Many2many(
        'ir.model', string='Allowed Models',
        domain="[('transient', '=', False)]",
        help="Leave empty to allow every model this user can already reach. "
             "Naming models narrows the key further; it never widens it.")

    _sql_constraints = []

    @api.constrains('expires_on')
    def _check_expiry(self):
        for key in self.filtered('expires_on'):
            if key.expires_on < fields.Date.context_today(key):
                raise ValidationError(_("That expiry date is already in the past."))

    # -- generating and checking -------------------------------------------

    @api.model
    def _hash(self, raw_key):
        return hashlib.sha256(raw_key.encode()).hexdigest()

    def action_generate(self):
        """Mint a key, show it once, and store only its hash."""
        self.ensure_one()
        raw = secrets.token_urlsafe(KEY_BYTES)
        self.write({
            'key_prefix': raw[:PREFIX_LENGTH],
            'key_hash': self._hash(raw),
        })
        self.key_preview = raw
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Key generated"),
                'message': _("Copy it now: %s") % raw,
                'type': 'warning',
                'sticky': True,
            },
        }

    @api.model
    def _resolve(self, raw_key):
        """The key record for a presented secret, or an empty recordset.

        Looked up by prefix then verified by hash, so the stored secret is never
        compared in the clear and the search stays indexed.
        """
        if not raw_key or len(raw_key) < PREFIX_LENGTH:
            return self.browse()
        candidates = self.sudo().search([
            ('key_prefix', '=', raw_key[:PREFIX_LENGTH]),
            ('active', '=', True),
        ])
        digest = self._hash(raw_key)
        for candidate in candidates:
            if secrets.compare_digest(candidate.key_hash or '', digest):
                return candidate
        return self.browse()

    def _is_usable(self):
        self.ensure_one()
        if not self.active or not self.key_hash:
            return False
        if self.expires_on and self.expires_on < fields.Date.context_today(self):
            return False
        return bool(self.user_id and self.user_id.active)

    def _may_touch(self, model_name):
        """Whether this key is allowed to reach `model_name` at all.

        An empty list means "whatever the user can reach"; a populated one is a
        further restriction, never a widening of it.
        """
        self.ensure_one()
        if not self.allowed_model_ids:
            return True
        return model_name in self.allowed_model_ids.mapped('model')

    def _note_use(self):
        self.ensure_one()
        self.sudo().write({
            'last_used': fields.Datetime.now(),
            'use_count': self.use_count + 1,
        })

    def action_revoke(self):
        self.write({'active': False})
        return True
