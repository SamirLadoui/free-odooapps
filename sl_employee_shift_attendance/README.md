# Employee Shift Attendance — Odoo 19

Optional companion to `sl_employee_shift`. Requires `hr_attendance` and the
standard `base_import` module, not Payroll. It is disabled on every assignment
by default, including after upgrade.

## Configure an explicit historical schedule

1. As both an HR Administrator and Attendance Administrator, create a shift:
   18:00 to 03:00, unpaid break 60 minutes.
2. Create a dated employee assignment. Select the actual schedule timezone and
   shift-start weekdays (`0` Monday through `6` Sunday, comma-separated).
   UTC and Monday–Friday are defaults only. Confirm an exact unpaid-break window;
   for a synthetic example, 22:00–23:00. Do not infer lunch from arbitrary gaps.
3. Before changing historical behavior, run the assignment's bounded
   `action_repair_attendance(dry_run=True)` through an authorized ORM integration.
   It reports proposed net/regular/raw overtime, presence, and existing native
   decisions. This API is not an automatic production migration or a UI wizard.
4. Explicitly choose **Shift net hours — custom authoritative overtime**.
   This selects one custom engine for eligible assignment dates instead of native
   overtime for those punches; it is not an addition to native overtime. A decided
   or manually altered native overtime line blocks adoption until reconciled
   through the native authorized workflow. Pending lines are audited when replaced.
5. Import attendances normally. Open **Employees → Logical Shift Attendance**.
   Grant **Shift Overtime Approver** only to authorized approvers; the decision
   button requires a reason and permits partial approval or refusal. Raw overtime
   is never automatically approved. Corrections revoke stale approval.

## Supported import and update

Use the normal Attendances CSV/XLSX import. Map **External ID**, Employee,
Check In, and Check Out. Use an unambiguous employee external/database ID when
names repeat. Keep the attendance External ID stable for update/reimport; a blind
reimport without an ID is not an update. Datetimes are interpreted in the import
user's timezone: make it agree with the source file. Original UTC timestamps are
not shortened, moved, or split to manufacture net hours.

With the explicit 22:00–23:00 break in an ordinary UTC fixture:

- 18:00–03:00: 9 elapsed, 8 net/regular, 0 raw overtime, 1 logical presence.
- 18:00–04:00: 10 elapsed, 8 regular + 1 raw overtime, 1 presence.
- 18:00–05:00: 11 elapsed, 8 regular + 2 raw overtime, 1 presence.
- 18:00–22:00 and 23:00–03:00: 8 net, no second break deduction.

All punches of a logical shift share one employee/shift-start-date anchor.
Incomplete aggregates do not produce payable hours or presence. Presence is a
separate logical count, not native payroll day-equivalents. The configured
shift-start weekday controls overnight carryover; opted-out or unscheduled
records retain native behavior.

## Repair and audit

`assignment.action_repair_attendance(dry_run=False, reason='...')` requires the
configuration roles and explicit opt-in. It does not change source timestamps,
reuse invalid approvals, or touch unrelated employees. Repetition retains source
identities and quantities. Summaries and audit events cannot be forged through
ordinary create/write, context defaults, or a boolean context bypass. Archived
assignments still explain history; used shift definitions and assignment employee
identity are protected. Use future dated definitions for roster changes.

## Deliberate limits

The custom policy is net hours beyond the assigned shift, with explicit approval.
It does not implement statutory/night/holiday premiums or reuse a native
ruleset's tolerance/rate semantics; do not enable it when those native semantics
are required without a provider-specific adapter. Unmanaged employees are unchanged.
Ambiguous/nonexistent local DST clock times are rejected. Early arrivals before
the supported duty window or punches crossing the next shift start require explicit
roster/punch correction, not an assumed grace rule. No client spreadsheet,
proprietary UAE payroll, fixed-salary amount, browser, or biometric hardware
certification is supplied by the synthetic ORM/import tests.

See `sl_employee_shift_work_entry` for optional work-entry export. Installing this
attendance companion alone does not make an arbitrary payroll provider consume
its approved quantities or lock its proprietary paid periods.

License: LGPL-3.
