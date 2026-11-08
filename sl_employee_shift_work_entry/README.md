# Employee Shift Work Entries — Odoo 16

Optional provider-neutral bridge from `sl.shift.day` to real `hr.work.entry`.
Depends on `sl_employee_shift_attendance` and `hr_work_entry_contract` (and its native Contracts/Work Entries dependencies), not a Payroll
engine. No wage, statutory multiplier, salary rule, or payslip total is supplied.

## Explicit setup and manual generation

1. Configure and enable the attendance companion first (see its README).
2. As an HR and Attendance Administrator, enable **Manual Shift Work Entries**
   on the dated assignment. Explicitly select distinct regular and overtime
   non-leave work-entry types appropriate to the provider. Odoo 16 has no generic native overtime type in these sources; explicitly configure your own type.
3. Select **Shift Summary (Explicit Manual Generation)** as the work-entry
   source of every applicable effective `hr.contract`, with valid contract dates
   and state Open/Expired. This is an exclusive source: native calendar/attendance
   generation does not also generate entries for those contracts. The historical
   interval selects the contract, not the employee's current contract. Nothing switches source
   automatically. Resolve existing unrelated entries before generation.
4. On **Logical Shift Attendance**, an HR Administrator who also holds **Shift
   Overtime Approver** and the native **Contracts / Administrator** role can use
   **Generate / Open Work Entries**. Contract generation coverage is maintained
   with the actor's real rights, never by granting extra contract ACLs. Pending/refused
   overtime produces regular hours only. Approve the actual permitted amount
   before exporting overtime; changing approval invalidates owned draft entries.
5. Validate the resulting native entries through their normal action as an
   authorized shift approver. Native work-entry validation is not proof that a
   client's payslip consumed those entries.

The ORM API is `day.action_generate_work_entries()`; the UI action wrapper is
`day.action_generate_and_open_work_entries()`. Repeating generation returns the
same entries when the authoritative source evidence and mapping have not changed.
There is no scheduled automatic export.

## Date allocation and presence

Odoo 16 stores real **date_start/date_stop/contract_id** intervals. The bridge
excludes the configured unpaid break, allocates regular hours first and approved
excess afterward, and clips intervals at actual local calendar midnight. It does
not write a fake duration onto a gross interval, add a rate/amount field, or assume
a salary rule. Presence remains on the local shift-start date and must not be
calculated by summing overtime day-equivalents.

For a synthetic UTC 18:00–05:00 attendance, 22:00–23:00 break, and approval of
two overtime hours: D 18:00–22:00 and 23:00–24:00 are 5 regular hours;
D+1 00:00–03:00 is 3 regular hours and 03:00–05:00 is 2 approved overtime hours.
The 22:00–23:00 break is absent from native entries.
The total is 8 regular + 2 overtime and one logical presence, including across
month end. The client must approve this allocation policy before rollout.

## Historical repair and closed periods

The assignment's dry-run API also reports existing native entries and finalized
entry blockers. It never deletes unrelated/native-source entries. Only this
bridge's own draft entries may be reconciled, with immutable source/audit links.
Direct quantity/source writes, forged context defaults, and duplicate native
creation for enabled dates are denied. Validated managed entries cannot be
rewritten, reopened, archived, split, deleted, or altered through source punches,
assignment policy, mapped types, or used contract ownership/source.

Finalized native entries and overlapping standard `hr.payslip` records in
`done`/`paid` block automatic correction. Unknown proprietary payroll states and
providers are not certified by that defensive optional check. There is no
production repair or finalized-payslip adjustment tool in this module.

Leave/public-holiday overlap fails closed pending provider classification; it is
not silently turned into ordinary work/overtime. This protects against accidental
double payment but does not implement localization-specific leave rules.

## Acceptance boundary

Native install/upgrade, real CSV/XLSX imports, permissions, immutable evidence,
regular/approved overtime, idempotency, and synthetic period boundaries are the
module's testable scope. A real UAE Monthly Pay payslip and fixed-salary behavior
still require the client's licensed modules, anonymized input, historical
configuration, and provider-specific acceptance before production use.

License: LGPL-3.
