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

## Supported Versions

`19.0`

## License

LGPL-3. See the `LICENSE` file.

## Support

- LinkedIn: <https://www.linkedin.com/in/samir-ladoui>
- WhatsApp: +213658127254
- Email: samir.odoo.apps2325@gmail.com
