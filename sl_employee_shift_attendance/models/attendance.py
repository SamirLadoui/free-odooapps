# SPDX-License-Identifier: LGPL-3.0-or-later
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from .summary import internal, trusted


class ShiftTemplateGuard(models.Model):
    _name = 'sl.shift.template.guard'
    _description = 'Shift Template and Assignment Coordination'

    shift_id = fields.Many2one('sl.shift', required=True, ondelete='cascade', index=True)
    generation = fields.Integer(default=0)

    _sql_constraints = [
        ('shift_unique', 'UNIQUE(shift_id)', 'One template coordination row per shift.'),
    ]

    @api.model
    def _sl_lock(self, shift_ids):
        # A real row update makes stale REPEATABLE READ participants serialize.
        for shift_id in sorted(set(shift_ids)):
            if not shift_id:
                continue
            self.env.cr.execute('''
                INSERT INTO sl_shift_template_guard (shift_id, generation)
                VALUES (%s, 1)
                ON CONFLICT (shift_id) DO UPDATE
                SET generation = sl_shift_template_guard.generation + 1
                RETURNING id
            ''', (shift_id,))
            self.env.cr.fetchone()

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Template coordination rows are maintained internally.'))

    def write(self, vals):
        raise AccessError(_('Template coordination rows are maintained internally.'))

    def unlink(self):
        raise AccessError(_('Template coordination rows are maintained internally.'))


class ShiftAssignment(models.Model):
    _inherit = 'sl.shift.assignment'

    attendance_policy = fields.Selection([
        ('off', 'Native (no shift integration)'),
        ('shift', 'Shift net hours — module-owned overtime'),
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
            candidates = self.filtered(lambda a: a.employee_id == attendance.employee_id)
            assignment, window = candidates._sl_resolve(attendance.employee_id, attendance.check_in) if candidates else (candidates, None)
            if assignment:
                key = (assignment.id, window['date'])
                if key not in groups:
                    groups[key] = (assignment, window, self.env['hr.attendance'])
                a, w, records = groups[key]
                groups[key] = (a, w, records | attendance)
        for assignment, window, records in groups.values():
            proposed = self.env['sl.shift.day']._sl_values(assignment, window, records)
            days = records.sl_shift_day_id
            preview.append({'attendance_ids': records.ids, 'shift_date': str(window['date']),
                            'employee_id': assignment.employee_id.id,
                            'old_net_hours': sum(records.mapped('worked_hours')),
                            'native_overtime_supported': False,
                            'old_approved_overtime': sum(days.mapped('approved_overtime_hours')),
                            'proposed_net_hours': proposed['net_hours'],
                            'proposed_regular_hours': proposed['regular_hours'],
                            'proposed_raw_overtime_hours': proposed['raw_overtime_hours'],
                            'proposed_presence_days': proposed['presence_days'],
                            'proposed_approved_overtime': sum(days.mapped('approved_overtime_hours')) if days and days.digest == proposed['digest'] else 0,
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
            for field in ('worked_hours',):
                self.env.add_to_compute(punches._fields[field], punches)
            punches.sl_shift_day_id._sl_audit('repair', reason, {'attendance_ids': punches.ids})
        return preview

    @api.model_create_multi
    def create(self, vals_list):
        enabled = any(v.get('attendance_policy', self.env.context.get('default_attendance_policy', 'off')) == 'shift' for v in vals_list)
        if enabled and not (self.env.user.has_group('hr.group_hr_manager') and self.env.user.has_group('hr_attendance.group_hr_attendance_manager')):
            raise AccessError(_('Enabling shift integration requires HR and Attendance administrator roles.'))
        defaults = self.default_get(['shift_id'])
        shift_ids = [values.get('shift_id') or defaults.get('shift_id') for values in vals_list]
        self.env['sl.shift.template.guard']._sl_lock(shift_ids)
        records = super().create(vals_list)
        # Enabling does not silently repair historical attendance or approvals.
        return records

    def write(self, vals):
        template_guard_fields = {
            'employee_id', 'shift_id', 'date_from', 'date_to', 'active',
            'attendance_policy', 'schedule_tz', 'workdays', 'break_window_set', 'break_start',
        }
        if template_guard_fields.intersection(vals):
            shift_ids = self.mapped('shift_id').ids
            if vals.get('shift_id'):
                shift_ids.append(vals['shift_id'])
            self.env['sl.shift.template.guard']._sl_lock(shift_ids)
        if vals.get('attendance_policy') == 'off' and self.env['sl.shift.day'].sudo().search_count([
                ('assignment_id', 'in', self.ids)]):
            raise UserError(_('A historical shift assignment cannot be disabled after attendance evidence exists.'))
        schedule_fields = {'employee_id', 'shift_id', 'date_from', 'date_to', 'schedule_tz',
                           'workdays', 'break_window_set', 'break_start', 'attendance_policy'}
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
            for field in ('worked_hours',):
                self.env.add_to_compute(after._fields[field], after)
            return result

    def unlink(self):
        if not self:
            return super().unlink()
        # Preserve the native assignment ACL/record-rule decision before any
        # privileged inspection or coordination-row mutation.
        self.check_access_rights('unlink')
        self.check_access_rule('unlink')
        with self.env.cr.savepoint():
            self.env['sl.shift.template.guard']._sl_lock(self.mapped('shift_id').ids)
            self.env['sl.shift.guard']._sl_lock(self.mapped('employee_id').ids)
            assignments = self.env['sl.shift.assignment'].sudo().with_context(
                active_test=False).search([('id', 'in', self.ids)])
            if self.env['sl.shift.day'].sudo().search_count([
                    ('assignment_id', 'in', assignments.ids)]):
                raise UserError(_('Historical assignments with shift evidence cannot be deleted.'))
            opted = assignments.filtered(lambda assignment: assignment.attendance_policy == 'shift')
            if opted and not (
                    self.env.user.has_group('hr.group_hr_manager')
                    and self.env.user.has_group('hr_attendance.group_hr_attendance_manager')):
                raise AccessError(_('Shift attendance configuration requires HR and Attendance administrator roles.'))
            return super().unlink()


class Shift(models.Model):
    _inherit = 'sl.shift'

    def write(self, vals):
        self.check_access_rights('write')
        self.check_access_rule('write')
        # Assignment mutations use this key too; update it before searching so
        # a stale repeatable-read snapshot cannot miss a concurrent opt-in.
        self.env['sl.shift.template.guard']._sl_lock(self.ids)
        assignments = self.env['sl.shift.assignment'].sudo().with_context(active_test=False).search([
            ('shift_id', 'in', self.ids),
        ])
        opted_assignments = assignments.filtered(lambda assignment: assignment.attendance_policy == 'shift')
        if opted_assignments and not (
                self.env.user.has_group('hr.group_hr_manager')
                and self.env.user.has_group('hr_attendance.group_hr_attendance_manager')):
            raise AccessError(_('Shift attendance configuration requires HR and Attendance administrator roles.'))
        if {'start_time', 'end_time', 'break_minutes'}.intersection(vals) and assignments:
            self.env['sl.shift.guard']._sl_lock(assignments.employee_id.ids)
            if self.env['sl.shift.day'].sudo().search_count([
                    ('assignment_id', 'in', assignments.ids)]):
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

    @api.depends('check_in', 'check_out', 'employee_id', 'sl_shift_day_id.digest')
    def _compute_worked_hours(self):
        # Native 14 has only raw elapsed worked_hours; it has no lunch/OT engine.
        super()._compute_worked_hours()
        for attendance in self:
            assignment, window = attendance._sl_assignment()
            if assignment and attendance.check_in and attendance.check_out:
                attendance.worked_hours = attendance._sl_net_in_window(window, attendance.check_in, attendance.check_out)

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

    sl_regular_hours = fields.Float(compute='_compute_sl_quantities', string='Shift Regular Hours')
    sl_raw_overtime_hours = fields.Float(compute='_compute_sl_quantities', string='Shift Raw Overtime (Module-owned)')
    sl_approved_overtime_hours = fields.Float(compute='_compute_sl_quantities', string='Shift Approved Overtime (Module-owned)')

    @api.depends('check_in', 'check_out', 'employee_id', 'sl_shift_day_id.digest',
                 'sl_shift_day_id.approved_overtime_hours', 'sl_shift_day_id.state')
    def _compute_sl_quantities(self):
        for attendance in self:
            raw, approved = attendance._sl_allocation()
            attendance.sl_raw_overtime_hours = raw
            attendance.sl_approved_overtime_hours = approved
            attendance.sl_regular_hours = max(0, attendance.worked_hours - raw) if attendance.sl_shift_day_id and attendance.sl_shift_day_id.state not in ('open', 'void') else 0

    def _sl_check_protected(self, vals, employee=None, check_in=None):
        if trusted(self.env):
            return
        protected = {'sl_shift_day_id', 'sl_elapsed_hours', 'worked_hours', 'sl_regular_hours',
                     'sl_raw_overtime_hours', 'sl_approved_overtime_hours'}
        is_managed = any(bool(a._sl_assignment()[0]) or a.sl_shift_day_id for a in self)
        if employee and check_in:
            probe = self.new({'employee_id': employee.id, 'check_in': check_in})
            is_managed |= bool(probe._sl_assignment()[0])
        if ('sl_shift_day_id' in vals or 'default_sl_shift_day_id' in self.env.context
                or is_managed and (protected.intersection(vals) or any('default_' + f in self.env.context for f in protected))):
            raise AccessError(_('Managed attendance totals, approval and source links are maintained internally.'))

    def _sl_authorize_employee(self, employee):
        # Native record rules authorize the old row before write. Validate the
        # destination as well, without granting new native attendance ACLs.
        if not employee.exists() or employee.sudo().company_id not in self.env.companies:
            raise AccessError(_('The employee company is not enabled.'))
        if not self.env.su and not self.env.user.has_group('hr_attendance.group_hr_attendance_user') and employee.sudo().user_id != self.env.user:
            raise AccessError(_('Only an Attendance Officer can change another employee attendance.'))

    def _sl_before_mutation(self, proposed=None):
        candidates = self | (proposed or self.browse())
        for attendance in candidates:
            self._sl_authorize_employee(attendance.employee_id)
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
        self.check_access_rule('create')
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

    def unlink(self):
        if not self:
            return super().unlink()
        # Keep native employee deletion authorization ahead of coordination or
        # privileged assignment inspection.
        self.check_access_rights('unlink')
        self.check_access_rule('unlink')
        employee_ids = self.ids
        assignment_model = self.env['sl.shift.assignment']
        assignment_model.flush(['employee_id', 'shift_id', 'attendance_policy'])
        # This key-only SQL pass includes archived rows. The authoritative ORM
        # search and all history/opt-in checks happen after the shared template
        # guard and employee coordination rows have been updated.
        self.env.cr.execute(
            'SELECT DISTINCT shift_id FROM sl_shift_assignment '
            'WHERE employee_id = ANY(%s) ORDER BY shift_id',
            (employee_ids,),
        )
        shift_ids = [row[0] for row in self.env.cr.fetchall()]
        with self.env.cr.savepoint():
            self.env['sl.shift.template.guard']._sl_lock(shift_ids)
            self.env['sl.shift.guard']._sl_lock(employee_ids)
            assignments = assignment_model.sudo().with_context(active_test=False).search([
                ('employee_id', 'in', employee_ids),
            ])
            if self.env['sl.shift.day'].sudo().search_count([
                    ('assignment_id', 'in', assignments.ids)]):
                raise UserError(_('Historical assignments with shift evidence cannot be deleted.'))
            opted = assignments.filtered(lambda assignment: assignment.attendance_policy == 'shift')
            if opted and not (
                    self.env.user.has_group('hr.group_hr_manager')
                    and self.env.user.has_group('hr_attendance.group_hr_attendance_manager')):
                raise AccessError(_('Shift attendance configuration requires HR and Attendance administrator roles.'))
            return super().unlink()
