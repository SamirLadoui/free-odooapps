# Employee Shift Attendance — Odoo 18

Optional integration for `sl_employee_shift`, native `hr_attendance` and the real
`base_import` CSV/XLSX importer. It is **off by default**. Installing or upgrading
this addon does not opt in assignments or rewrite existing punches.

## Explicit policy, not an extra overtime payment engine

On an eligible assignment select **Shift net hours — custom authoritative
overtime**. This explicitly replaces native daily overtime for those historical
employee/date buckets; it does not add another payable overtime calculation.
Unassigned, opted-out and unscheduled control records retain native behavior.
Native manual adjustment rows are preserved. A civil-day bucket containing both
managed and unmanaged punches is refused rather than assigned two owners.
Odoo 18 flexible weekly native overtime mixed with this policy also fails closed.

The base addon still depends only on `hr` and `mail`; no payroll dependency is
added to it. This attendance addon does not create work entries or payslips.

## Configuration

1. Define a shift, for example 18:00–03:00 with 60 unpaid break minutes.
2. Assign an employee with inclusive historical start/end dates. Set the actual
   schedule timezone and shift-start weekdays (`0` = Monday, `6` = Sunday).
   UTC and Monday–Friday are defaults, **not inferred client settings**.
3. For a nonzero break, confirm its explicit local clock window. For example,
   break start `22` means 22:00–23:00. The break must fit wholly within the shift;
   before-start clock hours refer to the next day. Ambiguous/nonexistent DST
   times are rejected, not guessed.
4. Review existing data before opting in. Enabling/changing managed schedule
   policy and executing repair require both **HR Administrator** and native
   **Attendances Administrator**. Odoo 18's Attendance Officer only manages the
   employees for whom they are the native attendance manager; this addon does
   not extend those native attendance write rights.
5. Grant **Shift Overtime Approver** explicitly to the users who may decide
   calculated overtime. This is a separate role, not implied by an import.

## Results and approvals

Assuming one ordinary scheduled workday, zero special premiums/tolerances, and
one confirmed hour of unpaid break:

| Original local punch | Elapsed | Net | Regular | Raw overtime | Presence |
|---|---:|---:|---:|---:|---:|
| 18:00–03:00 next day | 9 | 8 | 8 | 0 | 1 |
| 18:00–04:00 next day | 10 | 9 | 8 | 1 | 1 |
| 18:00–05:00 next day | 11 | 10 | 8 | 2 | 1 |

Original UTC check-in/check-out values are unchanged. Native `worked_hours` is
net for managed rows; `sl_elapsed_hours` preserves the raw elapsed measure.
`sl.shift.day` retains one employee/shift-start-date anchor, source digest,
original punch links, elapsed/net/regular/raw/approved hours and immutable audit.
A verified split at the configured break is not deducted twice. Arbitrary gaps
remain absence, not guessed lunch. An open aggregate has no payable or presence
result until all its punches are closed. Presence here means one logical
nonempty completed shift, **not an overtime day-equivalent or legal payroll day**.

In **Employees → Logical Shift Attendance**, use **Approve / Refuse Overtime**.
A reason is mandatory; partial approval must be finite and between zero and raw
overtime. Raw overtime is not payable approval, even if the native company's
automatic overtime approval setting is enabled. Corrections reset the approval,
retain its audit and invalidate integration-owned draft work entries when the
optional bridge is present. Direct ORM/RPC totals, audit fields, source links,
context-default spoofing and boolean capability flags do not authorize approval.

## Native CSV/XLSX import and stable reimport

Use the native Attendances importer, with the correct import timezone. Map:

- **External ID** → `id`, a stable value unique to each source punch;
- **Employee / External ID** → `employee_id/id` for portable files, or
  **Employee / Database ID** → `employee_id/.id` for a same-database fixture;
- **Check In** → `check_in` and **Check Out** → `check_out`, with full dates.

Use the same External ID to correct or repeat an import. A blind file without
stable IDs is not an update contract. Real CSV creation/update and real XLSX
update/reimport are covered by native integration tests. Import test/dry-run
rolls its database changes back. Batch creation, out-of-order split punches and
later checkout use the same guarded engine; no `onchange`-only correction exists.

## Historical repair API

An authorized operator may call the assignment ORM action:

```python
assignment.action_repair_attendance()  # preview; also available before opt-in
assignment.action_repair_attendance(False, 'Approved historical reconciliation')
```

Preview reports proposed totals, native overtime decisions and, with the bridge,
existing work entries. Preview does not change punches, decisions or summaries.
Execution requires explicit opt-in and a reason. Pending untouched native daily
overtime can be adopted with its removed values retained in JSON audit evidence.
Decided/manual native history blocks adoption: reconcile it through its own
native authorized workflow while integration is off. No silent deletion of
approved native overtime is performed. Repeated repair retains punch/summary
identities and totals; a separate repair audit event may be appended.

Historical resolution never uses today's display-only `current_shift_id`.
Archived assignments still describe history. Templates used by managed evidence
and assignment employee identity are frozen; create future dated definitions
instead. Schedule corrections are guarded, recomputed and require reapproval.
Concurrent participating writers update a private employee coordination row so
stale repeatable-read writers must retry. This does not coordinate arbitrary SQL
or external providers that ignore the protocol.

## Boundaries and verification limits

A punch before its shift start is not inferred as an early-arrival policy. A
managed punch crossing the next shift start must be corrected/split explicitly.
Friday carryover uses Friday's roster; an unscheduled Saturday starts native
behavior. Source timestamps are never shortened to conceal a break.

The optional `sl_employee_shift_work_entry` bridge supplies finalized native
work-entry and standard done/paid payslip overlap guards. Attendance-only use
cannot certify proprietary payroll finalization. No licensed UAE Monthly Pay
structure, client file, salary rules, payroll amounts, holiday/night premiums,
hardware, browser/HTTP flow or production data repair is certified by this addon.
Its tests use synthetic local records; provider-specific payroll acceptance is
still required. Native roles and daily aggregate APIs here are Odoo 18-specific,
not a transplant of Odoo 19 overtime lines.

License: LGPL-3.0-or-later; see `LICENSE`.
