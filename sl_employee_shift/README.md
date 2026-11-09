# Employee Shifts

> Historical schedules for Odoo 17, including overnight shifts

Define your shifts once, assign people to them over time, and see who is on which. Built around the case most shift modules get wrong: the night shift.

## Features

- **Overnight Shifts Are Eight Hours, Not Minus Sixteen** - A shift ending earlier than it starts runs past midnight, and the paid hours reflect that. Getting this wrong is how a night shift quietly ends up unpaid.
- **Scheduled Net Hours** - A 18:00–03:00 shift has nine elapsed hours; a 60-minute unpaid break leaves eight scheduled net hours. This base addon does not itself calculate payroll.
- **One Shift At A Time** - An employee cannot hold two overlapping assignments. Two at once means no report can say which shift they were actually on, so the second is refused and the first is named.
- **Permanent Or Temporary** - Leave the end date empty for a standing assignment, or set one for a temporary move. Consecutive assignments are fine; overlapping ones are not.
- **Current Shift On The Employee** - Each employee shows the shift they are on today, worked out from the assignment dates rather than maintained by hand.
- **Nonsense Refused At Entry** - A zero-length shift, a break as long as the shift itself, times outside the day, and a duplicate shift code are all caught when you save.

## Getting Started

1. Install the module and open Employees > Configuration > Shifts.
2. Define your shifts, using a start later than the end for anything overnight.
3. Go to Employees > Shift Assignments and assign people, with or without an end date.
4. Each employee's current shift appears on their own form.

## Historical schedule and optional integrations

The base remains dependent on `hr` and `mail` only. Installing it alone does not
change native attendance/overtime, work entries, wages, salary rules or payslips.

Assignments have an explicit historical timezone, shift-start weekdays (`0`
Monday to `6` Sunday), and a confirmed local break window. The current-shift
employee display is for today only; the optional integrations resolve historical
assignment dates instead. Archived assignments still describe history.
Ambiguous/nonexistent DST clock times are rejected rather than guessed.
Assignment company is derived from the employee and isolated by record rules.

- `sl_employee_shift_attendance`: optional, default-off custom net-hours and
  overtime approval engine, with one logical shift-start presence anchor.
- `sl_employee_shift_work_entry`: separately default-off provider-neutral native
  interval bridge; requires explicit type mappings and a historical manual-source
  contract. It does not depend on licensed payroll.

Read the companions' READMEs before opting in. A nonzero unpaid break needs its
actual local window, not just its quantity. Source template times/break quantity
become frozen once used by attendance evidence; use a new shift and future-dated
assignment for a new template. Upgrade never silently enables an assignment.

## Good To Know

- Times are entered as hours of the day: 8.5 means 08:30.
- The paid hours shown are the shift length less the unpaid break.
- Shift codes are unique so two spellings of one shift cannot split your reporting.

## Supported Versions

This source targets **17.0**. Sibling releases require independent native ports
and receipts; this README does not certify those releases.

## Limits

Scheduled net hours and logical presence are not salary calculations. No UAE
statutory rates, leave/night premiums, salary rules or production repair are
supplied. The original client spreadsheet and licensed payroll implementation
are unavailable; no actual client payslip or fixed-salary proof is claimed.

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
