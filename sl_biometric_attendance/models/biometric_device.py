# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

try:
    from zk import ZK
except ImportError:  # optional: only needed to reach a real device
    ZK = None

ZK_MISSING = _(
    "Talking to a device needs the 'pyzk' Python package on the Odoo server. "
    "Install it with: pip install pyzk")

# Two punches closer together than this are the same person pressing twice.
DEFAULT_DEBOUNCE_SECONDS = 60


class BiometricDevice(models.Model):
    _name = 'sl.biometric.device'
    _description = 'Biometric Attendance Device'
    _order = 'name'

    name = fields.Char(required=True)
    address = fields.Char(string='IP Address', required=True)
    port = fields.Integer(default=4370, required=True)
    password = fields.Char(string='Device Password', default='0')
    timeout = fields.Integer(string='Timeout (seconds)', default=30)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)

    debounce_seconds = fields.Integer(
        string='Ignore Repeats Within (seconds)', default=DEFAULT_DEBOUNCE_SECONDS,
        help="Two punches this close together are treated as one. People press "
             "twice when the beep is not obvious.")

    last_download = fields.Datetime(readonly=True)
    last_state = fields.Selection(
        [('ok', 'Success'), ('fail', 'Failed')], readonly=True)
    last_message = fields.Text(readonly=True)

    @api.constrains('port')
    def _check_port(self):
        for device in self:
            if not 1 <= device.port <= 65535:
                raise ValidationError(_("A port must be between 1 and 65535."))

    @api.constrains('debounce_seconds')
    def _check_debounce(self):
        for device in self:
            if device.debounce_seconds < 0:
                raise ValidationError(_("The repeat window cannot be negative."))

    # -- talking to the device ---------------------------------------------

    def _connect(self):
        self.ensure_one()
        if ZK is None:
            raise UserError(ZK_MISSING)
        try:
            connection = ZK(
                self.address, port=self.port, timeout=self.timeout,
                password=self.password or 0, force_udp=False, ommit_ping=True)
            return connection.connect()
        except Exception as err:
            raise UserError(_("Cannot reach %(name)s at %(address)s: %(err)s")
                            % {'name': self.name, 'address': self.address, 'err': err})

    def action_test_connection(self):
        self.ensure_one()
        connection = self._connect()
        try:
            count = len(connection.get_users() or [])
        finally:
            connection.disconnect()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Connected"),
                'message': _("%(count)s user(s) enrolled on %(name)s.")
                           % {'count': count, 'name': self.name},
                'type': 'success', 'sticky': False,
            },
        }

    def action_download(self):
        for device in self:
            connection = device._connect()
            try:
                punches = [
                    {'device_user_id': str(record.user_id),
                     'timestamp': record.timestamp}
                    for record in (connection.get_attendance() or [])
                ]
            finally:
                connection.disconnect()
            device._process_punches(punches)
        return True

    # -- turning punches into attendance -----------------------------------

    @api.model
    def _clean_punches(self, punches, debounce_seconds):
        """Sort, and drop repeats inside the debounce window.

        People press twice when the beep is not obvious, and a raw device dump
        is not in any guaranteed order.
        """
        cleaned = []
        by_user = {}
        for punch in sorted(punches, key=lambda p: (p['device_user_id'], p['timestamp'])):
            user = punch['device_user_id']
            previous = by_user.get(user)
            if previous is not None:
                gap = (punch['timestamp'] - previous).total_seconds()
                if gap < debounce_seconds:
                    continue
            by_user[user] = punch['timestamp']
            cleaned.append(punch)
        return cleaned

    @api.model
    def _pair_punches(self, punches):
        """Alternate punches into (check_in, check_out) pairs per user.

        A trailing odd punch is returned with no check-out: somebody is still
        inside, and inventing a check-out would be a lie.
        """
        pairs = []
        by_user = {}
        for punch in punches:
            by_user.setdefault(punch['device_user_id'], []).append(punch['timestamp'])
        for user, stamps in by_user.items():
            stamps.sort()
            for index in range(0, len(stamps), 2):
                check_in = stamps[index]
                check_out = stamps[index + 1] if index + 1 < len(stamps) else False
                pairs.append({
                    'device_user_id': user,
                    'check_in': check_in,
                    'check_out': check_out,
                })
        return pairs

    def _process_punches(self, punches):
        """Store the punches as hr.attendance, skipping what is already there."""
        self.ensure_one()
        Attendance = self.env['hr.attendance']
        Employee = self.env['hr.employee']

        cleaned = self._clean_punches(punches, self.debounce_seconds)
        created, unknown = 0, set()

        for pair in self._pair_punches(cleaned):
            employee = Employee.search([
                ('sl_device_user_id', '=', pair['device_user_id']),
            ], limit=1)
            if not employee:
                unknown.add(pair['device_user_id'])
                continue
            existing = Attendance.search([
                ('employee_id', '=', employee.id),
                ('check_in', '=', pair['check_in']),
            ], limit=1)
            if existing:
                continue
            values = {'employee_id': employee.id, 'check_in': pair['check_in']}
            if pair['check_out']:
                values['check_out'] = pair['check_out']
            Attendance.create(values)
            created += 1

        message = _("%s attendance record(s) created.") % created
        if unknown:
            message += '\n' + _(
                "No employee is mapped to these device users: %s") % ', '.join(
                    sorted(unknown))
        self.sudo().write({
            'last_download': fields.Datetime.now(),
            'last_state': 'ok',
            'last_message': message,
        })
        return created

    @api.model
    def _cron_download(self):
        """One unreachable device must not stop the others."""
        failures = []
        for device in self.search([]):
            try:
                with self.env.cr.savepoint():
                    device.action_download()
            except Exception as err:
                device.sudo().write({
                    'last_download': fields.Datetime.now(),
                    'last_state': 'fail',
                    'last_message': str(err),
                })
                failures.append('%s: %s' % (device.name, err))
        if failures:
            _logger.warning("Biometric downloads failed:\n%s", '\n'.join(failures))
        return True
