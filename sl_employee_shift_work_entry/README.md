# Employee Shift Work Entries — Odoo 15

Optional provider-neutral bridge. Dependencies: `sl_employee_shift_attendance` and
native `hr_work_entry_contract`. No payroll provider is a mandatory dependency.

## Enable both boundaries explicitly

1. Configure the historical assignment and custom attendance policy as described
   in `sl_employee_shift_attendance/README.md`.
2. Enable **Manual Shift Work Entries** on that assignment and deliberately map
   two distinct **non-leave** native work-entry types: regular and approved overtime.
   Odoo 15 supplies the regular `WORK100` type but no generic overtime XML ID;
   create/select an appropriate type for your provider. This addon sets no rates.
3. On the historical effective employee contract, select **Shift Summary (Explicit
   Manual Generation)** in the addon-owned **Shift Work Entry Source** field
   (`sl_shift_work_entry_source`). Its default remains **Native Calendar**.
   Odoo 15 has no native `work_entry_source` field; this port does not pretend it
   does. Every exported interval must have exactly one effective same-company
   open/closed contract with the explicit manual source. Today's current contract
   is not substituted for historical contract coverage.
4. Give the generating user HR Administrator, Contract Administrator/native
   work-entry rights and **Shift Overtime Approver** roles as appropriate. Use
   **Generate / Open Work Entries** on a completed Logical Shift Attendance form.
   Approve overtime first if it is payable. Pending/refused days export regular
   time only.

## Actual native intervals, no duplicate engine

The explicit generator produces real `hr.work.entry` start/stop rows linked to
`contract_id`, `sl_shift_day_id`, kind and source digest. The 18:00–05:00 example
with a 22:00–23:00 unpaid break and two approved overtime hours yields:

```text
D   18:00–22:00  regular  4h
D   23:00–24:00  regular  1h
D+1 00:00–03:00  regular  3h
D+1 03:00–05:00  overtime 2h
```

Net intervals exclude the break, and split on the assignment's **actual local
midnight**. Presence remains one day on D; overtime/day-equivalent hours are not
additional days present. A month-end shift contributes five hours to each adjacent
month in this example, with one presence anchor in the starting month. Partial
approval exports only the approved duration, allocated chronologically after the
regular budget. No salary rule or statutory premium is inferred.

Odoo 15 generation is intercepted at `_get_contract_work_entries_values`,
`_get_work_entries_values` and `_generate_work_entries`: automatic/force-native
calendar generation returns no rows for the explicit manual source. There is no
16+ public `generate_work_entries` API used in this port. Native calendar contracts
remain native. Explicit generation updates the native generated-coverage bounds.
Repeating generation with the same authoritative payload reuses the same IDs;
corrected evidence/approval replaces **only owned mutable** rows. Existing
unrelated native entries are reported/refused, never deleted or archived by this
addon. It does not run the broad native regeneration wizard automatically.

## Integrity and closed periods

Direct source/default/relational spoofing, copy, unauthorized generation, financial
writes and source reparenting are refused. Types, contract ownership/source and
assignment mappings already used by shift entries are frozen; use future dated
records for changes. Validation remains a native action with an explicit approver
role and current-evidence check.

Validated shift entries cannot be edited, cancelled, archived, unlinked or reset
through this addon. A finalized native work-entry overlap (including archived
entries), or standard optional `hr.payslip` in done/paid state, blocks attendance,
assignment, approval and regeneration changes. Both the full duty window and actual
old/new attendance interval overlaps are checked; a check-in before the managed
assignment cannot bypass the finalized interval boundary. Idempotent read/reuse of
identical entries is allowed. Corrections require a separately authorized adjustment
outside the closed period, not rewriting finalized evidence.

Leave/public-holiday overlap fails closed because the payroll provider must decide
its classification. No forced payslip recomputation, salary rate/divisor change,
posting or finalized-data repair is provided. A proprietary provider with different
models/states still needs integration review. No licensed payroll/UAE Monthly Pay
stack was available, so **no real UAE draft payslip or fixed-salary result is
claimed**. Native installation/upgrade, ORM, import and Form tests are not browser,
physical-device or live-provider certification.

LGPL-3; see `LICENSE`.
