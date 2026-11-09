# SPDX-License-Identifier: LGPL-3.0-or-later
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain

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
        self.check_access('write')
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
            native = self.env['hr.attendance.overtime.line'].search([
                ('employee_id', '=', assignment.employee_id.id), ('time_start', 'in', records.mapped('check_in')),
            ])
            days = records.sl_shift_day_id
            preview.append({'attendance_ids': records.ids, 'shift_date': str(window['date']),
                            'employee_id': assignment.employee_id.id,
                            'old_net_hours': sum(records.mapped('worked_hours')),
                            'old_native_overtime': sum(records.mapped('overtime_hours')),
                            'old_approved_overtime': sum(records.mapped('validated_overtime_hours')),
                            'proposed_net_hours': proposed['net_hours'],
                            'proposed_regular_hours': proposed['regular_hours'],
                            'proposed_raw_overtime_hours': proposed['raw_overtime_hours'],
                            'proposed_presence_days': proposed['presence_days'],
                            'proposed_approved_overtime': sum(days.mapped('approved_overtime_hours')) if days and days.digest == proposed['digest'] else 0,
                            'native_overtime': native.read(['date', 'duration', 'manual_duration', 'status']),
                            'native_decision_blocks_repair': any(l.status != 'to_approve' or l.manual_duration != l.duration for l in native),
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
            for field in ('worked_hours', 'overtime_hours', 'validated_overtime_hours', 'overtime_status', 'expected_hours'):
                self.env.add_to_compute(punches._fields[field], punches)
            punches.sl_shift_day_id._sl_audit('repair', reason, {'attendance_ids': punches.ids})
        return preview

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access('create')
        enabled = any(v.get('attendance_policy', self.env.context.get('default_attendance_policy', 'off')) == 'shift' for v in vals_list)
        if enabled and not (self.env.user.has_group('hr.group_hr_manager') and self.env.user.has_group('hr_attendance.group_hr_attendance_manager')):
            raise AccessError(_('Enabling shift integration requires HR and Attendance administrator roles.'))
        defaults = self.default_get(['shift_id'])
        shift_ids = [
            shift_id
            for vals in vals_list
            if (shift_id := vals.get('shift_id', defaults.get('shift_id')))
        ]
        shifts = self.env['sl.shift'].browse(shift_ids).exists()
        shifts.check_access('read')
        self.env['sl.shift.template.guard']._sl_lock(shifts.ids)
        records = super().create(vals_list)
        # Enabling does not silently repair historical attendance or approvals.
        return records

    def write(self, vals):
        template_guard_fields = {
            'employee_id', 'shift_id', 'date_from', 'date_to', 'active',
            'schedule_tz', 'workdays', 'break_window_set', 'break_start',
            'attendance_policy',
        }
        if template_guard_fields.intersection(vals):
            self.check_access('write')
            shift_ids = self.mapped('shift_id').ids
            if vals.get('shift_id'):
                shift_ids.append(vals['shift_id'])
            shifts = self.env['sl.shift'].browse(shift_ids).exists()
            shifts.check_access('read')
            self.env['sl.shift.template.guard']._sl_lock(shifts.ids)
        schedule_fields = {'employee_id', 'shift_id', 'date_from', 'date_to', 'schedule_tz',
                           'workdays', 'break_window_set', 'break_start', 'attendance_policy'}
        if not schedule_fields.intersection(vals) or not any(a.attendance_policy == 'shift' or vals.get('attendance_policy') == 'shift' for a in self):
            return super().write(vals)
        self._sl_config_authorize()
        evidence = self.env['sl.shift.day'].sudo().search([('assignment_id', 'in', self.ids)])
        immutable_history = {'shift_id', 'schedule_tz', 'workdays', 'break_window_set',
                             'break_start', 'attendance_policy', 'date_from'}
        if evidence and immutable_history.intersection(vals):
            raise UserError(_('A shift assignment used by attendance is historical evidence; create a new future-dated assignment instead.'))
        if evidence and 'date_to' in vals:
            cutoff = fields.Date.to_date(vals['date_to']) if vals['date_to'] else False
            latest_evidence = max(evidence.mapped('shift_date'))
            if cutoff and cutoff < latest_evidence:
                raise UserError(_('The assignment end date cannot exclude an existing shift day.'))
        if 'employee_id' in vals and any(a.employee_id.id != vals['employee_id'] for a in self):
            target = self.env['hr.employee'].browse(vals['employee_id'])
            target.check_access('read')
            if target.company_id not in self.env.companies:
                raise AccessError(_('The employee company is not enabled for this user.'))
            if evidence:
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
            for field in ('worked_hours', 'overtime_hours', 'validated_overtime_hours', 'overtime_status', 'expected_hours'):
                self.env.add_to_compute(after._fields[field], after)
            return result

    def unlink(self):
        self.check_access('unlink')
        opted_assignments = self.filtered(lambda assignment: assignment.attendance_policy == 'shift')
        if opted_assignments:
            self.env['sl.shift.template.guard']._sl_lock(opted_assignments.mapped('shift_id').ids)
            opted_assignments._sl_config_authorize()
        if self.env['sl.shift.day'].sudo().search_count([('assignment_id', 'in', self.ids)]):
            raise UserError(_('Historical assignments with shift evidence cannot be deleted.'))
        return super().unlink()


class Shift(models.Model):
    _inherit = 'sl.shift'

    def write(self, vals):
        self.check_access('write')
        self.env['sl.shift.template.guard']._sl_lock(self.ids)
        assignments = self.env['sl.shift.assignment'].sudo().with_context(active_test=False).search([
            ('shift_id', 'in', self.ids),
        ])
        opted_assignments = assignments.filtered(lambda assignment: assignment.attendance_policy == 'shift')
        if opted_assignments:
            opted_assignments.with_user(self.env.user)._sl_config_authorize()
        if {'start_time', 'end_time', 'break_minutes'}.intersection(vals) and opted_assignments:
            self.env['sl.shift.guard']._sl_lock(opted_assignments.employee_id.ids)
            if self.env['sl.shift.day'].sudo().search_count([('assignment_id', 'in', opted_assignments.ids)]):
                raise UserError(_('A shift with attendance evidence is frozen. Create a new shift and a future dated assignment.'))
        return super().write(vals)


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    sl_shift_day_id = fields.Many2one('sl.shift.day', readonly=True, copy=False, ondelete='restrict', index=True)
    sl_elapsed_hours = fields.Float(compute='_compute_sl_elapsed', string='Raw Elapsed Hours')

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

    def _get_worked_hours_in_range(self, start_dt, end_dt):
        self.ensure_one()
        assignment, window = self._sl_assignment()
        if not assignment:
            return super()._get_worked_hours_in_range(start_dt, end_dt)
        return self._sl_net_in_window(window, max(self.check_in, start_dt), min(self.check_out, end_dt))

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
            net = attendance._get_worked_hours_in_range(attendance.check_in, attendance.check_out) if attendance.check_out else 0
            overtime = max(0, consumed + net - day.expected_hours) - max(0, consumed - day.expected_hours)
            if attendance == self:
                approved = min(overtime, max(0, day.approved_overtime_hours - max(0, consumed - day.expected_hours)))
                return overtime, approved
            consumed += net
        return 0, 0

    @api.depends('check_in', 'check_out', 'employee_id', 'sl_shift_day_id.digest', 'sl_shift_day_id.approved_overtime_hours')
    def _compute_overtime_hours(self):
        managed = self.filtered(lambda a: bool(a._sl_assignment()[0]))
        super(HrAttendance, self - managed)._compute_overtime_hours()
        for attendance in managed:
            attendance.overtime_hours = attendance._sl_allocation()[0]

    @api.depends('check_in', 'check_out', 'employee_id', 'sl_shift_day_id.digest', 'sl_shift_day_id.approved_overtime_hours')
    def _compute_validated_overtime_hours(self):
        managed = self.filtered(lambda a: bool(a._sl_assignment()[0]))
        super(HrAttendance, self - managed)._compute_validated_overtime_hours()
        for attendance in managed:
            attendance.validated_overtime_hours = attendance._sl_allocation()[1]

    @api.depends('check_in', 'check_out', 'employee_id', 'sl_shift_day_id.state')
    def _compute_overtime_status(self):
        managed = self.filtered(lambda a: bool(a._sl_assignment()[0]))
        super(HrAttendance, self - managed)._compute_overtime_status()
        for attendance in managed:
            attendance.overtime_status = {'pending': 'to_approve', 'approved': 'approved', 'refused': 'refused'}.get(attendance.sl_shift_day_id.state, False)

    @api.depends('check_in', 'check_out', 'employee_id')
    def _compute_linked_overtime_ids(self):
        managed = self.filtered(lambda a: bool(a._sl_assignment()[0]))
        super(HrAttendance, self - managed)._compute_linked_overtime_ids()
        for attendance in managed:
            attendance.linked_overtime_ids = False

    def _update_overtime(self, attendance_domain=None):
        domain = attendance_domain if attendance_domain is not None else self._get_overtimes_to_update_domain()
        candidates = self | self.env['hr.attendance'].search(domain)
        managed = candidates.filtered(lambda a: bool(a._sl_assignment()[0]))
        if not managed:
            return super()._update_overtime(attendance_domain)
        excluded = Domain.OR([Domain.AND([Domain('employee_id', '=', a.employee_id.id),
                                         Domain('check_in', '=', a.check_in)]) for a in managed])
        native_domain = Domain.AND([Domain(domain), ~excluded])
        native = self - managed
        if native or self.env['hr.attendance'].search_count(native_domain):
            return super(HrAttendance, native)._update_overtime(native_domain)
        return None

    def _sl_check_protected(self, vals, employee=None, check_in=None):
        if trusted(self.env):
            return
        protected = {'sl_shift_day_id', 'sl_elapsed_hours', 'worked_hours', 'overtime_hours',
                     'validated_overtime_hours', 'overtime_status', 'expected_hours', 'linked_overtime_ids', 'date'}
        is_managed = any(bool(a._sl_assignment()[0]) or a.sl_shift_day_id for a in self)
        if employee and check_in:
            probe = self.new({'employee_id': employee.id, 'check_in': check_in})
            is_managed |= bool(probe._sl_assignment()[0])
        if ('sl_shift_day_id' in vals or 'default_sl_shift_day_id' in self.env.context
                or is_managed and (protected.intersection(vals) or any('default_' + f in self.env.context for f in protected))):
            raise AccessError(_('Managed attendance totals, approval and source links are maintained internally.'))

    def _sl_before_mutation(self, proposed=None):
        candidates = self | (proposed or self.browse())
        self.env['sl.shift.guard']._sl_lock(candidates.employee_id.ids)
        for attendance in candidates:
            if attendance.employee_id and attendance.employee_id.sudo().company_id not in self.env.companies:
                raise AccessError(_('The destination employee company is not enabled for this user.'))
        self.sl_shift_day_id._sl_assert_mutable()
        for attendance in candidates:
            assignment, window = attendance._sl_assignment()
            if assignment:
                self.env['sl.shift.day']._sl_check_mutation(attendance.employee_id, window)
                if attendance.check_out and attendance.check_out > window['next_start']:
                    raise ValidationError(_('A managed punch must not cross the next shift start.'))

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access('create')
        for vals in vals_list:
            employee = self.env['hr.employee'].browse(vals.get('employee_id') or self.env.context.get('default_employee_id') or self._default_employee().id)
            check_in = vals.get('check_in') or self.env.context.get('default_check_in') or fields.Datetime.now()
            self._sl_check_protected(vals, employee, check_in)
        with self.env.cr.savepoint():
            proposed = self.browse()
            for vals in vals_list:
                proposed |= self.new({'employee_id': vals.get('employee_id') or self.env.context.get('default_employee_id') or self._default_employee().id,
                                      'check_in': vals.get('check_in') or self.env.context.get('default_check_in') or fields.Datetime.now(),
                                      'check_out': vals.get('check_out') or self.env.context.get('default_check_out')})
            proposed._sl_before_mutation()
            records = super().create(vals_list)
            self.env['sl.shift.day']._sl_sync(records)
            return records

    def write(self, vals):
        self.check_access('write')
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
        self.check_access('unlink')
        with self.env.cr.savepoint():
            self._sl_before_mutation()
            previous = self.sl_shift_day_id
            result = super().unlink()
            self.env['sl.shift.day']._sl_sync(self.browse(), previous)
            return result


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def unlink(self):
        self.check_access('unlink')
        opted_assignments = self.env['sl.shift.assignment'].sudo().with_context(active_test=False).search([
            ('employee_id', 'in', self.ids), ('attendance_policy', '=', 'shift'),
        ])
        if opted_assignments:
            self.env['sl.shift.template.guard']._sl_lock(opted_assignments.mapped('shift_id').ids)
            opted_assignments.with_user(self.env.user)._sl_config_authorize()
            if self.env['sl.shift.day'].sudo().search_count([
                ('assignment_id', 'in', opted_assignments.ids),
            ]):
                raise UserError(_('Historical assignments with shift evidence cannot be deleted.'))
        return super().unlink()

    def write(self, vals):
        if ('company_id' in vals and any(e.company_id.id != vals['company_id'] for e in self)
                and self.env['sl.shift.day'].sudo().search_count([('employee_id', 'in', self.ids)])):
            raise UserError(_('Employee company with historical shift evidence is frozen.'))
        if 'company_id' in vals:
            changed = self.filtered(lambda employee: employee.company_id.id != vals['company_id'])
            opted_assignments = self.env['sl.shift.assignment'].sudo().with_context(active_test=False).search([
                ('employee_id', 'in', changed.ids), ('attendance_policy', '=', 'shift'),
            ])
            if opted_assignments:
                opted_assignments.with_user(self.env.user)._sl_config_authorize()
                destination = self.env['res.company'].browse(vals['company_id']).exists()
                if destination not in self.env.companies:
                    raise AccessError(_('The destination company is not enabled for this user.'))
                self.env['sl.shift.template.guard']._sl_lock(opted_assignments.mapped('shift_id').ids)
        return super().write(vals)


class NativeOvertime(models.Model):
    _inherit = 'hr.attendance.overtime.line'

    @api.model
    def _sl_managed_overtime_day(self, employee_id, work_date):
        """Whether a native employee-local day intersects an opted-in shift.

        Odoo 19 derives ``hr.attendance.date`` from ``employee._get_tz()``.
        A native overtime line's date therefore denotes that whole local civil
        day, not just an assignment's local shift-start date. Convert its
        half-open interval to UTC, then compare it with explicit assignment
        windows built in each assignment's own schedule timezone.
        """
        if not employee_id or not work_date:
            return False
        from datetime import datetime, time, timedelta
        import pytz

        work_date = fields.Date.to_date(work_date)
        employee = self.env['hr.employee'].sudo().browse(employee_id).exists()
        if not employee:
            return False
        try:
            native_zone = pytz.timezone(employee._get_tz() or 'UTC')
            native_start = native_zone.localize(datetime.combine(work_date, time.min), is_dst=None)
            native_stop = native_zone.localize(
                datetime.combine(work_date + timedelta(days=1), time.min), is_dst=None)
        except (pytz.AmbiguousTimeError, pytz.NonExistentTimeError, pytz.UnknownTimeZoneError) as error:
            raise ValidationError(_('The native overtime date has an ambiguous or nonexistent local boundary.')) from error
        native_start_utc = native_start.astimezone(pytz.utc)
        native_stop_utc = native_stop.astimezone(pytz.utc)
        native_start_utc_naive = native_start_utc.replace(tzinfo=None)
        native_stop_utc_naive = native_stop_utc.replace(tzinfo=None)

        assignments = self.env['sl.shift.assignment'].sudo().with_context(active_test=False).search([
            ('employee_id', '=', employee_id), ('attendance_policy', '=', 'shift'),
        ])
        for assignment in assignments:
            schedule_zone = pytz.timezone(assignment.schedule_tz)
            # A configured shift is shorter than 24 hours. Include the local
            # start date of every shift that could reach this native civil day;
            # timezone offsets can make that a previous calendar date.
            first_day = (native_start_utc - timedelta(days=1)).astimezone(schedule_zone).date()
            last_day = (native_stop_utc - timedelta(microseconds=1)).astimezone(schedule_zone).date()
            candidate_day = first_day
            while candidate_day <= last_day:
                window = assignment._sl_window(candidate_day)
                if (window and window['start'] < native_stop_utc_naive
                        and native_start_utc_naive < window['stop']):
                    return True
                candidate_day += timedelta(days=1)
        return False

    def _sl_reject_managed(self, vals=None):
        if trusted(self.env):
            return
        targets = []
        for line in self:
            targets.append((line.employee_id.id, line.date, line.time_start))
            if vals:
                targets.append((vals.get('employee_id', line.employee_id.id),
                                vals.get('date', line.date), vals.get('time_start', line.time_start)))
        if vals and not self:
            targets.append((vals.get('employee_id'), vals.get('date'), vals.get('time_start')))
        for employee_id, work_date, instant in targets:
            # Timed native lines are governed by their actual attendance start
            # below. The whole civil-day overlap rule is specifically for a
            # date-only adjustment, whose record has no narrower interval.
            if not instant and self._sl_managed_overtime_day(employee_id, work_date):
                raise AccessError(_('This assignment explicitly uses the custom shift engine; native overtime cannot also be created or approved.'))
            if employee_id and instant:
                probe = self.env['hr.attendance'].new({'employee_id': employee_id, 'check_in': instant})
                if probe._sl_assignment()[0]:
                    raise AccessError(_('This assignment explicitly uses the custom shift engine; native overtime cannot also be created or approved.'))

    @api.model_create_multi
    def create(self, vals_list):
        defaults = self.default_get(['employee_id', 'date', 'time_start'])
        for vals in vals_list:
            self._sl_reject_managed(dict(defaults, **vals))
        return super().create(vals_list)

    def write(self, vals):
        self._sl_reject_managed(vals)
        return super().write(vals)

    def unlink(self):
        self._sl_reject_managed()
        return super().unlink()
