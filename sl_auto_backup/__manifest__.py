# -*- coding: utf-8 -*-
{
    'name': 'Database Auto-Backup',
    'version': '17.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Scheduled database backups to a local directory or a remote SFTP server, with retention and failure alerts',
    'description': """
Database Auto-Backup
====================

Schedule unattended dumps of any database on this Odoo server and keep the
backup directory from filling up.

Features
--------
* Back up any database hosted on the server, not just the current one.
* Two formats: ``zip`` (database **and** filestore) or ``pg_dump`` (database only).
* Two destinations: a local directory, or a remote SFTP server.
* Retention: automatically delete dumps older than N days.
* Email alert when a scheduled backup fails.
* "Test Connection" button so a misconfigured destination is caught before the
  first nightly run, not after it.
* Last run, result, and message shown on every record.

Safety
------
* Dumps are written to a temporary file and moved into place only once complete,
  so an interrupted run never leaves a truncated file that looks like a valid
  backup.
* Retention only ever deletes files matching this database's own dump naming
  pattern. Unrelated files sharing the directory, and other databases' dumps,
  are never touched.
* One failing configuration does not stop the remaining scheduled backups.

Setup
-----
1. Go to **Settings > Backups > Scheduled Backups** and create a record.
2. Press **Test Connection**, then **Back Up Now** to verify.
3. Enable the **Automated Backup** scheduled action (it ships disabled) and set
   the frequency you want.

The SFTP destination requires the ``paramiko`` Python package on the server::

    pip install paramiko
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/db_backup_security.xml',
        'data/ir_cron_data.xml',
        'views/db_backup_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'external_dependencies': {},
    'installable': True,
    'application': False,
    'auto_install': False,
}
