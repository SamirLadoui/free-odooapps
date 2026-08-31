# -*- coding: utf-8 -*-
import logging
import os
import re
import tempfile
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.service import db as db_service
from odoo.tools import config

_logger = logging.getLogger(__name__)

try:
    import paramiko
except ImportError:  # optional: only needed for the SFTP destination
    paramiko = None

# <db>_<YYYY-MM-DD_HH-MM-SS>.<ext> -- also the pattern autoremove matches on.
FILENAME_RE = re.compile(r'^(?P<db>.+)_(?P<stamp>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.(zip|dump)$')


class DbBackup(models.Model):
    _name = 'db.backup'
    _description = 'Scheduled Database Backup'
    _inherit = ['mail.thread']
    _order = 'db_name, id'

    def _default_folder(self):
        return os.path.join(config.get('data_dir', tempfile.gettempdir()), 'backups')

    name = fields.Char(compute='_compute_name', store=True)
    active = fields.Boolean(default=True)
    db_name = fields.Char(
        string='Database', required=True,
        default=lambda self: self.env.cr.dbname,
        help="Name of the database to dump.")
    folder = fields.Char(
        string='Backup Directory', required=True, default=_default_folder,
        help="Local directory the dump is written to. Created if missing.")
    backup_format = fields.Selection(
        [('zip', 'zip (database + filestore)'),
         ('dump', 'pg_dump (database only)')],
        default='zip', required=True)
    method = fields.Selection(
        [('local', 'Local disk'), ('sftp', 'Remote SFTP server')],
        string='Destination', default='local', required=True)

    sftp_host = fields.Char(string='SFTP Host')
    sftp_port = fields.Integer(string='SFTP Port', default=22)
    sftp_user = fields.Char(string='SFTP Username')
    sftp_password = fields.Char(string='SFTP Password')
    sftp_path = fields.Char(string='SFTP Path', help="Remote directory, e.g. /home/backups/odoo")

    autoremove = fields.Boolean(
        string='Delete Old Backups',
        help="Remove dumps of this database older than the retention window.")
    days_to_keep = fields.Integer(string='Keep For (days)', default=30)

    notify_email = fields.Char(
        string='Notify On Failure',
        help="Comma-separated addresses warned when a backup fails.")

    last_run = fields.Datetime(readonly=True)
    last_state = fields.Selection(
        [('ok', 'Success'), ('fail', 'Failed')], readonly=True)
    last_message = fields.Text(readonly=True)

    @api.depends('db_name', 'method', 'folder', 'sftp_host')
    def _compute_name(self):
        for rec in self:
            where = rec.folder if rec.method == 'local' else (rec.sftp_host or '')
            rec.name = '%s @ %s' % (rec.db_name or '', where or '')

    @api.constrains('days_to_keep', 'autoremove')
    def _check_days_to_keep(self):
        for rec in self:
            if rec.autoremove and rec.days_to_keep < 1:
                raise ValidationError(_("Keep For (days) must be at least 1 when deleting old backups."))

    @api.constrains('method', 'sftp_host', 'sftp_user', 'sftp_path')
    def _check_sftp(self):
        for rec in self:
            if rec.method != 'sftp':
                continue
            if paramiko is None:
                raise ValidationError(_(
                    "The SFTP destination needs the 'paramiko' Python package. "
                    "Install it with: pip install paramiko"))
            missing = [label for label, value in (
                (_("Host"), rec.sftp_host), (_("Username"), rec.sftp_user), (_("Path"), rec.sftp_path),
            ) if not value]
            if missing:
                raise ValidationError(_("SFTP destination needs: %s") % ', '.join(missing))

    @api.constrains('db_name')
    def _check_db_exists(self):
        available = db_service.list_dbs(force=True)
        for rec in self:
            if rec.db_name not in available:
                raise ValidationError(_("No database named '%s' on this server.") % rec.db_name)

    # -- naming ------------------------------------------------------------

    def _filename(self, when=None):
        self.ensure_one()
        when = when or fields.Datetime.now()
        ext = 'zip' if self.backup_format == 'zip' else 'dump'
        return '%s_%s.%s' % (self.db_name, when.strftime('%Y-%m-%d_%H-%M-%S'), ext)

    def _is_own_backup(self, filename):
        """True when `filename` is a dump this record produced, so autoremove
        never touches unrelated files sharing the directory."""
        self.ensure_one()
        match = FILENAME_RE.match(filename)
        return bool(match) and match.group('db') == self.db_name

    # -- running -----------------------------------------------------------

    def action_backup(self):
        """Run every selected backup now, reporting the first hard failure."""
        for rec in self:
            rec._run()
        return True

    def _run(self):
        self.ensure_one()
        try:
            self._dump()
            if self.autoremove:
                self._cleanup()
        except Exception as err:  # a failed backup must not abort the cron
            _logger.exception("Backup of %s failed", self.db_name)
            self.sudo().write({
                'last_run': fields.Datetime.now(),
                'last_state': 'fail',
                'last_message': str(err),
            })
            self._notify_failure(err)
            raise UserError(_("Backup of '%(db)s' failed: %(err)s") % {
                'db': self.db_name, 'err': err})
        self.sudo().write({
            'last_run': fields.Datetime.now(),
            'last_state': 'ok',
            'last_message': _("Wrote %s") % self._filename(),
        })
        return True

    def _dump(self):
        self.ensure_one()
        filename = self._filename()
        # Dump to a temp file first: a crash mid-dump must not leave a
        # truncated file that looks like a valid backup.
        handle, tmp_path = tempfile.mkstemp(prefix='odoo_backup_', suffix='.tmp')
        os.close(handle)
        try:
            with open(tmp_path, 'wb') as stream:
                db_service.dump_db(self.db_name, stream, backup_format=self.backup_format)
            if self.method == 'local':
                self._store_local(tmp_path, filename)
            else:
                self._store_sftp(tmp_path, filename)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _store_local(self, tmp_path, filename):
        self.ensure_one()
        os.makedirs(self.folder, exist_ok=True)
        os.replace(tmp_path, os.path.join(self.folder, filename))
        _logger.info("Backup written to %s", os.path.join(self.folder, filename))

    def _sftp_client(self):
        self.ensure_one()
        transport = paramiko.Transport((self.sftp_host, self.sftp_port or 22))
        transport.connect(username=self.sftp_user, password=self.sftp_password or None)
        return paramiko.SFTPClient.from_transport(transport), transport

    def _store_sftp(self, tmp_path, filename):
        self.ensure_one()
        sftp, transport = self._sftp_client()
        try:
            try:
                sftp.stat(self.sftp_path)
            except IOError:
                sftp.mkdir(self.sftp_path)
            sftp.put(tmp_path, '%s/%s' % (self.sftp_path.rstrip('/'), filename))
        finally:
            sftp.close()
            transport.close()

    def action_test_connection(self):
        self.ensure_one()
        if self.method == 'local':
            try:
                os.makedirs(self.folder, exist_ok=True)
                probe = os.path.join(self.folder, '.odoo_backup_write_test')
                with open(probe, 'w') as fh:
                    fh.write('ok')
                os.remove(probe)
            except OSError as err:
                raise UserError(_("Cannot write to %(folder)s: %(err)s") % {
                    'folder': self.folder, 'err': err})
            message = _("Directory %s is writable.") % self.folder
        else:
            sftp, transport = self._sftp_client()
            try:
                sftp.listdir(self.sftp_path)
            except Exception as err:
                raise UserError(_("SFTP connection failed: %s") % err)
            finally:
                sftp.close()
                transport.close()
            message = _("Connected to %s.") % self.sftp_host
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _("Connection successful"), 'message': message,
                       'type': 'success', 'sticky': False},
        }

    # -- retention ---------------------------------------------------------

    def _cleanup(self):
        self.ensure_one()
        cutoff = datetime.now() - timedelta(days=self.days_to_keep)
        if self.method == 'local':
            if not os.path.isdir(self.folder):
                return
            names, remove = os.listdir(self.folder), os.remove
            join = lambda n: os.path.join(self.folder, n)
        else:
            sftp, transport = self._sftp_client()
            try:
                names = sftp.listdir(self.sftp_path)
                base = self.sftp_path.rstrip('/')
                join = lambda n: '%s/%s' % (base, n)
                self._remove_expired(names, join, sftp.remove, cutoff)
            finally:
                sftp.close()
                transport.close()
            return
        self._remove_expired(names, join, remove, cutoff)

    def _remove_expired(self, names, join, remove, cutoff):
        self.ensure_one()
        for name in names:
            if not self._is_own_backup(name):
                continue
            stamp = datetime.strptime(FILENAME_RE.match(name).group('stamp'), '%Y-%m-%d_%H-%M-%S')
            if stamp >= cutoff:
                continue
            try:
                remove(join(name))
                _logger.info("Removed expired backup %s", name)
            except OSError as err:
                _logger.warning("Could not remove %s: %s", name, err)

    # -- notification ------------------------------------------------------

    def _notify_failure(self, err):
        self.ensure_one()
        if not self.notify_email:
            return
        self.env['mail.mail'].sudo().create({
            'subject': _("Odoo backup failed: %s") % self.db_name,
            'email_to': self.notify_email,
            'body_html': '<p>%s</p>' % _(
                "The scheduled backup of database %(db)s failed:<br/><pre>%(err)s</pre>"
            ) % {'db': self.db_name, 'err': err},
            'auto_delete': True,
        }).send()

    # -- cron --------------------------------------------------------------

    @api.model
    def _cron_backup(self):
        """One bad configuration must not stop the others from running."""
        failures = []
        for rec in self.search([]):
            try:
                rec._run()
                self.env.cr.commit()
            except Exception as err:
                self.env.cr.rollback()
                failures.append('%s: %s' % (rec.db_name, err))
        if failures:
            _logger.warning("Scheduled backups failed:\n%s", '\n'.join(failures))
        return True
