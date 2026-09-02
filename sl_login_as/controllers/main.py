# -*- coding: utf-8 -*-
"""The one place the session actually changes hands.

Everything before this is a form and a record. This is where the session stops
being one person and starts being another, so it checks the same rule again -
a url is not a promise that the wizard was used - and it refuses unless an
entry was written for this pair moments ago, which is what stops the address
being a way round the reason.
"""
from datetime import timedelta

from odoo import fields, http
from odoo.http import request

# Long enough to survive a slow page, short enough that a stale entry is no use.
GRACE_SECONDS = 60


class LoginAsController(http.Controller):

    @http.route('/sl_login_as/<int:user_id>', type='http', auth='user',
                methods=['GET'], csrf=False)
    def sl_login_as(self, user_id, **kwargs):
        actor = request.env.user
        target = request.env['res.users'].sudo().browse(user_id).exists()
        if not target or not actor._sl_may_log_in_as(target):
            return request.redirect('/web')

        # The address on its own proves nothing; an entry written seconds ago
        # by this person for this account is what proves the reason was given.
        since = fields.Datetime.now() - timedelta(seconds=GRACE_SECONDS)
        vouched = request.env['sl.login.as.log'].sudo().search_count([
            ('actor_user_id', '=', actor.id),
            ('target_user_id', '=', target.id),
            ('happened_on', '>=', fields.Datetime.to_string(since)),
        ])
        if not vouched:
            return request.redirect('/web')

        request.session.uid = target.id
        # The token is tied to the user, so it has to be reissued or the very
        # next request throws the session away again.
        if hasattr(target, '_compute_session_token'):
            request.session.session_token = target.sudo()._compute_session_token(
                request.session.sid)
        if 'login' in request.session:
            request.session.login = target.sudo().login
        return request.redirect('/web')
