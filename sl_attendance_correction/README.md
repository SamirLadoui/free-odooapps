# Attendance Correction Requests — Odoo 15

Employees can ask to correct their **own existing attendance**, or add a genuinely
missing, closed shift. A native attendance Officer or
Administrator makes one decision within permitted companies. There is no paid dependency.

## Setup and use

1. Install `sl_attendance_correction` with the standard `hr_attendance` dependency.
2. Link each internal user to an active employee in the current company.
3. Use the existing Attendances **Officer** or **Administrator** role for decision
   makers. Odoo 15 has no designated Attendance Approver field. A generic employee
   parent/manager without the native attendance role cannot decide. Officers can
   decide requests for all employees in their permitted companies, except themselves.
4. Open **Attendance Corrections → Requests**. Choose your existing attendance, or
   leave it blank for a missing shift. Enter both proposed times and a reason.
5. **Submit** freezes the proposal and captures the native original times, last
   modification timestamp and a server-generated digest of stored attendance data. A missing period must not overlap an existing/open
   attendance. Approvers use **Approve** or **Reject** (reason required).
6. Requesters can **Cancel Request** while draft or submitted. Cancelled, rejected
   and approved requests cannot be reopened, edited or deleted. Make a fresh
   request when the proposal or underlying attendance changes.

## What approval does

Approval updates/creates `hr.attendance` using the approver's own ORM rights,
without `sudo` on the attendance mutation. Native validation and ordinary Odoo
attendance/overtime computations apply. Self-approval and self-rejection are
forbidden, including for attendance administrators. Requests are company-isolated.
The module does not grant extra rights on any existing HR model.

Originals, proposal, actor, decision date and reason remain on the request. Chatter
notes distinguish the submitted snapshot, requested values and values actually
applied, with UTC labels. Rejection/cancellation notes do not claim an attendance
change. The module logs these notes without sending notification emails; users
can still use ordinary Odoo chatter manually. Administrative database/code access
is outside the normal-RPC audit protection boundary.

## Limits and compatibility

* Backend/internal users only; no portal, public endpoints, device calls, cron,
  automatic emails/SMS, payroll processing or generic approval engine.
* Both proposed check-in and check-out are required; this release requests closed
  shifts, including closing an existing open attendance.
* A stale request must be cancelled and recreated. The module does not overwrite
  an attendance changed since submission.
* This app changes **Odoo records only**. It does not rewrite device logs or
  provide full biometric reimport integration. A later device import or another
  attendance integration may change native records; reconcile such changes with
  that integration's owner. `sl_biometric_attendance` is not modified or required.
  `pyzk` is not needed by this app.
* Concurrent decisions within this app are serialized per request and employee.
  A module-owned transaction guard handles PostgreSQL repeatable-read snapshots;
  Odoo's normal RPC retry then sees the committed decision/conflict. This is not
  a global lock protocol for device imports or unrelated native attendance writers.
* No multi-stage approvals or automatic payroll adjustments. Odoo's normal
  attendance computations still run when attendance records change.

## Tests

The addon includes native Odoo `TransactionCase` tests for requester/manager rights,
RPC values/context spoofing, snapshots, company/ownership, stale caches, overlap,
repeated decisions, rejection/cancellation and backend views. Use a disposable
local database with the matching Odoo 15 interpreter:

```
odoo-bin -d YOUR_DISPOSABLE_DB -i sl_attendance_correction --without-demo \
  --test-enable --test-tags /sl_attendance_correction --stop-after-init \
  --no-http --http-interface=127.0.0.1 --http-port=0 --max-cron-threads=0
```

## Credits and license

Copyright © 2026 **Samir Ladoui**. Maintained by Samir Ladoui.
Licensed under **GNU LGPL version 3 or later** (manifest: `LGPL-3`).
The clock icon follows the author's existing free-odooapps branding.
Odoo is a trademark of Odoo S.A.; this is an independent community addon.
Support: samir.odoo.apps2325@gmail.com
