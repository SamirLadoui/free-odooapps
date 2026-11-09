# Employee Shifts

> Including The Ones That Run Past Midnight

Define your shifts once, assign people to them over time, and see who is on which. Built around the case most shift modules get wrong: the night shift.

## Features

- **Overnight Shifts Are Eight Hours, Not Minus Sixteen** - A shift ending earlier than it starts runs past midnight, and the paid hours reflect that. Getting this wrong is how a night shift quietly ends up unpaid.
- **Breaks Come Off The Total** - An unpaid break is deducted from the paid hours, on overnight shifts as well as ordinary ones, so what you see is what you pay.
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

## Optional historical attendance and work entries (Odoo 15)

The base catalogue depends only on `hr` and `mail`: displayed paid shift hours do
not by themselves change imported attendance, approve overtime or calculate salary.
Historical assignments additionally store schedule timezone, shift-start weekdays
and an explicitly confirmed unpaid-break window. The current-shift display remains
for today only.

Install `sl_employee_shift_attendance` separately for opt-in historical net hours,
one logical presence anchor and audited overtime approval. It defaults off; native
behavior remains unchanged without an eligible opted-in assignment. Install
`sl_employee_shift_work_entry` separately for provider-neutral explicit manual
export of regular and **approved** overtime into native Odoo 15 start/stop contract
work entries. Both the assignment and the effective contract source must be selected
explicitly. Read each companion's README before enabling historical corrections.

The fixture 18:00–03:00 with one confirmed unpaid hour yields eight regular hours,
zero overtime and one logical shift presence; 18:00–05:00 yields eight regular and
two raw overtime hours, not eleven overtime hours. These are configured-policy
examples, not statutory UAE salary rules. No production repair, licensed payroll
provider or real client payslip is certified by this catalogue.

## Supported Versions

`14.0` `15.0` `16.0` `17.0` `18.0` `19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
