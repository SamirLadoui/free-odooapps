# -*- coding: utf-8 -*-
"""Who is read-only.

Asked of the group rather than of a field on the user, so it is granted and
taken away like every other permission in Odoo, and shows up in the same place
an administrator already looks.
"""
from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _sl_is_read_only(self):
        self.ensure_one()
        # sudo: the question is asked while an operation is being checked, and
        # reading the group must not itself need permission.
        return self.sudo().has_group('sl_readonly_user.group_read_only')
