# Employee Shift Attendance — Odoo 15

Optional companion to `sl_employee_shift`, depending on native `hr_attendance`
and `base_import`. Installing it does **not** enable existing assignments.
The base addon still depends only on `hr` and `mail`.

## Explicit configuration

An HR Administrator who is also an Attendance Administrator selects **Shift net
hours — custom authoritative overtime** on a dated assignment. Save the historical
IANA timezone and shift-start weekdays (`0` Monday through `6` Sunday). For a
nonzero unpaid break, confirm its explicit local start time. A break before the
shift-start clock time belongs to the next date. Ambiguous/nonexistent DST times
are rejected. Assignment end dates are inclusive. Archive hides a record in the
UI but does not erase its historical schedule.

This policy is **one custom authoritative engine**, not native overtime plus a
second payable engine. Odoo 15 has daily `hr.attendance.overtime` aggregates, no
per-attendance overtime approval state. Eligible employee/check-in days are
excluded from native aggregate regeneration. Native manual adjustments and
unrelated employee/days remain native. A day mixing managed and unmanaged punches
is refused rather than silently replacing a shared native aggregate. A native
aggregate whose duration differs from its raw amount blocks adoption until it is
reconciled through the native workflow while integration is off.

## Odoo 15 upgrade safety

Version `15.0.1.1.0` removes the old Shift Overtime Approver → native Attendance
Officer implication. Its post-migration hook finds users who still have both groups,
ignores Officer membership still implied by another native group, and removes only
ambiguous legacy Officer memberships through the native `res.users` ORM.

Before upgrading a database containing ambiguous legacy users, set the
module-owned `ir.config_parameter` key
`sl_employee_shift_attendance.legacy_attendance_officer_preserve` to JSON in the
form `{"preserve_user_ids": [12, 34]}`. Those explicit user IDs retain Officer;
all other ambiguous legacy memberships are revoked. A missing, malformed, or
unknown-ID decision fails the upgrade closed rather than guessing. With no
ambiguous legacy users the parameter is unnecessary. Re-running the migration is
safe and makes no further changes.

The policy is net hours in excess of the assigned shift budget. For a scheduled
18:00–03:00 shift with an explicit 22:00–23:00 unpaid break:

| Actual pair | Raw elapsed | Net regular | Raw overtime | Logical presence |
|---|---:|---:|---:|---:|
| 18:00–03:00 next day | 9 | 8 | 0 | 1 |
| 18:00–04:00 next day | 10 | 8 | 1 | 1 |
| 18:00–05:00 next day | 11 | 8 | 2 | 1 |

Check-in/check-out timestamps remain unchanged. `sl_elapsed_hours` exposes raw
elapsed time; native `worked_hours` is net for opted-in punches only. The
`sl.shift.day` summary retains evidence/digest, original punch links, regular,
raw/approved overtime and one presence anchor on the **local shift-start date**.
The explicit break intersection is deducted once; matching separate break punches
do not cause a second deduction. Other gaps are absence, not inferred lunch.
Any open punch makes the day incomplete: no payable summary/presence until closed.
A late after-midnight arrival resolves to the prior eligible shift start. Early
arrivals and punches crossing the next shift start need explicit roster/correction
handling, not an invented grace period.

The employee's current-shift display is not the historical calculation source.
Changing used shift times/breaks is refused: create a new shift and future dated
assignment. An assignment's employee identity remains frozen once evidence exists,
even after disabling integration. A correction/reassignment rebuilds old and new
anchors, revokes earlier approval and invalidates owned draft work entries.

## Native CSV/XLSX import and updates

Use the standard **Attendances → Import records** route, not an onchange or
custom file parser. Map **External ID**, **Employee / External ID** (or an exact
Employee / Database ID), **Check In**, **Check Out**. Use a stable unique attendance
external ID for each original pair. Export an employee external ID once; do not
use ambiguous duplicate names. Example column mapping for a UTC import:

```csv
id,employee_id/id,check_in,check_out
night_shift_20261102,employee_example,2026-11-02 18:00:00,2026-11-03 03:00:00
```

Replace the illustrative IDs with the actual employee/attendance external IDs and
set the importing user's timezone to the intended source timezone. For a later
checkout, keep the same attendance external ID and change only the relevant source
columns. The CSV/XLSX routes both support creation and repeated external-ID updates.
Reimport without a stable external ID is **not** an update guarantee; native overlap
validation may reject a new duplicate. No attendance ID or approval should be
supplied in calculated columns. A native dry run rolls the proposed changes back.

## Approval and safe correction

**Employees → Logical Shift Attendance** shows raw versus approved values. Grant
the dedicated **Shift Overtime Approver** role deliberately. **Approve / Refuse
Overtime** opens a restricted-user decision form; a reason is mandatory and partial
approval cannot exceed raw completed overtime. Pending/refused overtime is not
payable. Audit actor/time/reason are server-maintained and immutable. UI readonly
fields are also protected against ORM/RPC/default-context spoofing.

Administrator API for a selected bounded assignment (no automatic mass repair):

```python
preview = assignment.action_repair_attendance()  # read-only, also before opt-in
# Review original punches, proposed hours, approval/native-entry blockers first.
assignment.action_repair_attendance(False, 'Authorized historical correction')
```

Execution requires explicit opt-in and a reason. Repeated repair retains source
identities and totals; each authorized invocation may add a repair audit event.
Module-owned coordination rows serialize participating mutation/approval/generation
paths. This does not claim coordination with arbitrary SQL/native writers outside
the addon protocol. Company record rules and native attendance ACLs are preserved;
attendance mutations do not run as sudo.

## Limits

This is not a statutory, night/holiday-premium or UAE salary engine. No salary
rules, wage rates, paid payslips or production data are rewritten. The optional
`sl_employee_shift_work_entry` companion exports provider-neutral intervals and
adds finalized-period guards. Attendance alone does not certify a payroll provider.
The original client spreadsheet, exact payroll stack and UAE Monthly Pay salary
structure were unavailable. Synthetic ORM/import/Form regressions are not a real
client payslip, browser, device or legal-compliance certification.

LGPL-3; see `LICENSE`.
