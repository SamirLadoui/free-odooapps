# SPDX-License-Identifier: LGPL-3.0-or-later
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['res.groups']._sl_cleanup_legacy_attendance_officer_memberships()
    env.clear()
