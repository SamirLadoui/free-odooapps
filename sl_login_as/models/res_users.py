# -*- coding: utf-8 -*-
"""Opening a session as another user, deliberately and on the record.

Support work needs it constantly: a person reports that a button is missing
and the only way to see what they see is to be them. Doing it by resetting
their password locks them out and tells you nothing afterwards.

What is refused matters as much as what is allowed. Somebody cannot use an
account with more power than their own - otherwise this is not a support tool,
it is a way around the access rights the database already has.
"""
from odoo import _, api, models
from odoo.exceptions import AccessError, UserError


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _sl_may_log_in_as(self, target):
        """Whether this user may open a session as that one.

        The rule is not seniority, it is containment: every right the target
        has, the actor must already have. A support person who could become
        somebody more powerful has effectively granted themselves that power.
        """
        self.ensure_one()
        if not self.has_group('base.group_erp_manager'):
            return False
        if target == self:
            return False
        if target._is_system() and not self._is_system():
            return False
        field = 'group_ids' if 'group_ids' in self._fields else 'groups_id'
        return not (target[field] - self[field])

    def sl_login_as(self, reason=None):
        """Open a session as this user, and write down that it happened."""
        self.ensure_one()
        actor = self.env.user
        if not actor._sl_may_log_in_as(self):
            raise AccessError(_(
                'You cannot use %s: that account has rights yours does not, '
                'and taking it would be granting them to yourself.',
                self.display_name))
        if not (reason or '').strip():
            raise UserError(_(
                'Say why. An entry with no reason is the one that cannot be '
                'explained afterwards.'))
        self.env['sl.login.as.log'].sudo().create({
            'actor_user_id': actor.id,
            'target_user_id': self.id,
            'reason': reason.strip(),
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web',
            'target': 'self',
        }

    def action_sl_login_as(self):
        """From the user form: ask for the reason, then go."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sl.login.as.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_target_user_id': self.id},
        }
