# -*- coding: utf-8 -*-
"""Asking why, before anything happens.

The reason is not paperwork. It is the only part of the record that says what
the session was for, and it has to be given before the session starts rather
than remembered afterwards.
"""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class LoginAsWizard(models.TransientModel):
    _name = 'sl.login.as.wizard'
    _description = 'Log In As'

    target_user_id = fields.Many2one(
        'res.users', string='Whose Account', required=True)
    reason = fields.Char(
        required=True,
        help='What this session is for. It is kept with the entry.')
    may_do_it = fields.Boolean(compute='_compute_may_do_it')
    refusal = fields.Char(compute='_compute_may_do_it')

    @api.depends('target_user_id')
    def _compute_may_do_it(self):
        for wizard in self:
            target = wizard.target_user_id
            allowed = bool(target) and self.env.user._sl_may_log_in_as(target)
            wizard.may_do_it = allowed
            wizard.refusal = '' if allowed or not target else _(
                '%s has rights yours does not, so taking that account would be '
                'granting them to yourself.', target.display_name)

    def action_go(self):
        self.ensure_one()
        if not self.env.user._sl_may_log_in_as(self.target_user_id):
            raise AccessError(self.refusal or _('That account cannot be used.'))
        if not (self.reason or '').strip():
            raise UserError(_('Say why first.'))
        self.target_user_id.sl_login_as(self.reason)
        return {
            'type': 'ir.actions.act_url',
            'url': '/sl_login_as/%d' % self.target_user_id.id,
            'target': 'self',
        }
