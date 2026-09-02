# -*- coding: utf-8 -*-
"""Every time somebody logged in as somebody else.

The feature is useful and it is also the most abusable thing an administrator
can do, so it is only worth having with a record attached. What is kept is who
did it, whose account they used, when, and why - and none of it can be edited
or deleted afterwards, including by the person who did it.

A log that the administrator can tidy up is not a log.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class LoginAsLog(models.Model):
    _name = 'sl.login.as.log'
    _description = 'Logged In As'
    _order = 'create_date desc, id desc'
    _rec_name = 'target_user_id'

    actor_user_id = fields.Many2one(
        'res.users', string='Who Did It', required=True, readonly=True,
        ondelete='restrict')
    target_user_id = fields.Many2one(
        'res.users', string='Whose Account', required=True, readonly=True,
        ondelete='restrict')
    reason = fields.Char(readonly=True)
    happened_on = fields.Datetime(
        readonly=True, default=lambda self: fields.Datetime.now())

    def write(self, vals):
        """A log that can be edited afterwards records nothing."""
        raise UserError(_(
            'These entries cannot be changed. That is what makes them worth '
            'keeping.'))

    def unlink(self):
        raise UserError(_(
            'These entries cannot be deleted, including by whoever created '
            'them. A log an administrator can tidy up is not a log.'))
