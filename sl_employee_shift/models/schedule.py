# SPDX-License-Identifier: LGPL-3.0-or-later
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class ShiftAssignment(models.Model):
    _inherit = 'sl.shift.assignment'

    company_id = fields.Many2one(related='employee_id.company_id', store=True, index=True)
    schedule_tz = fields.Selection([(tz, tz) for tz in pytz.all_timezones],
                                   default='UTC', required=True, string='Schedule Timezone')
    workdays = fields.Char(default='0,1,2,3,4', required=True,
                          help='Shift-start weekdays: Monday=0 through Sunday=6, comma separated.')
    break_window_set = fields.Boolean(string='Explicit Break Window Confirmed')
    break_start = fields.Float(string='Break Starts At', default=0,
                              help='Local clock hour; before shift start means the following day.')

    @api.constrains('workdays', 'break_start', 'break_window_set', 'shift_id')
    def _sl_check_schedule(self):
        for assignment in self:
            days = assignment.workdays.split(',')
            if not days or any(day not in tuple(str(i) for i in range(7)) for day in days) or len(set(days)) != len(days):
                raise ValidationError(_('Use distinct weekday numbers 0 through 6, separated by commas.'))
            if not 0 <= assignment.break_start < 24:
                raise ValidationError(_('Break start must be between 0 and 24.'))
            if assignment.break_window_set and assignment.shift_id.break_minutes:
                assignment._sl_window(fields.Date.to_date('2026-01-05'), check_workday=False)

    def _sl_window(self, day, check_workday=True):
        """One logical shift, UTC datetimes; presence belongs to local start day.

        Ambiguous/nonexistent DST clock times are rejected instead of guessed.
        Archived assignments still describe history; active is a UI filter only.
        """
        self.ensure_one()
        day = fields.Date.to_date(day)
        if check_workday and (day < self.date_from or (self.date_to and day > self.date_to)
                              or str(day.weekday()) not in self.workdays.split(',')):
            return None
        zone = pytz.timezone(self.schedule_tz)
        shift = self.shift_id
        def clock(hour, next_day=False):
            naive = datetime.combine(day + timedelta(days=int(next_day)), time.min) + timedelta(hours=hour)
            try:
                return zone.localize(naive, is_dst=None).astimezone(pytz.utc).replace(tzinfo=None)
            except (pytz.AmbiguousTimeError, pytz.NonExistentTimeError) as error:
                raise ValidationError(_('The schedule contains an ambiguous or nonexistent local time.')) from error
        start = clock(shift.start_time)
        stop = clock(shift.end_time, shift.end_time < shift.start_time)
        next_start = clock(shift.start_time, True)
        break_start = break_stop = None
        if shift.break_minutes:
            if not self.break_window_set:
                raise ValidationError(_('Confirm an explicit unpaid break window before enabling integration.'))
            break_start = clock(self.break_start, self.break_start < shift.start_time)
            break_stop = break_start + timedelta(minutes=shift.break_minutes)
            if not start <= break_start < break_stop <= stop:
                raise ValidationError(_('The explicit unpaid break must be wholly inside the shift.'))
        expected = (stop - start).total_seconds() / 3600 - shift.break_minutes / 60
        return {'date': day, 'start': start, 'stop': stop, 'next_start': next_start,
                'break_start': break_start, 'break_stop': break_stop, 'expected': expected}

    @api.model
    def _sl_resolve(self, employee, instant):
        """Resolve by historical shift start, never by today's current_shift_id."""
        instant = fields.Datetime.to_datetime(instant)
        found = []
        candidates = self if self else self.with_context(active_test=False).search([('employee_id', '=', employee.id)])
        for assignment in candidates:
            local_day = pytz.utc.localize(instant).astimezone(pytz.timezone(assignment.schedule_tz)).date()
            for day in (local_day - timedelta(days=1), local_day):
                # Avoid demanding a break window for unrelated historical dates.
                if day < assignment.date_from or (assignment.date_to and day > assignment.date_to):
                    continue
                window = assignment._sl_window(day)
                if window and window['start'] <= instant < window['next_start']:
                    found.append((assignment, window))
        if len(found) > 1:
            raise ValidationError(_('Ambiguous historical shift assignment.'))
        return found[0] if found else (self.browse(), None)

    def _sl_check_assignment_overlap(self, candidates, exclude_ids=None):
        assignment_model = self.sudo().with_context(active_test=False)
        exclude_ids = set(exclude_ids or [])
        checked = []
        max_date = '9999-12-31'
        for values in candidates:
            employee_id = values.get('employee_id')
            date_from = fields.Date.to_date(values.get('date_from'))
            date_to = fields.Date.to_date(values.get('date_to')) if values.get('date_to') else None
            if not employee_id or not date_from:
                continue
            domain = [
                ('employee_id', '=', employee_id),
                ('date_from', '<=', fields.Date.to_string(date_to) if date_to else max_date),
                '|', ('date_to', '=', False),
                     ('date_to', '>=', fields.Date.to_string(date_from)),
            ]
            if exclude_ids:
                domain.append(('id', 'not in', list(exclude_ids)))
            if assignment_model.search(domain, limit=1):
                raise ValidationError(_('An employee cannot have overlapping historical shift assignments.'))
            for previous_employee, previous_from, previous_to in checked:
                if (employee_id == previous_employee
                        and (not previous_to or previous_to >= date_from)
                        and (not date_to or date_to >= previous_from)):
                    raise ValidationError(_('An employee cannot have overlapping historical shift assignments.'))
            checked.append((employee_id, date_from, date_to))

    @api.model_create_multi
    def create(self, vals_list):
        defaults = self.default_get(['employee_id', 'date_from', 'date_to'])
        candidates = [dict(defaults, **values) for values in vals_list]
        for values in vals_list:
            if 'company_id' in values or 'default_company_id' in self.env.context:
                raise AccessError(_('Assignment company is derived from the employee.'))
            employee = self.env['hr.employee'].browse(
                values.get('employee_id') or self.env.context.get('default_employee_id'))
            employee.check_access_rights('read')
            employee.check_access_rule('read')
            if employee.company_id not in self.env.companies:
                raise AccessError(_('The employee company is not enabled for this user.'))
        with self.env.cr.savepoint():
            self.env['sl.shift.guard']._sl_lock(
                [values.get('employee_id') for values in candidates if values.get('employee_id')])
            self._sl_check_assignment_overlap(candidates)
            return super().create(vals_list)

    def write(self, vals):
        if 'employee_id' in vals:
            employee = self.env['hr.employee'].browse(vals['employee_id'])
            employee.check_access_rights('read')
            employee.check_access_rule('read')
            if employee.company_id not in self.env.companies:
                raise AccessError(_('The employee company is not enabled for this user.'))
        if 'company_id' in vals or 'default_company_id' in self.env.context:
            raise AccessError(_('Assignment company is derived from the employee.'))
        overlap_fields = {'employee_id', 'date_from', 'date_to', 'active', 'attendance_policy'}
        if overlap_fields.intersection(vals):
            self.check_access_rights('write')
            self.check_access_rule('write')
            target_employee = vals.get('employee_id')
            employee_ids = self.employee_id.ids + ([target_employee] if target_employee else [])
            candidates = [{
                'employee_id': target_employee or assignment.employee_id.id,
                'date_from': vals.get('date_from', assignment.date_from),
                'date_to': vals.get('date_to', assignment.date_to),
            } for assignment in self]
            with self.env.cr.savepoint():
                self.env['sl.shift.guard']._sl_lock(employee_ids)
                self._sl_check_assignment_overlap(candidates, exclude_ids=self.ids)
        return super().write(vals)
