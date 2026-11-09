# Employee Shift Work Entries — Odoo 18

Optional, provider-neutral bridge from approved logical shift attendance to
native Odoo 18 **contract/start-stop `hr.work.entry` intervals**. Depends on
`sl_employee_shift_attendance` and native `hr_work_entry_contract`, not on a
payroll engine. No salary rule, wage, divisor, premium or statutory rate is set.

## Two explicit opt-ins

1. Configure historical dates, timezone, start weekdays and the explicit break
   on the assignment; select the custom shift attendance policy.
2. Enable **Manual Shift Work Entries** and select two distinct non-leave types:
   regular and approved overtime. Country-restricted types must match the company.
   Typical Odoo 18 mappings are `hr_work_entry.work_entry_type_attendance`
   (`WORK100`) and **`hr_work_entry.overtime_work_entry_type`** (`OVERTIME`).
3. Select **Shift Summary (Explicit Manual Generation)** on each applicable
   historical native contract (`work_entry_source='sl_shift_manual'`). Each
   actual local work date requires exactly one same-company open/closed contract.
   Native Contracts Administrator rights remain necessary to configure contracts.
4. Explicit generation requires **HR Administrator + Shift Overtime Approver**,
   enabled company access and native work-entry access. This does not grant
   general contract or attendance write rights.
5. Use **Generate / Open Work Entries** on the logical shift summary, or call
   `day.action_generate_work_entries()` as an authorized actor. The UI action
   opens the real native work entries. There is no automatic scheduled generator
   for the manual source; native contract generation returns no duplicate entries.

Installing/upgrading either companion enables none of these settings by default.
Changing a calendar-source contract to the manual source refuses existing native
entries instead of invoking a broad archive/regeneration wizard over them.

## What is exported

Only completed nonempty shifts generate entries. Regular net time is allocated
first, then **approved** overtime, never pending/refused raw overtime. An ordinary
18:00–03:00 shift with an explicit 22:00–23:00 unpaid break yields 8 regular hours.
A checkout at 05:00 yields 8 regular hours plus at most 2 approved overtime hours.

Breaks are excluded from real intervals, not hidden in altered punches. Entries
are split at actual local midnight using the saved schedule timezone. For the
UTC 18:00–05:00 example, the intervals are:

| From | To | Kind | Hours |
|---|---|---|---:|
| D 18:00 | D 22:00 | Regular | 4 |
| D 23:00 | D+1 00:00 | Regular | 1 |
| D+1 00:00 | D+1 03:00 | Regular | 3 |
| D+1 03:00 | D+1 05:00 | Approved overtime | 2 |

A month-end example allocates 5 hours to the starting month and 5 to the next,
without loss or duplication. The summary still reports **one** presence anchored
to the shift-start date. This presence value does not rewrite native payslip
worked-day or overtime day-equivalent calculations. Native contract generation
coverage bounds and last-generation date are maintained from generated intervals.

`sl_shift_day_id`, `sl_shift_kind` and `sl_shift_digest` retain provenance on every
owned native entry. Repeated generation retains matching identities; approved
quantity/source changes replace only owned draft entries. The optional bridge
does not delete another engine's records. Existing overlapping unrelated entries
block generation and appear in repair preview. Direct creation/reparenting,
caller/context source defaults and whole multi-day/duration-driven native
intervals cannot duplicate an enabled manual-source duty period, even before its
first punch. Ownership uses historical local windows, not just a UTC start date.

## Finalization and corrections

Native work-entry validation is separate from overtime approval and is not a
posted payslip. Managed validation requires Shift Overtime Approver and current
source digests. Once native entries are validated, attendance edits/deletion,
reapproval/refusal, date/parent/company changes, assignment schedule corrections,
source changes, type remapping and direct entry write/unlink are blocked.
Idempotent generation may return the same finalized entries; it cannot rewrite
them. Used source contracts, mapping and type semantics are frozen; create new
future dated records for changes. Unknown/closed-period differences require a
separate authorized adjustment, not automatic repair.

Standard `hr.payslip` in `done`/`paid`, when that model is installed, also blocks
an overlapping correction. Calendar absences and public holidays with
`time_type='leave'` block generation when their UTC intervals overlap the duty
window. Validated `time_type='other'` records retain native worked-time semantics
and are not treated as absences. There is no guessed leave, weekend, night, premium
or fixed-monthly-salary rule.

## Operational boundary

Before client adoption, obtain the original anonymized import, exact licensed
payroll/localization source, historical calendars/contracts and timezone,
workdays, break window and payroll cutoff policy. Use a backup and preview; do
not mass-delete work entries, overwrite posted payslips or enable all historical
assignments implicitly. The ORM preview/repair API is documented in the
attendance companion. Native regeneration of other sources is not an integration
repair API.

Local regression tests exercise the real Odoo 18 ORM/importer/native intervals,
restricted roles/company isolation, approval, idempotency and finalized SQL
snapshots. They are not an unseen client's UAE payslip certification, a live
provider check, concurrency certification against external SQL, or browser/
hardware testing. No SMTP/SMS/payment/device delivery is needed.

License: LGPL-3.0-or-later; see `LICENSE`.
