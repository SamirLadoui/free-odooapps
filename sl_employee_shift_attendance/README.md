# Employee Shift Attendance — Odoo 17

Optional companion to `sl_employee_shift`; depends on native `hr_attendance` and
`base_import`. Existing assignments default to **Native (no shift integration)**.
Installation or upgrade does not opt employees into the custom engine.

## Explicit historical policy

On the selected assignment, an HR Administrator **and** Attendance Administrator
must deliberately select **Shift net hours — custom authoritative overtime**.
Set its timezone, shift-start weekdays and dated range first. A nonzero unpaid
break requires a confirmed local break window wholly inside the shift.

For an ordinary eligible 18:00–03:00 schedule, with an explicit 22:00–23:00 unpaid
break and no other punches:

| Actual local check-out | Raw elapsed | Net worked | Regular | Raw overtime | Logical presence |
|---|---:|---:|---:|---:|---:|
| Next day 03:00 | 9 h | 8 h | 8 h | 0 h | 1 |
| Next day 04:00 | 10 h | 9 h | 8 h | 1 h | 1 |
| Next day 05:00 | 11 h | 10 h | 8 h | 2 h | 1 |

Original `check_in`/`check_out` values are preserved. `sl_elapsed_hours` remains
raw clock time; native `worked_hours` is the managed net duration. Separate break
punches are not deducted twice: only recorded work intersecting the explicit
break is removed. Other gaps are absences, not guessed lunch. An open logical
shift has no payable summary/presence until every contributing punch is closed.

`sl.shift.day` has one unique anchor per employee/shift-start date, source digest,
source punches and immutable audit events. Presence means one closed nonempty
duty window, not a statutory paid-day entitlement or `hours / 8` conversion.
Actual-hour attribution and shift-start presence are separate policies.

## One engine, not duplicate native overtime

Odoo 17 has daily `hr.attendance.overtime` aggregates, but no native overtime
approval state. This companion explicitly supplies its **own** guarded approval
workflow. Eligible managed buckets are excluded from native daily regeneration;
ordinary/unassigned days retain native behavior. Existing independent native
`adjustment=True` rows are retained, not copied into the bridge's payable hours.
A mixed native civil-day bucket containing managed and unmanaged punches is
refused; its policy must be reconciled explicitly.

Existing non-adjustment native overtime has no auditable approval provenance in
this release. Adoption therefore fails closed instead of deleting such history.
Review/reconcile it through an authorized native workflow while integration is
off, with a reason and backup, before enabling the assignment.

## Approval and correction

Open Employees → Logical Shift Attendance. A **Shift Overtime Approver** can use
**Approve / Refuse Overtime**; a reason is mandatory and approved hours must be
finite, nonnegative and no more than raw overtime. Approval is not granted to an
Attendance Officer just because they can correct punches.

The guarded ORM actions are `day.action_approve(hours, reason)` and
`day.action_refuse(reason)`. Raw overtime is never automatically approved.
Corrections recompute old/new logical days, retain their identities/audit, revoke
outdated decisions and invalidate owned draft work entries if the bridge is
installed. Direct summary/audit changes, authoritative attendance values,
relational/context-default spoofing and forged boolean capabilities are refused.
Native attendance ACLs and designated-officer rules are retained; attendance CRUD
is not sudoed. Destination employee/company is checked before a managed reparent.

## Real CSV/XLSX imports

Use the standard Attendances Import action with full, timezone-correct datetimes,
including the next day's checkout date. Map Employee, Check In and Check Out.
For updates/reimports, also use a stable **External ID**: a repeated file without
that identity is not an update contract and can fail native overlap checks.
CSV/XLSX creation, checkout updates and repeat updates use the same ORM hooks as
manual creation. Native ordering/overlap constraints remain in force. The tests
exercise real `base_import.import.execute_import`, not a substitute parser.

## Historical repair, preview first

For an authorized administrator:

```python
preview = assignment.action_repair_attendance()  # default dry-run, also while off
# Review grouped net/regular/raw overtime, native history and source identities.
assignment.action_repair_attendance(False, 'Authorized correction reference')
```

Execution requires explicit opt-in and a nonempty reason. Preview does not modify
punches/decisions. Repeated repair retains source/summary identities and totals;
each authorized invocation can add a repair audit event. Enabling/changing an
assignment can recompute its existing eligible history, so preview before that
change. Source shift template times/break quantity are frozen after evidence;
assignment employee identity cannot be changed once it owns history. Guarded
policy changes before finalization require recomputation/reapproval. With the
bridge installed, finalized work-entry/payslip overlaps block corrections.

## Explicit limits

- Shift-start weekdays decide overnight carryover; rest-day arrivals without a
  matching eligible shift retain native behavior. Early check-in before the
  scheduled start is not assigned a guessed grace policy; correct/configure it
  explicitly. Punches crossing the next shift start are refused when managed.
- Ambiguous/nonexistent DST schedule times are refused, not rounded silently.
- This custom policy is net excess over the assignment's expected hours; it does
  not reuse native tolerance, statutory premium or automatic approval semantics.
- The mutation guard coordinates participating addon transactions; it is not a
  promise about arbitrary SQL writers. Browser/HttpCase, actual devices and the
  unavailable original client spreadsheet/payroll are not certified.
- No payslip, wage, fixed salary, tax, statutory UAE rule or production repair is
  supplied. Install the optional bridge only after agreeing its source/mappings.

LGPL-3; see `LICENSE`. Author: Samir Ladoui.
