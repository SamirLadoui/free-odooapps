# Biometric Device Attendance

> Turn Fingerprint Punches Into Hours Worked

Connect Odoo to your ZKTeco fingerprint or face terminals and download their punches as real attendance records. A device gives you a flat list of times; turning that into hours worked is where this module does its work.

## Features

- **Double Presses Dropped** - Two punches within a minute are one person pressing twice because the beep was not obvious. The window is configurable per device, and the debounce is per person so two people arriving together are both recorded.
- **Punches Paired Into Shifts** - Four punches in a day become a morning and an afternoon, not four mysteries. Each person's punches are paired independently.
- **An Open Shift Stays Open** - Somebody who has not checked out yet gets a record with no check-out. Inventing an end time would be a lie, and payroll would believe it.
- **Safe To Download Twice** - Punches already imported are skipped, so running the download again, or letting the cron overlap a manual pull, never doubles anyone's hours.
- **Unmapped Ids Are Reported** - A punch from a device id with no employee behind it is named in the result rather than silently dropped or guessed at, so you can see exactly who needs mapping.
- **One Dead Terminal Does Not Stop The Rest** - The hourly download isolates each device, and records the outcome of the last attempt on the device itself, good or bad.

## Getting Started

1. Install pyzk on the Odoo server: pip install pyzk
2. Install the module and open Employees > Configuration > Biometric Devices.
3. Add your device, press Test Connection, then Download Attendance.
4. Give each employee the Biometric ID they are enrolled under on the device.
5. Enable the Biometric Devices: Download Attendance scheduled action. It ships disabled.

## Good To Know

- Odoo connects over your network, so the terminal must be reachable from the Odoo server itself.
- Two employees cannot share a Biometric ID, because that would silently merge their hours.
- Without pyzk the module installs and configures cleanly and tells you what is missing the first time you connect.

## Supported Versions

`18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
