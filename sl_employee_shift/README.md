# Employee Shifts

> Including The Ones That Run Past Midnight

Define your shifts once, assign people to them over time, and see who is on which. Built around the case most shift modules get wrong: the night shift.

## Features

- **Overnight Shifts Are Eight Hours, Not Minus Sixteen** - A shift ending earlier than it starts runs past midnight, and the paid hours reflect that. Getting this wrong is how a night shift quietly ends up unpaid.
- **Breaks Come Off The Total** - An unpaid break is deducted from the scheduled net duration, on overnight shifts as well as ordinary ones. This is not a payslip calculation.
- **One Shift At A Time** - An employee cannot hold two overlapping assignments. Two at once means no report can say which shift they were actually on, so the second is refused and the first is named.
- **Permanent Or Temporary** - Leave the end date empty for a standing assignment, or set one for a temporary move. Consecutive assignments are fine; overlapping ones are not.
- **Current Shift On The Employee** - Each employee shows the shift they are on today, worked out from the assignment dates rather than maintained by hand.
- **Nonsense Refused At Entry** - A zero-length shift, a break as long as the shift itself, times outside the day, and a duplicate shift code are all caught when you save.

## Getting Started

1. Install the module and open Employees > Configuration > Shifts.
2. Define your shifts, using a start later than the end for anything overnight.
3. Go to Employees > Shift Assignments and assign people, with or without an end date.
4. Each employee's current shift appears on their own form.

## Good To Know

- Times are entered as hours of the day: 8.5 means 08:30.
- The paid hours shown are the shift length less the unpaid break.
- Shift codes are unique so two spellings of one shift cannot split your reporting.

## Attendance and payroll are optional

The base module depends only on `hr` and `mail`. Its **Paid Hours** column means
scheduled shift duration less the planned break; assigning a shift alone does
not change native attendance, work entries, or payslips.

For opt-in integration, install `sl_employee_shift_attendance` and, if needed,
`sl_employee_shift_work_entry`. Read each companion README before enabling an
existing assignment. New and upgraded assignments remain on native behavior
until explicitly enabled. Configure the historical timezone, shift-start
workdays, and exact break window: UTC and Monday–Friday are editable defaults,
not inferred employee settings.

An 18:00–03:00 shift with one unpaid hour has eight scheduled net hours. Under
the optional custom shift policy, a completed 18:00–05:00 attendance has eight
regular plus two **raw** overtime hours and one logical presence day. Overtime
is not exported as payable until an authorized approver decides it. The bridge
creates provider-neutral work entries, not salary rules or a second overtime
payment. A client's actual payslip/localization requires separate acceptance.

## Supported Versions

`14.0` `15.0` `16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
