# SPDX-License-Identifier: LGPL-3.0-or-later
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from datetime import timedelta

import pytz

from .summary import trusted


class ShiftAssignment(models.Model):
    _inherit = 'sl.shift.assignment'

    attendance_policy = fields.Selection([
        ('off', 'Native (no shift integration)'),
        ('shift', 'Shift net hours — custom authoritative overtime'),
    ], default='off', required=True)

    @api.constrains('attendance_policy', 'break_window_set', 'break_start', 'shift_id', 'schedule_tz', 'workdays')
    def _sl_check_enabled(self):
        for assignment in self.filtered(lambda a: a.attendance_policy == 'shift'):
            assignment._sl_window(assignment.date_from, check_workday=False)

    def _sl_config_authorize(self):
        if not (self.env.user.has_group('hr.group_hr_manager')
                and self.env.user.has_group('hr_attendance.group_hr_attendance_manager')):
            raise AccessError(_('Shift attendance configuration requires HR and Attendance administrator roles.'))
        self.check_access_rights('write')
        self.check_access_rule('write')
        if any(a.company_id not in self.env.companies for a in self):
            raise AccessError(_('The assignment company is not enabled.'))

    def _sl_punches(self):
        # A deliberately bounded employee/date repair, with a one-day UTC margin
        # for timezone conversion and midnight carryover.
        from datetime import datetime, timedelta
        punches = self.env['hr.attendance']
        for assignment in self:
            start = datetime.combine(assignment.date_from, datetime.min.time()) - timedelta(days=1)
            domain = [('employee_id', '=', assignment.employee_id.id), ('check_in', '>=', start)]
            if assignment.date_to:
                end = datetime.combine(assignment.date_to, datetime.max.time()) + timedelta(days=2)
                domain.append(('check_in', '<=', end))
            punches |= self.env['hr.attendance'].search(domain)
        return punches

    def action_repair_attendance(self, dry_run=True, reason=None):
        self._sl_config_authorize()
        punches = self._sl_punches()
        preview = []
        groups = {}
        for attendance in punches:
            candidates = self.filtered(lambda a, employee=attendance.employee_id: a.employee_id == employee)
            assignment, window = candidates._sl_resolve(attendance.employee_id, attendance.check_in) if candidates else (candidates, None)
            if assignment:
                key = (assignment.id, window['date'])
                if key not in groups:
                    groups[key] = (assignment, window, self.env['hr.attendance'])
                a, w, records = groups[key]
                groups[key] = (a, w, records | attendance)
        for assignment, window, records in groups.values():
            proposed = self.env['sl.shift.day']._sl_values(assignment, window, records)
            native_dates = {records._get_day_start_and_day(assignment.employee_id, a.check_in)[1] for a in records}
            native = self.env['hr.attendance.overtime'].search([
                ('employee_id', '=', assignment.employee_id.id), ('date', 'in', list(native_dates)), ('adjustment', '=', False),
            ])
            days = records.sl_shift_day_id
            preview.append({'attendance_ids': records.ids, 'shift_date': str(window['date']),
                            'employee_id': assignment.employee_id.id,
                            'old_net_hours': sum(records.mapped('worked_hours')),
                            'old_native_overtime': sum(native.mapped('duration')),
                            'old_approved_overtime': 0,
                            'proposed_net_hours': proposed['net_hours'],
                            'proposed_regular_hours': proposed['regular_hours'],
                            'proposed_raw_overtime_hours': proposed['raw_overtime_hours'],
                            'proposed_presence_days': proposed['presence_days'],
                            'proposed_approved_overtime': sum(days.mapped('approved_overtime_hours')) if days and days.digest == proposed['digest'] else 0,
                            'native_overtime': native.read(['date', 'duration', 'duration_real', 'adjustment']),
                            'native_decision_blocks_repair': False,
                            'summary_ids': days.ids, 'punches_unchanged': True})
        if dry_run is not False:
            return preview
        if any(a.attendance_policy != 'shift' for a in self):
            raise UserError(_('Opt in explicitly before executing a repair; preview is available while integration is off.'))
        if not reason or not reason.strip():
            raise ValidationError(_('A repair reason is required.'))
        with self.env.cr.savepoint():
            self.env['sl.shift.guard']._sl_lock(self.employee_id.ids)
            old = punches.sl_shift_day_id
            old._sl_assert_mutable()
            for attendance in punches:
                assignment, window = attendance._sl_assignment()
                if assignment:
                    self.env['sl.shift.day']._sl_check_mutation(attendance.employee_id, window)
            self.env['sl.shift.day']._sl_sync(punches, old)
            punches._update_overtime()
            for field in ('worked_hours',):
                self.env.add_to_compute(punches._fields[field], punches)
            punches.sl_shift_day_id._sl_audit('repair', reason, {'attendance_ids': punches.ids})
        return preview

    @api.model_create_multi
    def create(self, vals_list):
        defaults = self.default_get(['employee_id', 'attendance_policy'])
        default_employee_id = defaults.get('employee_id') or self.env.context.get('default_employee_id')
        default_policy = defaults.get('attendance_policy') or 'off'
        enabled_employee_ids = []
        employee_ids = []
        for vals in vals_list:
            employee_id = vals.get('employee_id') or default_employee_id
            if employee_id:
                employee_ids.append(employee_id)
                if vals.get('attendance_policy', default_policy) == 'shift':
                    enabled_employee_ids.append(employee_id)
        employees = self.env['hr.employee'].browse(sorted(set(employee_ids)))
        employees.check_access_rights('read')
        employees.check_access_rule('read')
        if any(employee.company_id not in self.env.companies for employee in employees):
            raise AccessError(_('The employee company is not enabled for this user.'))
        self.check_access_rights('create')
        enabled = any(v.get('attendance_policy', default_policy) == 'shift' for v in vals_list)
        if enabled and not (self.env.user.has_group('hr.group_hr_manager') and self.env.user.has_group('hr_attendance.group_hr_attendance_manager')):
            raise AccessError(_('Enabling shift integration requires HR and Attendance administrator roles.'))
        if enabled_employee_ids:
            # Punch writers use this employee key before resolving assignments.
            # New opted-in assignments must participate before becoming visible.
            self.env['sl.shift.guard']._sl_lock(enabled_employee_ids)
        records = super().create(vals_list)
        # Enabling does not silently repair historical attendance or approvals.
        return records

    def write(self, vals):
        schedule_fields = {'employee_id', 'shift_id', 'date_from', 'date_to', 'schedule_tz',
                           'workdays', 'break_window_set', 'break_start', 'attendance_policy'}
        historical_schedule_fields = schedule_fields - {'attendance_policy'}
        if (historical_schedule_fields.intersection(vals)
                and any(a.attendance_policy == 'off' for a in self)
                and self.env['sl.shift.day'].sudo().search_count([('assignment_id', 'in', self.ids)])):
            raise UserError(_('A disabled assignment with shift history is immutable.'))
        if not schedule_fields.intersection(vals) or not any(a.attendance_policy == 'shift' or vals.get('attendance_policy') == 'shift' for a in self):
            return super().write(vals)
        self._sl_config_authorize()
        if 'employee_id' in vals and any(a.employee_id.id != vals['employee_id'] for a in self):
            target = self.env['hr.employee'].browse(vals['employee_id'])
            target.check_access_rights('read')
            target.check_access_rule('read')
            if target.company_id not in self.env.companies:
                raise AccessError(_('The employee company is not enabled for this user.'))
            if self.env['sl.shift.day'].sudo().search_count([('assignment_id', 'in', self.ids)]):
                raise UserError(_('An assignment employee with historical shift evidence cannot be changed.'))
        with self.env.cr.savepoint():
            self.env['sl.shift.guard']._sl_lock(self.employee_id.ids + ([vals['employee_id']] if vals.get('employee_id') else []))
            before = self._sl_punches()
            old_days = before.sl_shift_day_id
            old_days._sl_assert_mutable()
            result = super().write(vals)
            after = before | self._sl_punches()
            for attendance in after:
                assignment, window = attendance._sl_assignment()
                if assignment:
                    self.env['sl.shift.day']._sl_check_mutation(attendance.employee_id, window)
            self.env['sl.shift.day']._sl_sync(after, old_days)
            after._update_overtime()
            for field in ('worked_hours',):
                self.env.add_to_compute(after._fields[field], after)
            return result

    def unlink(self):
        if self.env['sl.shift.day'].sudo().search_count([('assignment_id', 'in', self.ids)]):
            raise UserError(_('Historical assignments with shift evidence cannot be deleted.'))
        return super().unlink()


class Shift(models.Model):
    _inherit = 'sl.shift'

    def write(self, vals):
        self.check_access_rights('write')
        self.check_access_rule('write')
        # Assignment opt-ins use the same template key. Lock before searching so
        # a concurrent opted-in assignment cannot slip past this authorization.
        self.env['sl.shift.template.guard']._sl_lock(self.ids)
        assignments = self.env['sl.shift.assignment'].sudo().with_context(active_test=False).search([
            ('shift_id', 'in', self.ids),
        ])
        opted_assignments = assignments.filtered(lambda assignment: assignment.attendance_policy == 'shift')
        if opted_assignments:
            opted_assignments.with_user(self.env.user)._sl_config_authorize()
        if {'start_time', 'end_time', 'break_minutes'}.intersection(vals):
            if assignments:
                self.env['sl.shift.guard']._sl_lock(assignments.employee_id.ids)
                if self.env['sl.shift.day'].sudo().search_count([('assignment_id', 'in', assignments.ids)]):
                    raise UserError(_('A shift with attendance evidence is frozen. Create a new shift and a future dated assignment.'))
        return super().write(vals)


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    sl_shift_day_id = fields.Many2one('sl.shift.day', readonly=True, copy=False, ondelete='restrict', index=True)
    sl_elapsed_hours = fields.Float(compute='_compute_sl_elapsed', string='Raw Elapsed Hours')

    sl_raw_overtime_hours = fields.Float(compute='_compute_sl_overtime', string='Shift Raw Overtime')
    sl_approved_overtime_hours = fields.Float(compute='_compute_sl_overtime', string='Shift Approved Overtime')

    @api.depends('check_in', 'check_out', 'sl_shift_day_id.digest', 'sl_shift_day_id.state', 'sl_shift_day_id.approved_overtime_hours')
    def _compute_sl_overtime(self):
        for attendance in self:
            raw, approved = attendance._sl_allocation()
            attendance.sl_raw_overtime_hours = raw
            attendance.sl_approved_overtime_hours = approved

    @api.depends('check_in', 'check_out', 'employee_id', 'sl_shift_day_id.digest')
    def _compute_worked_hours(self):
        managed = self.filtered(lambda a: bool(a._sl_assignment()[0]))
        super(HrAttendance, self - managed)._compute_worked_hours()
        for attendance in managed:
            window = attendance._sl_assignment()[1]
            attendance.worked_hours = attendance._sl_net_in_window(window, attendance.check_in, attendance.check_out) if attendance.check_out else 0

    @api.depends('check_in', 'check_out')
    def _compute_sl_elapsed(self):
        for attendance in self:
            attendance.sl_elapsed_hours = (attendance.check_out - attendance.check_in).total_seconds() / 3600 if attendance.check_out and attendance.check_in else 0

    def _sl_assignment(self):
        self.ensure_one()
        if not self.employee_id or not self.check_in:
            return self.env['sl.shift.assignment'], None
        assignments = self.env['sl.shift.assignment'].sudo().with_context(active_test=False).search([
            ('employee_id', '=', self.employee_id.id), ('attendance_policy', '=', 'shift'),
        ])
        return assignments._sl_resolve(self.employee_id, self.check_in) if assignments else (assignments, None)

    def _sl_net_in_window(self, window, start, stop):
        self.ensure_one()
        elapsed = max(0, (stop - start).total_seconds())
        if window['break_start']:
            elapsed -= max(0, (min(stop, window['break_stop']) - max(start, window['break_start'])).total_seconds())
        return max(0, elapsed) / 3600

    def _sl_allocation(self):
        """Allocate excess to the tail punches; never duplicate daily totals."""
        self.ensure_one()
        day = self.sl_shift_day_id
        if not day or day.state in ('open', 'void'):
            return 0, 0
        consumed = 0
        for attendance in day.attendance_ids.sorted(lambda a: (a.check_in, a.id)):
            net = attendance._sl_net_in_window(attendance._sl_assignment()[1], attendance.check_in, attendance.check_out) if attendance.check_out else 0
            overtime = max(0, consumed + net - day.expected_hours) - max(0, consumed - day.expected_hours)
            if attendance == self:
                approved = min(overtime, max(0, day.approved_overtime_hours - max(0, consumed - day.expected_hours)))
                return overtime, approved
            consumed += net
        return 0, 0

    @api.model
    def _sl_native_date_managed(self, employee, day):
        """Native16 owns a whole employee/check-in day, never a punch fragment.

        Exclude configured shift-start days plus after-midnight managed punch
        dates. Adjustment rows and other employee/days remain entirely native.
        """
        if not employee or not day:
            return False
        day = fields.Date.to_date(day)
        zone = pytz.timezone(employee._get_tz())
        from datetime import datetime, time
        begin = zone.localize(datetime.combine(day, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        end = zone.localize(datetime.combine(day + timedelta(days=1), time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        punches = self.sudo().search([('employee_id', '=', employee.id), ('check_in', '>=', begin), ('check_in', '<', end)])
        if any(a._sl_assignment()[0] for a in punches):
            return True
        assignments = self.env['sl.shift.assignment'].sudo().with_context(active_test=False).search([
            ('employee_id', '=', employee.id), ('attendance_policy', '=', 'shift'),
        ])
        for assignment in assignments:
            for local_day in (day - timedelta(days=1), day, day + timedelta(days=1)):
                if (local_day < assignment.date_from or assignment.date_to and local_day > assignment.date_to
                        or str(local_day.weekday()) not in assignment.workdays.split(',')):
                    continue
                window = assignment._sl_window(local_day)
                if window and self._get_day_start_and_day(employee, window['start'])[1] == day:
                    return True
        return False

    def _update_overtime(self, employee_attendance_dates=None):
        dates = self._get_attendances_dates() if employee_attendance_dates is None else employee_attendance_dates
        native = {}
        for employee, day_pairs in dates.items():
            eligible = {pair for pair in day_pairs if not self._sl_native_date_managed(employee, pair[1])}
            if eligible:
                native[employee] = eligible
        # Native16 accepts employee -> {(UTC day start, local date)}; it searches
        # complete aggregates itself. Passing a filtered recordset alone is unsafe.
        return super()._update_overtime(native)

    def _sl_check_protected(self, vals, employee=None, check_in=None):
        if trusted(self.env):
            return
        protected = {'sl_shift_day_id', 'sl_elapsed_hours', 'worked_hours', 'overtime_hours',
                     'sl_raw_overtime_hours', 'sl_approved_overtime_hours'}
        is_managed = any(bool(a._sl_assignment()[0]) or a.sl_shift_day_id for a in self)
        if employee and employee.sudo().company_id not in self.env.companies:
            # Native16 checks write rules on the old attendance, not its new
            # employee. Authorize the destination before any ORM mutation.
            raise AccessError(_('The attendance employee company is not enabled for this user.'))
        if employee and check_in:
            probe = self.new({'employee_id': employee.id, 'check_in': check_in})
            is_managed |= bool(probe._sl_assignment()[0])
        if ('sl_shift_day_id' in vals or 'default_sl_shift_day_id' in self.env.context
                or is_managed and (protected.intersection(vals) or any('default_' + f in self.env.context for f in protected))):
            raise AccessError(_('Managed attendance totals, approval and source links are maintained internally.'))

    def _sl_before_mutation(self, proposed=None):
        candidates = self | (proposed or self.browse())
        self.env['sl.shift.guard']._sl_lock(candidates.employee_id.ids)
        self.sl_shift_day_id._sl_assert_mutable()
        for attendance in candidates:
            assignment, window = attendance._sl_assignment()
            if assignment:
                self.env['sl.shift.day']._sl_check_mutation(attendance.employee_id, window)
                if attendance.check_out and attendance.check_out > window['next_start']:
                    raise ValidationError(_('A managed punch must not cross the next shift start.'))

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access_rights('create')
        for vals in vals_list:
            employee = self.env['hr.employee'].browse(vals.get('employee_id') or self.env.context.get('default_employee_id') or self._default_employee().id)
            check_in = vals.get('check_in') or self.env.context.get('default_check_in') or fields.Datetime.now()
            self._sl_check_protected(vals, employee, check_in)
        with self.env.cr.savepoint():
            proposed = self.browse()
            for vals in vals_list:
                proposed |= self.new(dict(employee_id=vals.get('employee_id') or self.env.context.get('default_employee_id') or self._default_employee().id,
                                           check_in=vals.get('check_in') or self.env.context.get('default_check_in') or fields.Datetime.now(),
                                           check_out=vals.get('check_out') or self.env.context.get('default_check_out')))
            proposed._sl_before_mutation()
            records = super().create(vals_list)
            self.env['sl.shift.day']._sl_sync(records)
            return records

    def write(self, vals):
        self.check_access_rights('write')
        self.check_access_rule('write')
        if trusted(self.env):
            return super().write(vals)
        self._sl_check_protected(vals)
        if not {'employee_id', 'check_in', 'check_out'}.intersection(vals):
            return super().write(vals)
        with self.env.cr.savepoint():
            proposed = self.browse()
            for attendance in self:
                employee = self.env['hr.employee'].browse(vals.get('employee_id', attendance.employee_id.id))
                check_in = vals.get('check_in', attendance.check_in)
                self._sl_check_protected(vals, employee, check_in)
                proposed |= self.new({'employee_id': employee.id, 'check_in': check_in,
                                      'check_out': vals.get('check_out', attendance.check_out)})
            self._sl_before_mutation(proposed)
            previous = self.sl_shift_day_id
            result = super().write(vals)
            self.env['sl.shift.day']._sl_sync(self, previous)
            return result

    def unlink(self):
        self.check_access_rights('unlink')
        self.check_access_rule('unlink')
        with self.env.cr.savepoint():
            self._sl_before_mutation()
            previous = self.sl_shift_day_id
            result = super().unlink()
            self.env['sl.shift.day']._sl_sync(self.browse(), previous)
            return result


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def write(self, vals):
        if 'company_id' in vals and any(e.company_id.id != vals['company_id'] for e in self):
            if self.env['sl.shift.day'].sudo().search_count([('employee_id', 'in', self.ids)]):
                raise UserError(_('Employee company with historical shift evidence is frozen.'))
        return super().write(vals)


class NativeOvertime(models.Model):
    _inherit = 'hr.attendance.overtime'

    def _sl_reject_managed(self, vals=None):
        if trusted(self.env):
            return
        vals = vals or {}
        # Check both original and proposed ownership, including defaults; an
        # adjustment must not be converted into an automatic managed aggregate.
        effective_rows = [dict(employee_id=r.employee_id.id, date=r.date, adjustment=r.adjustment) for r in self]
        targets = [dict(row, **vals) for row in effective_rows] if self else [vals]
        for row in effective_rows + targets:
            if (not row.get('adjustment') and row.get('employee_id') and row.get('date')
                    and self.env['hr.attendance']._sl_native_date_managed(self.env['hr.employee'].browse(row['employee_id']), row['date'])):
                raise AccessError(_('This employee/day uses the custom shift engine; native automatic overtime cannot also be created or edited. Adjustment rows remain native.'))

    @api.model_create_multi
    def create(self, vals_list):
        defaults = self.default_get(['employee_id', 'date', 'adjustment'])
        for vals in vals_list:
            self._sl_reject_managed(dict(defaults, **vals))
        return super().create(vals_list)

    def write(self, vals):
        self._sl_reject_managed(vals)
        return super().write(vals)

    def unlink(self):
        self._sl_reject_managed()
        return super().unlink()
