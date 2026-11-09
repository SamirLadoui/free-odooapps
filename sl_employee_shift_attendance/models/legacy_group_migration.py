# SPDX-License-Identifier: LGPL-3.0-or-later
import json

from odoo import api, Command, models, _
from odoo.exceptions import UserError


class ShiftAttendanceGroupMigration(models.Model):
    _inherit = 'res.groups'

    _sl_legacy_officer_preserve_param = (
        'sl_employee_shift_attendance.legacy_attendance_officer_preserve'
    )

    @api.model
    def _sl_cleanup_legacy_attendance_officer_memberships(self):
        approver = self.env.ref('sl_employee_shift_attendance.group_shift_approver')
        officer = self.env.ref('hr_attendance.group_hr_attendance_user')
        if officer in approver.implied_ids:
            raise UserError(_(
                'The Shift Overtime Approver still implies the native Attendance '
                'Officer group; refusing legacy membership cleanup.'
            ))

        users = self.env['res.users'].sudo().search([
            ('groups_id', 'in', approver.id),
            ('groups_id', 'in', officer.id),
        ])
        if not users:
            return 0

        native_officer_users = users.filtered(
            lambda user: officer in (
                user.groups_id - approver - officer
            ).trans_implied_ids
        )
        ambiguous_users = users - native_officer_users
        preserve_ids = self._sl_legacy_preserved_officer_user_ids(
            ambiguous_users,
        )
        victims = ambiguous_users.filtered(lambda user: user.id not in preserve_ids)
        if victims:
            victims.write({'groups_id': [Command.unlink(officer.id)]})
        return len(victims)

    def _sl_legacy_preserved_officer_user_ids(self, ambiguous_users):
        raw = self.env['ir.config_parameter'].sudo().get_param(
            self._sl_legacy_officer_preserve_param,
        )
        if raw is None:
            if ambiguous_users:
                raise UserError(_(
                    'Legacy Shift Approver users have ambiguous native Attendance '
                    'Officer memberships. Set the module-owned parameter %s with '
                    'a JSON object such as {"preserve_user_ids": []} before '
                    'upgrading.'
                ) % self._sl_legacy_officer_preserve_param)
            return set()

        try:
            config = json.loads(raw)
        except (TypeError, ValueError):
            raise UserError(_(
                'The module-owned legacy Attendance Officer preservation '
                'parameter must be valid JSON.'
            ))
        if not isinstance(config, dict) or set(config) != {'preserve_user_ids'}:
            raise UserError(_(
                'The module-owned legacy Attendance Officer preservation '
                'parameter must contain only preserve_user_ids.'
            ))
        preserve_ids = config['preserve_user_ids']
        if (
            not isinstance(preserve_ids, list)
            or any(isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0
                   for user_id in preserve_ids)
        ):
            raise UserError(_(
                'preserve_user_ids must be a list of positive integer user IDs.'
            ))

        existing_ids = set(
            self.env['res.users'].sudo().browse(preserve_ids).exists().ids
        )
        missing_ids = sorted(set(preserve_ids) - existing_ids)
        if missing_ids:
            raise UserError(_(
                'The legacy Attendance Officer preservation lists unknown user IDs: %s.'
            ) % ', '.join(map(str, missing_ids)))
        return set(preserve_ids)
