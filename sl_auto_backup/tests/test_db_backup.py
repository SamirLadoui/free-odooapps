# -*- coding: utf-8 -*-
import os
import tempfile
from datetime import datetime, timedelta

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDbBackup(TransactionCase):

    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp(prefix='sl_auto_backup_test_')
        self.backup = self.env['db.backup'].create({
            'db_name': self.env.cr.dbname,
            'folder': self.folder,
            'backup_format': 'dump',
        })

    def _touch(self, name, age_days=0):
        path = os.path.join(self.folder, name)
        with open(path, 'w') as fh:
            fh.write('x')
        if age_days:
            old = (datetime.now() - timedelta(days=age_days)).timestamp()
            os.utime(path, (old, old))
        return path

    def test_filename_format(self):
        when = datetime(2026, 3, 4, 5, 6, 7)
        self.assertEqual(
            self.backup._filename(when),
            '%s_2026-03-04_05-06-07.dump' % self.env.cr.dbname)
        self.backup.backup_format = 'zip'
        self.assertTrue(self.backup._filename(when).endswith('.zip'))

    def test_own_backup_matching(self):
        """Autoremove must only ever consider this database's own dumps."""
        db = self.env.cr.dbname
        self.assertTrue(self.backup._is_own_backup('%s_2026-01-01_00-00-00.zip' % db))
        self.assertTrue(self.backup._is_own_backup('%s_2026-01-01_00-00-00.dump' % db))
        self.assertFalse(self.backup._is_own_backup('other_db_2026-01-01_00-00-00.zip'))
        self.assertFalse(self.backup._is_own_backup('%s.zip' % db))
        self.assertFalse(self.backup._is_own_backup('important_customer_data.zip'))
        self.assertFalse(self.backup._is_own_backup('%s_2026-01-01.zip' % db))

    def test_cleanup_respects_retention_and_strangers(self):
        db = self.env.cr.dbname
        old = (datetime.now() - timedelta(days=40)).strftime('%Y-%m-%d_%H-%M-%S')
        recent = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d_%H-%M-%S')
        expired = self._touch('%s_%s.dump' % (db, old))
        kept = self._touch('%s_%s.dump' % (db, recent))
        stranger = self._touch('notes.txt')
        other_db = self._touch('someone_elses_db_%s.dump' % old)

        self.backup.write({'autoremove': True, 'days_to_keep': 30})
        self.backup._cleanup()

        self.assertFalse(os.path.exists(expired), "expired dump should be deleted")
        self.assertTrue(os.path.exists(kept), "in-window dump must survive")
        self.assertTrue(os.path.exists(stranger), "unrelated files must never be touched")
        self.assertTrue(os.path.exists(other_db), "another database's dump must not be touched")

    def test_days_to_keep_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self.backup.write({'autoremove': True, 'days_to_keep': 0})

    def test_unknown_database_rejected(self):
        with self.assertRaises(ValidationError):
            self.env['db.backup'].create({
                'db_name': 'no_such_database_here',
                'folder': self.folder,
            })

    def test_sftp_requires_credentials(self):
        with self.assertRaises(ValidationError):
            self.backup.write({'method': 'sftp', 'sftp_host': False})

    def test_test_connection_local(self):
        self.backup.action_test_connection()
        self.assertFalse(
            os.path.exists(os.path.join(self.folder, '.odoo_backup_write_test')),
            "the write probe must clean up after itself")

    def test_backup_writes_a_real_dump(self):
        self.backup.action_backup()
        dumps = [n for n in os.listdir(self.folder) if self.backup._is_own_backup(n)]
        self.assertEqual(len(dumps), 1, "exactly one dump should have been written")
        self.assertGreater(
            os.path.getsize(os.path.join(self.folder, dumps[0])), 1024,
            "the dump should not be empty")
        self.assertEqual(self.backup.last_state, 'ok')
