# -*- coding: utf-8 -*-
{
    'name': 'Biometric Device Attendance',
    'version': '17.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'summary': 'Download attendance from ZKTeco biometric devices into Odoo',
    'description': """
Biometric Device Attendance
===========================

Connect Odoo to your fingerprint or face-recognition terminals and turn their
punches into real attendance records.

Punches are not shifts
----------------------
A device gives you a flat list of times. Turning that into hours worked is where
this module does its work:

* **Repeats are dropped.** Two punches within a minute are one person pressing
  twice because the beep was not obvious. The window is configurable per device.
* **Punches are paired** into check-in and check-out, so four punches in a day
  become a morning and an afternoon, not four mysteries.
* **An odd punch stays open.** Somebody who has not checked out yet gets an
  attendance record with no check-out, because inventing one would be a lie.
* **Re-downloading is safe.** Punches already imported are skipped, so running
  the download twice does not double anyone's hours.

Mapping people
--------------
Each employee carries the **Biometric ID** they are enrolled under on the
device. Two employees cannot share one, because that would silently merge their
hours. Punches from an unmapped id are reported by name in the result rather
than guessed at or dropped in silence.

Automatic
---------
An hourly scheduled action downloads from every device, isolating each one so an
unplugged terminal cannot stop the rest. The result of the last download, good or
bad, is recorded on the device.

Requirements
------------
Needs the ``pyzk`` Python package on the Odoo server::

    pip install pyzk

Odoo connects to the device over your network, so the terminal must be reachable
from the Odoo server. Without pyzk the module installs and configures cleanly and
tells you what is missing the first time you connect.
""",
    'author': 'Samir Ladoui',
    'maintainer': 'Samir Ladoui',
    'website': 'https://www.linkedin.com/in/samir-ladoui',
    'license': 'LGPL-3',
    'depends': ['hr_attendance'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/biometric_device_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
