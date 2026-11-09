# SPDX-License-Identifier: LGPL-3.0-or-later
"""Odoo 18 contract/net-interval work-entry bridge. No salary rules or statutory rates."""
from datetime import datetime, time, timedelta
import json

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.sl_employee_shift_attendance.models.summary import (
    _filter_read_relations,
    internal,
    trusted,
)

_SOURCE = 'sl_shift_manual'


def _sl_lock_shift_owners(env, employee_ids):
    employee_ids = set(employee_ids)
    if not employee_ids:
        return
    assignments = env['sl.shift.assignment'].sudo().with_context(active_test=False).search([
        ('employee_id', 'in', list(employee_ids)),
        ('attendance_policy', '=', 'shift'),
        ('work_entry_enabled', '=', True),
    ])
    if assignments:
        env['sl.shift.guard']._sl_lock(assignments.employee_id.ids)


class ShiftAssignment(models.Model):
    _inherit = 'sl.shift.assignment'

    work_entry_enabled = fields.Boolean(default=False, string='Enable Manual Shift Work Entries')
    regular_type_id = fields.Many2one('hr.work.entry.type', string='Regular Work Entry Type')
    overtime_type_id = fields.Many2one('hr.work.entry.type', string='Approved Overtime Work Entry Type')

    @api.constrains('work_entry_enabled', 'attendance_policy', 'regular_type_id', 'overtime_type_id')
    def _sl_check_mapping(self):
        for assignment in self.filtered('work_entry_enabled'):
            if assignment.attendance_policy != 'shift':
                raise ValidationError(_('Manual shift work entries require the custom authoritative attendance engine.'))
            types = assignment.regular_type_id | assignment.overtime_type_id
            if len(types) != 2 or any(t.is_leave for t in types):
                raise ValidationError(_('Select two distinct non-leave work entry types explicitly.'))
            if any(t.country_id and t.country_id != assignment.company_id.country_id for t in types):
                raise ValidationError(_('Work entry type country must match the assignment company.'))

    def action_repair_attendance(self, dry_run=True, reason=None):
        self._sl_config_authorize()
        entries = self.env['hr.work.entry'].search([
            ('employee_id', 'in', self.employee_id.ids),
            ('date_stop', '>=', datetime.combine(min(self.mapped('date_from')), time.min) - timedelta(days=1)),
        ]) if self else self.env['hr.work.entry']
        before = entries.read(['employee_id', 'date_start', 'date_stop', 'duration', 'work_entry_type_id', 'state', 'sl_shift_day_id'])
        preview = super().action_repair_attendance(dry_run=dry_run, reason=reason)
        for row in preview:
            day = fields.Date.to_date(row['shift_date'])
            assignment = self.filtered(lambda a: a.employee_id.id == row['employee_id'] and a.date_from <= day and (not a.date_to or a.date_to >= day))
            window = assignment._sl_window(day, check_workday=False)
            matching = [e for e in before if e['employee_id'][0] == row['employee_id']
                        and e['date_start'] < window['next_start'] and e['date_stop'] > window['start']]
            row['existing_work_entries'] = matching
            row['finalized_work_entries_block_repair'] = any(e['state'] == 'validated' for e in matching)
            row['work_entry_action'] = 'Separate explicit generation; never export unapproved raw overtime.'
        return preview

    @api.model_create_multi
    def create(self, vals_list):
        enabled = any(v.get('work_entry_enabled', self.env.context.get('default_work_entry_enabled')) for v in vals_list)
        if enabled and not (self.env.user.has_group('hr.group_hr_manager') and self.env.user.has_group('hr_attendance.group_hr_attendance_manager')):
            raise AccessError(_('Work-entry integration requires HR and Attendance administrator roles.'))
        return super().create(vals_list)

    def write(self, vals):
        if {'work_entry_enabled', 'regular_type_id', 'overtime_type_id'}.intersection(vals):
            self._sl_config_authorize()
            self.env['sl.shift.guard']._sl_lock(self.employee_id.ids)
            entries = self.env['hr.work.entry'].sudo().with_context(active_test=False).search([
                ('sl_shift_day_id.assignment_id', 'in', self.ids),
            ])
            if entries:
                raise UserError(_('Work-entry mapping is frozen once used. Create a new dated assignment for future changes.'))
        return super().write(vals)


class HrContract(models.Model):
    _inherit = 'hr.contract'

    work_entry_source = fields.Selection(selection_add=[(_SOURCE, 'Shift Summary (Explicit Manual Generation)')],
                                         ondelete={_SOURCE: 'set default'})

    def _generate_work_entries(self, date_start, date_stop, force=False):
        native = self.filtered(lambda contract: contract.work_entry_source != _SOURCE)
        return super(HrContract, native)._generate_work_entries(date_start, date_stop, force=force) if native else self.env['hr.work.entry']

    def _get_work_entries_values(self, date_start, date_stop):
        native = self.filtered(lambda contract: contract.work_entry_source != _SOURCE)
        return super(HrContract, native)._get_work_entries_values(date_start, date_stop) if native else []

    def _get_contract_work_entries_values(self, date_start, date_stop):
        native = self.filtered(lambda contract: contract.work_entry_source != _SOURCE)
        return super(HrContract, native)._get_contract_work_entries_values(date_start, date_stop) if native else []

    def _sl_update_generation_coverage(self, first, last):
        """Update only native generation coverage from the guarded generator."""
        if not trusted(self.env):
            raise AccessError(_('Generation coverage is maintained internally.'))
        self.ensure_one()
        if not first or not last or first > last:
            raise ValidationError(_('Generation coverage must be a non-empty ordered interval.'))
        empty = self.date_generated_from == self.date_generated_to
        values = {
            'date_generated_from': first if empty else min(first, self.date_generated_from),
            'date_generated_to': last if empty else max(last, self.date_generated_to),
            'last_generation_date': fields.Date.today(),
        }
        return self.sudo().write(values)

    def write(self, vals):
        self.check_access('write')
        protected = {'work_entry_source', 'employee_id', 'company_id', 'date_start', 'date_end', 'resource_calendar_id', 'state', 'active'}
        if protected.intersection(vals):
            self.env['sl.shift.guard']._sl_lock(self.employee_id.ids)
            entries = self.env['hr.work.entry'].sudo().with_context(active_test=False).search([
                ('contract_id', 'in', self.ids), ('sl_shift_day_id', '!=', False),
            ])
            if entries:
                raise UserError(_('Contract source, dates and ownership used by shift evidence are frozen. Use a new dated contract for future changes.'))
            if vals.get('work_entry_source') == _SOURCE and any(contract.work_entry_source != _SOURCE for contract in self):
                # Native source changes can invoke the broad regeneration wizard.
                # Refuse adoption rather than archive another source's entries.
                if self.env['hr.work.entry'].sudo().with_context(active_test=False).search_count([
                    ('employee_id', 'in', self.employee_id.ids),
                ]):
                    raise UserError(_('Existing native work entries must be reconciled explicitly before selecting the manual shift source; none were archived.'))
        with self.env.cr.savepoint():
            return super().write(vals)

    def unlink(self):
        if self.env['hr.work.entry'].sudo().with_context(active_test=False).search_count([
            ('contract_id', 'in', self.ids), ('sl_shift_day_id', '!=', False),
        ]):
            raise UserError(_('Contracts used by shift evidence cannot be deleted.'))
        return super().unlink()


class ShiftDay(models.Model):
    _inherit = 'sl.shift.day'

    work_entry_ids = fields.One2many(
        'hr.work.entry', 'sl_shift_day_id', readonly=True,
        groups='hr.group_hr_user',
    )
    can_generate_work_entries = fields.Boolean(compute='_compute_can_generate_work_entries')

    @api.depends_context('uid')
    def _compute_can_generate_work_entries(self):
        allowed = (self.env.user.has_group('hr.group_hr_manager')
                   and self.env.user.has_group('sl_employee_shift_attendance.group_shift_approver'))
        for day in self:
            day.can_generate_work_entries = allowed

    def _read_format(self, fnames, load='_classic_read'):
        rows = super()._read_format(fnames=fnames, load=load)
        return _filter_read_relations(
            self, rows, fnames, {'work_entry_ids': ('hr.work.entry', 'sl_shift_day_id')},
        )

    @api.model
    def _sl_assert_period_mutable(self, employee, start, stop):
        finalized = self.env['hr.work.entry'].sudo().with_context(active_test=False).search_count([
            ('employee_id', '=', employee.id), ('date_start', '<', stop), ('date_stop', '>', start), ('state', '=', 'validated'),
        ])
        if finalized:
            raise UserError(_('This shift touches finalized native work entries. Use an authorized adjustment outside the closed period.'))
        if 'hr.payslip' in self.env.registry:
            payslips = self.env['hr.payslip'].sudo().search_count([
                ('employee_id', '=', employee.id), ('date_from', '<=', stop.date()), ('date_to', '>=', start.date()),
                ('state', 'in', ['done', 'paid']),
            ])
            if payslips:
                raise UserError(_('A finalized or paid payslip overlaps this shift. No automatic repair is permitted.'))

    def _sl_assert_mutable(self):
        for day in self:
            window = day.assignment_id._sl_window(day.shift_date, check_workday=False)
            self._sl_assert_period_mutable(day.employee_id, window['start'], window['next_start'])
        return super()._sl_assert_mutable()

    @api.model
    def _sl_check_mutation(self, employee, window):
        self._sl_assert_period_mutable(employee, window['start'], window['next_start'])
        return super()._sl_check_mutation(employee, window)

    def _sl_sources_changed(self):
        self._sl_assert_mutable()
        entries = self.sudo().work_entry_ids
        if entries:
            internal(entries).unlink()
        return super()._sl_sources_changed()

    def _sl_decision_changed(self):
        self._sl_sources_changed()
        return super()._sl_decision_changed()

    def _sl_assert_current(self):
        for day in self:
            window = day.assignment_id._sl_window(day.shift_date)
            if not window or day.assignment_id.attendance_policy != 'shift':
                raise UserError(_('The historical assignment changed. Run the guarded repair first.'))
            current = self.env['sl.shift.day']._sl_values(
                day.assignment_id, window, day.sudo().attendance_ids,
            )
            if current['digest'] != day.digest:
                raise UserError(_('Source punches changed. Run the guarded repair and obtain approval again.'))

    def _sl_entry_payload(self):
        """Real local-date hour allocation, separate from shift-start presence."""
        self.ensure_one()
        assignment = self.assignment_id
        if not assignment.work_entry_enabled:
            raise UserError(_('Enable manual work entries and explicitly map the two types on this assignment.'))
        assignment._sl_check_mapping()
        if self.state in ('open', 'void'):
            raise UserError(_('An incomplete or empty shift cannot generate work entries.'))
        zone = pytz.timezone(assignment.schedule_tz)
        window = assignment._sl_window(self.shift_date)
        if not window:
            raise UserError(_('The shift is no longer an eligible scheduled workday.'))
        # Leave/holiday classification belongs to the payroll provider. Calendar
        # intervals are checked above in UTC; request dates are only civil-day labels.
        # Refuse ambiguous overlaps instead of silently replacing native leave entries.
        leaves = self.env['resource.calendar.leaves'].sudo().search_count([
            ('resource_id', 'in', [False, self.employee_id.resource_id.id]),
            ('company_id', 'in', [False, self.company_id.id]),
            ('calendar_id', 'in', [False, self.employee_id.resource_calendar_id.id]),
            ('time_type', '=', 'leave'),
            ('date_from', '<', window['next_start']), ('date_to', '>', window['start']),
        ])
        if leaves:
            raise UserError(_('A leave or public holiday overlaps this duty window. Resolve its provider-specific classification before generation.'))
        segments = []
        remaining_regular = self.regular_hours
        remaining_overtime = self.approved_overtime_hours if self.state == 'approved' else 0
        for attendance in self.sudo().attendance_ids.sorted(lambda a: (a.check_in, a.id)):
            start, stop = attendance.check_in, attendance.check_out
            intervals = [(start, stop)]
            if window['break_start']:
                intervals = [(start, min(stop, window['break_start'])), (max(start, window['break_stop']), stop)]
            for begin, end in intervals:
                if begin >= end:
                    continue
                instant = begin
                for kind in ('regular', 'overtime'):
                    remaining = remaining_regular if kind == 'regular' else remaining_overtime
                    duration = min(remaining, (end - instant).total_seconds() / 3600)
                    if duration <= 0:
                        continue
                    segment_end = instant + timedelta(hours=duration)
                    while instant < segment_end:
                        local = pytz.utc.localize(instant).astimezone(zone)
                        midnight = zone.localize(datetime.combine(local.date() + timedelta(days=1), time.min), is_dst=None).astimezone(pytz.utc).replace(tzinfo=None)
                        boundary = min(segment_end, midnight)
                        segments.append((instant, boundary, local.date(), kind))
                        instant = boundary
                    if kind == 'regular':
                        remaining_regular -= duration
                    else:
                        remaining_overtime -= duration
        values = []
        for begin, end, work_date, kind in segments:
            contracts = self.env['hr.contract'].sudo().search([
                ('employee_id', '=', self.employee_id.id), ('company_id', '=', self.company_id.id),
                ('date_start', '<=', work_date), '|', ('date_end', '=', False), ('date_end', '>=', work_date),
                ('state', 'in', ['open', 'close']),
            ])
            if len(contracts) != 1 or contracts.work_entry_source != _SOURCE:
                raise UserError(_('Each historical work date requires exactly one same-company open/closed contract explicitly using Shift Summary (Explicit Manual Generation).'))
            entry_type = assignment.regular_type_id if kind == 'regular' else assignment.overtime_type_id
            values.append({'name': '%s / %s / %s' % (self.employee_id.name, self.shift_date, kind),
                           'employee_id': self.employee_id.id, 'contract_id': contracts.id, 'company_id': self.company_id.id,
                           'date_start': begin, 'date_stop': end, 'duration': (end - begin).total_seconds() / 3600,
                           'work_entry_type_id': entry_type.id, 'state': 'draft', 'active': True,
                           'sl_shift_day_id': self.id, 'sl_shift_kind': kind, 'sl_shift_digest': self.digest})
        return values

    def action_generate_and_open_work_entries(self):
        entries = self.action_generate_work_entries()
        return {'type': 'ir.actions.act_window', 'name': _('Shift Work Entries'),
                'res_model': 'hr.work.entry', 'view_mode': 'list,form',
                'domain': [('id', 'in', entries.ids)]}

    def action_generate_work_entries(self):
        if not (self.env.user.has_group('hr.group_hr_manager')
                and self.env.user.has_group('sl_employee_shift_attendance.group_shift_approver')):
            raise AccessError(_('Manual generation requires HR administrator and Shift Overtime Approver roles.'))
        self.check_access('read')
        if any(day.company_id not in self.env.companies for day in self):
            raise AccessError(_('The summary company is not enabled.'))
        with self.env.cr.savepoint():
            self.env['sl.shift.guard']._sl_lock(self.employee_id.ids)
            self.invalidate_recordset()
            self._sl_assert_current()
            result = self.env['hr.work.entry']
            for day in self:
                payload = day._sl_entry_payload()
                existing = day.sudo().with_context(active_test=False).work_entry_ids
                compare = ['employee_id', 'contract_id', 'company_id', 'date_start', 'date_stop', 'duration', 'work_entry_type_id',
                           'sl_shift_day_id', 'sl_shift_kind', 'sl_shift_digest', 'active']
                def normalized(values):
                    return sorted([json.dumps({k: (str(v) if k in ('date_start', 'date_stop') else round(v, 8) if isinstance(v, float) else v)
                                               for k, v in row.items() if k in compare}, sort_keys=True) for row in values])
                stored = []
                for entry in existing:
                    stored.append({k: entry[k].id if entry._fields[k].type == 'many2one' else entry[k] for k in compare})
                if existing and normalized(stored) == normalized(payload):
                    result |= existing
                    continue
                day._sl_assert_mutable()
                if payload:
                    foreign = self.env['hr.work.entry'].sudo().search_count([
                        ('employee_id', '=', day.employee_id.id),
                        ('date_start', '<', max(v['date_stop'] for v in payload)),
                        ('date_stop', '>', min(v['date_start'] for v in payload)),
                        ('state', '!=', 'cancelled'), ('sl_shift_day_id', '=', False),
                    ])
                    if foreign:
                        raise UserError(_('Other native work entries already overlap this shift. Dry-run and reconcile their source; no entries were deleted.'))
                if existing:
                    internal(existing).unlink()
                if payload:
                    generated = internal(self.env['hr.work.entry']).create(payload)
                    result |= generated
                    # Keep the native generation coverage truthful for the
                    # explicit manual source without invoking its broad wizard.
                    # The authorized action supplies only server-derived bounds;
                    # it does not grant the caller general contract write rights.
                    for contract in internal(generated.sudo()).contract_id:
                        rows = generated.filtered(lambda entry, contract=contract: entry.contract_id == contract)
                        first, last = min(rows.mapped('date_start')), max(rows.mapped('date_stop'))
                        contract._sl_update_generation_coverage(first, last)
                    day._sl_audit('work_entries_generated', 'Explicit provider-neutral manual generation.',
                                  {'digest': day.digest, 'entry_ids': generated.ids,
                                   'regular_hours': day.regular_hours, 'approved_overtime_hours': day.approved_overtime_hours})
            return result


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    def _sl_assert_no_manual_shift_entries(self, proposed_values=None):
        for original in self:
            leave = original
            if proposed_values is not None:
                values = dict(proposed_values)
                if 'date_from' in values:
                    values['request_date_from'] = values['date_from']
                if 'date_to' in values:
                    values['request_date_to'] = values['date_to']
                leave = self.env['hr.leave'].new(values, origin=original)
                leave._compute_date_from_to()
            if (not leave.employee_id or not leave.date_from or not leave.date_to
                    or leave.holiday_status_id.time_type != 'leave'):
                continue
            entries = self.env['hr.work.entry'].sudo().with_context(active_test=False).search([
                ('employee_id', '=', leave.employee_id.id),
                ('sl_shift_day_id', '!=', False),
                ('date_start', '<', leave.date_to),
                ('date_stop', '>', leave.date_from),
                ('state', '!=', 'cancelled'),
            ], limit=1)
            if entries:
                raise UserError(_(
                    'This leave overlaps a shift day with manual work entries. '
                    'Resolve the shift entries before approving the leave.'))

    @api.model_create_multi
    def create(self, vals_list):
        with self.env.cr.savepoint():
            defaults = self.default_get(['employee_id'])
            _sl_lock_shift_owners(self.env, [
                values.get('employee_id', defaults.get('employee_id'))
                for values in vals_list
            ])
            leaves = super().create(vals_list)
            leaves.filtered(lambda leave: leave.state == 'validate')._sl_assert_no_manual_shift_entries()
        return leaves

    def write(self, vals):
        employee_ids = self.employee_id.ids
        if vals.get('employee_id'):
            employee_ids.append(vals['employee_id'])
        with self.env.cr.savepoint():
            _sl_lock_shift_owners(self.env, employee_ids)
            if vals.get('state') == 'validate' and any(leave.state != 'validate' for leave in self):
                self._sl_assert_no_manual_shift_entries(proposed_values=vals)
            return super().write(vals)

    def unlink(self):
        with self.env.cr.savepoint():
            _sl_lock_shift_owners(self.env, self.employee_id.ids)
            return super().unlink()

    def _validate_leave_request(self):
        _sl_lock_shift_owners(self.env, self.employee_id.ids)
        self._sl_assert_no_manual_shift_entries()
        return super()._validate_leave_request()


class ResourceCalendarLeaves(models.Model):
    _inherit = 'resource.calendar.leaves'

    def _sl_employee_ids_for_values(self, values):
        if values.get('time_type', 'leave') != 'leave':
            return []
        employee_ids = set()
        holiday_id = values.get('holiday_id')
        if holiday_id:
            holiday = self.env['hr.leave'].sudo().browse(holiday_id)
            employee_ids.update(holiday.employee_id.ids)
        resource_id = values.get('resource_id')
        if resource_id:
            employee_ids.update(self.env['hr.employee'].sudo().with_context(active_test=False).search([
                ('resource_id', '=', resource_id),
            ]).ids)
        else:
            domain = []
            if values.get('company_id'):
                domain.append(('company_id', '=', values['company_id']))
            if values.get('calendar_id'):
                domain.append(('resource_calendar_id', '=', values['calendar_id']))
            employee_ids.update(self.env['hr.employee'].sudo().with_context(active_test=False).search(domain).ids)
        return employee_ids

    def _sl_lock_affected_employees(self, vals=None, vals_list=None):
        employee_ids = set()
        for leave in self:
            old_values = {
                'time_type': leave.time_type,
                'holiday_id': leave.holiday_id.id,
                'resource_id': leave.resource_id.id,
                'calendar_id': leave.calendar_id.id,
                'company_id': leave.company_id.id,
            }
            employee_ids.update(self._sl_employee_ids_for_values(old_values))
            if vals:
                new_values = dict(old_values, **vals)
                employee_ids.update(self._sl_employee_ids_for_values(new_values))
        for values in vals_list or []:
            employee_ids.update(self._sl_employee_ids_for_values(values))
        _sl_lock_shift_owners(self.env, employee_ids)

    def _sl_assert_no_shift_entries(self):
        WorkEntry = self.env['hr.work.entry'].sudo().with_context(active_test=False)
        Employee = self.env['hr.employee'].sudo().with_context(active_test=False)
        for leave in self.filtered(lambda record: record.time_type == 'leave'):
            holiday = leave.holiday_id if 'holiday_id' in leave._fields else self.env['hr.leave']
            if holiday and holiday.employee_id:
                holiday._sl_assert_no_manual_shift_entries()
                continue

            domain = []
            if leave.resource_id:
                domain.append(('resource_id', '=', leave.resource_id.id))
            else:
                if leave.company_id:
                    domain.append(('company_id', '=', leave.company_id.id))
                if leave.calendar_id:
                    domain.append(('resource_calendar_id', '=', leave.calendar_id.id))
            employees = Employee.search(domain)
            if not employees:
                continue
            conflict = WorkEntry.search([
                ('employee_id', 'in', employees.ids),
                ('sl_shift_day_id', '!=', False),
                ('date_start', '<', leave.date_to),
                ('date_stop', '>', leave.date_from),
                ('state', '!=', 'cancelled'),
            ], limit=1)
            if conflict:
                raise UserError(_(
                    'This time off overlaps an existing work entry. '
                    'Resolve the work-entry period before creating or moving the leave.'))

    @api.model_create_multi
    def create(self, vals_list):
        with self.env.cr.savepoint():
            self._sl_lock_affected_employees(vals_list=vals_list)
            leaves = super().create(vals_list)
            leaves._sl_assert_no_shift_entries()
        return leaves

    def write(self, vals):
        try:
            with self.env.cr.savepoint():
                self._sl_lock_affected_employees(vals=vals)
                result = super().write(vals)
                self.invalidate_recordset()
                self._sl_assert_no_shift_entries()
                return result
        except UserError:
            self.invalidate_recordset()
            raise

    def unlink(self):
        with self.env.cr.savepoint():
            self._sl_lock_affected_employees()
            return super().unlink()


class HrWorkEntry(models.Model):
    _inherit = 'hr.work.entry'

    sl_shift_day_id = fields.Many2one(
        'sl.shift.day', readonly=True, copy=False, ondelete='restrict', index=True,
        groups='sl_employee_shift_attendance.group_shift_approver',
    )
    sl_shift_kind = fields.Selection([('regular', 'Regular'), ('overtime', 'Approved Overtime')], readonly=True, copy=False)
    sl_shift_digest = fields.Char(readonly=True, copy=False)
    _sql_constraints = [('sl_shift_entry_unique', 'UNIQUE(sl_shift_day_id, date_start, date_stop, sl_shift_kind)', 'A net shift interval can be generated only once.')]

    @api.model
    def _sl_managed_interval(self, employee_id, start, stop=None, duration=0):
        """Check the whole prospective interval, not just its UTC start date.

        A native record may begin before the assignment and extend into its
        manual-source period. Include caller defaults and duration-driven end
        recomputation; ownership uses the historical schedule timezone.
        """
        if not employee_id or not start:
            return False
        start = fields.Datetime.to_datetime(start)
        stop = fields.Datetime.to_datetime(stop) if stop else start
        if duration:
            stop = max(stop, start + timedelta(hours=duration))
        if stop <= start:
            return False
        assignments = self.env['sl.shift.assignment'].sudo().with_context(active_test=False).search([
            ('employee_id', '=', employee_id), ('work_entry_enabled', '=', True), ('attendance_policy', '=', 'shift'),
        ])
        for assignment in assignments:
            zone = pytz.timezone(assignment.schedule_tz)
            first = max(assignment.date_from, pytz.utc.localize(start).astimezone(zone).date() - timedelta(days=1))
            last = min(assignment.date_to or datetime.max.date(), pytz.utc.localize(stop).astimezone(zone).date())
            # Every nonempty weekday roster repeats within seven days. The
            # extra sample includes previous-day carryover without a year loop.
            for offset in range(min(8, (last - first).days + 1)):
                window = assignment._sl_window(first + timedelta(days=offset))
                if window and window['start'] < stop and window['next_start'] > start:
                    return True
        return False

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access('create')
        defaults = self.default_get(['employee_id', 'date_start', 'date_stop', 'duration', 'contract_id'])
        self.env['sl.shift.guard']._sl_lock([v.get('employee_id', defaults.get('employee_id')) for v in vals_list if v.get('employee_id', defaults.get('employee_id'))])
        if not trusted(self.env):
            protected = {'sl_shift_day_id', 'sl_shift_kind', 'sl_shift_digest'}
            for vals in vals_list:
                # Match native18's inferred effective contract before checking
                # its source; omitting contract_id must not bypass ownership.
                effective = self._set_current_contract(dict(defaults, **vals))
                contract = self.env['hr.contract'].sudo().browse(effective.get('contract_id'))
                if (protected.intersection(vals) or any('default_' + f in self.env.context for f in protected)
                        or contract.work_entry_source == _SOURCE
                        or self._sl_managed_interval(effective.get('employee_id'), effective.get('date_start'),
                                                     effective.get('date_stop'), effective.get('duration', 0))):
                    raise AccessError(_('Managed work-entry source links and amounts must be generated from an authoritative shift summary.'))
        return super().create(vals_list)

    def write(self, vals):
        self.check_access('write')
        managed = self.filtered('sl_shift_day_id')
        financial = {'date_start', 'date_stop', 'duration', 'employee_id', 'contract_id', 'work_entry_type_id', 'company_id', 'active', 'state'}
        if managed or financial.intersection(vals):
            # Unmanaged source writers participate too: a concurrent explicit
            # generator must not miss an interval moved into its duty window.
            self.env['sl.shift.guard']._sl_lock(self.employee_id.ids + ([vals['employee_id']] if vals.get('employee_id') else []))
        if managed:
            managed.invalidate_recordset()
            if any(entry.state == 'validated' for entry in managed):
                raise UserError(_('Finalized shift work entries are immutable. Use a separate authorized adjustment.'))
        if not trusted(self.env):
            protected = {'sl_shift_day_id', 'sl_shift_kind', 'sl_shift_digest'}
            if protected.intersection(vals) or any('default_' + f in self.env.context for f in protected):
                raise AccessError(_('Shift source evidence cannot be edited.'))
            if managed and financial.intersection(vals):
                # Native conflict recalculation is allowed; it cannot approve,
                # cancel or change quantities. Validation has its own action.
                if vals != {'state': 'conflict'} and vals != {'state': 'draft'}:
                    raise AccessError(_('Use guarded shift regeneration/validation, not direct work-entry writes.'))
            target_contract = self.env['hr.contract'].sudo().browse(vals.get('contract_id'))
            if target_contract.work_entry_source == _SOURCE:
                raise AccessError(_('An unmanaged entry cannot be reparented to the manual shift source.'))
            for entry in self - managed:
                start = vals.get('date_start', entry.date_start)
                stop = vals.get('date_stop', entry.date_stop)
                duration = vals.get('duration', entry.duration if 'date_start' in vals and 'date_stop' not in vals else 0)
                if self._sl_managed_interval(vals.get('employee_id', entry.employee_id.id), start, stop, duration) and financial.intersection(vals):
                    raise AccessError(_('An unmanaged work entry cannot be moved into an authoritative shift period.'))
        return super().write(vals)

    def unlink(self):
        self.check_access('unlink')
        managed = self.filtered('sl_shift_day_id')
        if managed:
            self.env['sl.shift.guard']._sl_lock(managed.employee_id.ids)
            managed.invalidate_recordset()
            if any(entry.state == 'validated' for entry in managed):
                raise UserError(_('Finalized shift work entries cannot be deleted.'))
            if not trusted(self.env):
                raise AccessError(_('Managed work entries can only be replaced by guarded regeneration.'))
        return super().unlink()

    def action_validate(self):
        managed = self.filtered('sl_shift_day_id')
        unmanaged = self - managed
        if managed and unmanaged:
            raise UserError(_(
                'Validate managed shift entries separately from native work entries.'
            ))
        if managed:
            self.check_access('write')
            if not self.env.user.has_group('sl_employee_shift_attendance.group_shift_approver'):
                raise AccessError(_('A Shift Overtime Approver must validate managed work entries.'))
            self.env['sl.shift.guard']._sl_lock(managed.employee_id.ids)
            managed.invalidate_recordset()
            managed.sl_shift_day_id._sl_assert_current()
            if any(e.sl_shift_digest != e.sl_shift_day_id.digest for e in managed):
                raise UserError(_('Stale work-entry evidence. Regenerate before validation.'))
            # Validate all managed entries together; native validation works at
            # the calendar-date boundary, not separately per midnight fragment.
            return super(HrWorkEntry, internal(self)).action_validate()
        return super().action_validate()


class WorkEntryType(models.Model):
    _inherit = 'hr.work.entry.type'

    def write(self, vals):
        if {'code', 'external_code', 'is_leave', 'country_id', 'active'}.intersection(vals):
            entries = self.env['hr.work.entry'].sudo().with_context(active_test=False).search([
                ('work_entry_type_id', 'in', self.ids), ('sl_shift_day_id', '!=', False),
            ])
            if entries:
                raise UserError(_('A work-entry type used by shift evidence is frozen. Use a new type for future mapping.'))
        return super().write(vals)

    def unlink(self):
        if self.env['hr.work.entry'].sudo().with_context(active_test=False).search_count([('work_entry_type_id', 'in', self.ids), ('sl_shift_day_id', '!=', False)]):
            raise UserError(_('A work-entry type used by shift evidence cannot be deleted.'))
        return super().unlink()
