# Database Auto-Backup

> Scheduled Database Dumps to Local Disk or a Remote SFTP Server

Set up unattended backups of any database on your Odoo server, keep the backup directory from filling up, and get an email the moment a scheduled run fails. No shell access or cron editing required.

## Features

- **Any Database On The Server** - Back up the current database or any other one hosted on the same server. Create as many scheduled backups as you need, each with its own destination and retention.
- **Two Formats** - Choose a zip archive containing the database and its filestore, or a plain pg_dump when you only need the SQL and want the smaller file.
- **Local Or Remote SFTP** - Write to a directory on the server, or push the dump straight to a remote SFTP host so your backups do not live on the same machine as the database.
- **Automatic Retention** - Delete dumps older than the number of days you choose. Retention only ever removes this database's own dumps, so unrelated files in the same folder are never touched.
- **Alerts On Failure** - Give each backup a notification address and Odoo emails you the error the moment a scheduled run fails, instead of finding out when you need the backup.
- **Test Before You Trust It** - A Test Connection button checks the directory is writable, or that the SFTP credentials work, so a misconfigured destination is caught before the first nightly run rather than after it.

## Getting Started

1. Install the module and open Settings > Backups > Scheduled Backups.
2. Create a record, pick the database, the format and the destination.
3. Press Test Connection, then Back Up Now, to confirm the setup works.
4. Enable the Automated Backup scheduled action under Settings > Technical > Scheduled Actions and set how often it should run. It ships disabled so nothing runs until you say so.

## Good To Know

- Backups are written to a temporary file first and moved into place only once complete, so an interrupted run never leaves a truncated file that looks like a valid backup.
- One misconfigured backup does not stop the others in the same scheduled run.
- The SFTP destination needs the paramiko Python package on the Odoo server: pip install paramiko
- Only users in the Settings group can see or edit backup configurations.

## Supported Versions

`14.0` `15.0` `16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
