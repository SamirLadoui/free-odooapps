# Employee Shift Work Entries — Odoo 17

Optional provider-neutral bridge from authoritative shift summaries to native
`hr.work.entry` intervals. Depends on `sl_employee_shift_attendance` and
`hr_work_entry_contract`, **not** licensed payroll. Installation/upgrade does not
enable assignment generation or switch an employee's contract source.

## Required explicit configuration

1. Configure/opt in the historical assignment's custom attendance policy and
   explicit unpaid break. Review its attendance companion README first.
2. Enable **Manual Shift Work Entries** on that assignment and explicitly select
   two distinct, non-leave regular/overtime types. Odoo 17's native examples are
   `hr_work_entry.work_entry_type_attendance` (`WORK100`) and
   `hr_work_entry.overtime_work_entry_type` (`OVERTIME`); the addon does not select
   types automatically or change their salary consumers.
3. Select **Shift Summary (Explicit Manual Generation)** (`sl_shift_manual`) on
   exactly one same-company open/closed historical contract covering each actual
   local work date. Today's employee contract is not substituted for history.
4. Give the generating actor HR Administrator and **Shift Overtime Approver**
   roles, plus the native access needed for contracts/work entries. Configuration
   also requires the Attendance Administrator role. No native ACL is widened.
5. Inspect Employees → Logical Shift Attendance; decide overtime with a reason,
   then choose **Generate / Open Work Entries**. Regular hours can be generated
   while overtime is pending/refused; only explicitly approved overtime exports.

Generation is deliberate/manual, not an import side effect. All relevant native
contract generation entrypoints exclude the manual source, including forced
regeneration. Selecting that source refuses unreconciled existing work entries
instead of letting the native broad regeneration wizard archive them.

## Output contract

For a UTC 18:00–05:00 punch, explicit 22:00–23:00 unpaid break, eight-hour regular
budget and two approved extra hours:

| Native interval | Kind | Hours |
|---|---|---:|
| D 18:00–22:00 | Regular | 4 |
| D 23:00–D+1 00:00 | Regular | 1 |
| D+1 00:00–03:00 | Regular | 3 |
| D+1 03:00–05:00 | Approved overtime | 2 |

Entries are actual, nonoverlapping net intervals: no full nine-hour attendance
span disguised as eight hours. Breaks/gaps are not paid. Partial approved overtime
uses only that many tail hours. Hours split at midnight in the assignment's
historical timezone; presence stays one anchor on D. The 30 November carryover
is therefore split into actual November/December hours without duplicating days.
No statutory rate, salary amount, salary rule or native overtime adjustment is
added to these quantities.

Each draft row retains `sl_shift_day_id`, kind and source digest. Repeated
unchanged generation returns the same identities. Corrections/changed decisions
invalidate only owned drafts; unrelated entries are reported/refused, never
automatically deleted. Native create/write guards inspect complete prospective
intervals, including context defaults, duration-only updates, long spans starting
outside an assignment and native inferred contract ownership. Callers cannot
forge managed links, quantities, relational children or approval capabilities.

## Freeze and audit boundaries

Native validation is separate from overtime approval. Validation requires the
Shift Overtime Approver role and current source evidence. Validated managed rows
cannot be edited, reopened, cancelled, moved or deleted. Any finalized native
work-entry overlap blocks attendance/assignment/decision repair, even if the
finalized row came from another source. An available standard `hr.payslip` model
is checked for overlapping `done`/`paid` slips; unknown proprietary states/models
are not certified.

Contracts and mapped type semantics already used by shift evidence are frozen;
use new dated contracts/types for future changes. Historical assignment employee
and employee company cannot be reparented after evidence. Timezone/workday/break
changes that affect finalized periods are refused atomically. Audit events are
immutable. UI readonly fields are not the protection: real ORM/RPC create/write,
context defaults, action, unlink and parent-change paths are guarded/tested.

## Preview / API

`assignment.action_repair_attendance()` includes existing native work entries,
finalized blockers and proposed hours. It does not generate entries.
`day.action_generate_work_entries()` returns native records; the UI wrapper
`day.action_generate_and_open_work_entries()` returns a serializable native
window action. Only a matching unchanged result can be reused after validation.

## Limits and deployment

Leave/public-holiday overlaps fail closed until the payroll provider's treatment
is agreed. There is no browser automation, legal wage/rate advice, licensed
payroll provider implementation, payslip calculation or production migration.
The original client spreadsheet, exact UAE Monthly Pay salary structure and
client cutoff policy are unavailable. Synthetic native work-entry tests do not
prove a real client payslip or fixed-salary preservation. Test a backup of the
actual licensed stack before any client data repair. This source targets 17.0;
sibling versions require independently executed native verification.

LGPL-3; see `LICENSE`. Author: Samir Ladoui.
