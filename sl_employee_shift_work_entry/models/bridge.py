# SPDX-License-Identifier: LGPL-3.0-or-later
"""Odoo 15 start/stop contract work-entry bridge. No salary rules or statutory rates."""
from datetime import datetime, time, timedelta
import json

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.sl_employee_shift_attendance.models.summary import internal, trusted

_SOURCE = 'sl_shift_manual'


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

    def action_repair_attendance(self, dry_run=True, reason=None):
        self._sl_config_authorize()
        entries = self.env['hr.work.entry'].search([
            ('employee_id', 'in', self.employee_id.ids),
            ('date_stop', '>=', min(self.mapped('date_from'))),
        ]) if self else self.env['hr.work.entry']
        before = entries.read(['employee_id', 'date_start', 'date_stop', 'duration', 'work_entry_type_id', 'state', 'sl_shift_day_id'])
        preview = super().action_repair_attendance(dry_run=dry_run, reason=reason)
        for row in preview:
            day = fields.Date.to_date(row['shift_date'])
            matching = [e for e in before if e['employee_id'][0] == row['employee_id']
                        and e['date_start'].date() <= day + timedelta(days=1) and e['date_stop'].date() >= day]
            row['existing_work_entries'] = matching
            row['finalized_work_entries_block_repair'] = any(e['state'] == 'validated' for e in matching)
            row['work_entry_action'] = 'Separate explicit generation; never export unapproved raw overtime.'
        return preview

    @api.model_create_multi
    def create(self, vals_list):
        defaults = self.default_get(['work_entry_enabled'])
        enabled = any(v.get('work_entry_enabled', defaults.get('work_entry_enabled', False)) for v in vals_list)
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

    # Odoo 15 has no native work_entry_source selection. Keep its calendar
    # default and expose an explicit addon-owned source; never invent a native API.
    sl_shift_work_entry_source = fields.Selection([
        ('calendar', 'Native Calendar'),
        (_SOURCE, 'Shift Summary (Explicit Manual Generation)'),
    ], default='calendar', required=True, string='Shift Work Entry Source')

    def _generate_work_entries(self, date_start, date_stop, force=False):
        native = self.filtered(lambda c: c.sl_shift_work_entry_source != _SOURCE)
        return super(HrContract, native)._generate_work_entries(date_start, date_stop, force=force) if native else self.env['hr.work.entry']

    def _get_contract_work_entries_values(self, date_start, date_stop):
        native = self.filtered(lambda c: c.sl_shift_work_entry_source != _SOURCE)
        return super(HrContract, native)._get_contract_work_entries_values(date_start, date_stop) if native else []

    def _get_work_entries_values(self, date_start, date_stop):
        native = self.filtered(lambda c: c.sl_shift_work_entry_source != _SOURCE)
        return super(HrContract, native)._get_work_entries_values(date_start, date_stop) if native else []

    def _get_fields_that_recompute_we(self):
        fields_to_recompute = super()._get_fields_that_recompute_we()
        # Explicit source selection must not run the native broad regeneration
        # wizard, which archives unrelated existing entries. Manual is exclusive.
        return [f for f in fields_to_recompute if f != 'sl_shift_work_entry_source'] if any(c.sl_shift_work_entry_source == _SOURCE for c in self) else fields_to_recompute

    def write(self, vals):
        self.check_access_rights('write')
        self.check_access_rule('write')
        protected = {'sl_shift_work_entry_source', 'employee_id', 'company_id', 'date_start', 'date_end', 'resource_calendar_id', 'state', 'active'}
        if protected.intersection(vals):
            self.env['sl.shift.guard']._sl_lock(self.employee_id.ids)
            entries = self.env['hr.work.entry'].sudo().with_context(active_test=False).search([
                ('contract_id', 'in', self.ids), ('sl_shift_day_id', '!=', False),
            ])
            if entries:
                raise UserError(_('Contract source and ownership used by shift work entries are frozen. Create a future dated contract.'))
        return super().write(vals)

    def unlink(self):
        if self.env['hr.work.entry'].sudo().with_context(active_test=False).search_count([('contract_id', 'in', self.ids), ('sl_shift_day_id', '!=', False)]):
            raise UserError(_('Contracts used by shift evidence cannot be deleted.'))
        return super().unlink()


class HrWorkEntryRegenerationWizard(models.TransientModel):
    _inherit = 'hr.work.entry.regeneration.wizard'

    def regenerate_work_entries(self):
        self.ensure_one()
        if not self.env.context.get('work_entry_skip_validation'):
            if not self.valid:
                raise ValidationError(_("In order to regenerate the work entries, you need to provide the wizard with an employee_id, a date_from and a date_to. In addition to that, the time interval defined by date_from and date_to must not contain any validated work entries."))
            if self.date_from < self.earliest_available_date or self.date_to > self.latest_available_date:
                raise ValidationError(_(
                    "The from date must be >= '%(earliest_available_date)s' and the to date must be <= '%(latest_available_date)s', which correspond to the generated work entries time interval.",
                    earliest_available_date=self._date_to_string(self.earliest_available_date),
                    latest_available_date=self._date_to_string(self.latest_available_date),
                ))

        date_from = max(self.date_from, self.earliest_available_date) if self.earliest_available_date else self.date_from
        date_to = min(self.date_to, self.latest_available_date) if self.latest_available_date else self.date_to
        entries = self.env['hr.work.entry'].search([
            ('employee_id', '=', self.employee_id.id),
            ('date_stop', '>=', date_from),
            ('date_start', '<=', date_to),
            ('state', '!=', 'validated'),
        ])
        manual_source_entries = entries.filtered(
            lambda entry: entry.contract_id.sl_shift_work_entry_source == _SOURCE)
        if not manual_source_entries:
            # Keep Odoo's exact implementation for the ordinary native-only path.
            return super().regenerate_work_entries()

        # Odoo 15's native wizard archives every draft row before asking the
        # employee to regenerate. A manual-source contract intentionally returns
        # no native replacement, so retain its rows and archive unrelated/native
        # rows only. Keep the archive + generation sequence atomic if a caller
        # catches a later generation error.
        with self.env.cr.savepoint():
            (entries - manual_source_entries).write({'active': False})
            self.employee_id.generate_work_entries(date_from, date_to, True)
        return self.env["ir.actions.actions"]._for_xml_id('hr_work_entry.hr_work_entry_action')


class ShiftDay(models.Model):
    _inherit = 'sl.shift.day'

    work_entry_ids = fields.One2many('hr.work.entry', 'sl_shift_day_id', readonly=True)

    @api.model
    def _sl_assert_period_mutable(self, employee, start_date, stop_date, lower=None, upper=None):
        zone = pytz.timezone(employee._get_tz())
        lower = lower or zone.localize(datetime.combine(start_date, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        upper = upper or zone.localize(datetime.combine(stop_date + timedelta(days=1), time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        finalized = self.env['hr.work.entry'].sudo().with_context(active_test=False).search_count([
            ('employee_id', '=', employee.id), ('date_stop', '>', lower), ('date_start', '<', upper), ('state', '=', 'validated'),
        ])
        if finalized:
            raise UserError(_('This shift touches finalized native work entries. Use an authorized adjustment outside the closed period.'))
        # The standard payroll model is optional. Never claim provider-specific
        # payroll certification from this defensive standard-state check.
        if 'hr.payslip' in self.env.registry:
            payslips = self.env['hr.payslip'].sudo().search_count([
                ('employee_id', '=', employee.id), ('date_from', '<=', stop_date), ('date_to', '>=', start_date),
                ('state', 'in', ['done', 'paid']),
            ])
            if payslips:
                raise UserError(_('A finalized or paid payslip overlaps this shift. No automatic repair is permitted.'))

    def _sl_assert_mutable(self):
        for day in self:
            window = day.assignment_id._sl_window(day.shift_date, check_workday=False)
            self._sl_assert_period_mutable(day.employee_id, day.shift_date, day.shift_date + timedelta(days=1), window['start'], window['next_start'])
        return super()._sl_assert_mutable()

    @api.model
    def _sl_check_mutation(self, employee, window):
        self._sl_assert_period_mutable(employee, window['date'], window['date'] + timedelta(days=1), window['start'], window['next_start'])
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
            current = self.env['sl.shift.day']._sl_values(day.assignment_id, window, day.attendance_ids)
            if current['digest'] != day.digest:
                raise UserError(_('Source punches changed. Run the guarded repair and obtain approval again.'))

    def _sl_effective_contract(self, begin, end):
        self.ensure_one()
        contracts = self.env['hr.contract'].sudo().with_context(active_test=False).search([
            ('employee_id', '=', self.employee_id.id), ('company_id', '=', self.company_id.id),
            ('state', 'in', ['open', 'close']), ('date_start', '<=', end.date() + timedelta(days=1)),
            '|', ('date_end', '=', False), ('date_end', '>=', begin.date() - timedelta(days=1)),
        ])
        matches = self.env['hr.contract']
        for contract in contracts:
            zone = pytz.timezone((contract.resource_calendar_id or self.employee_id.resource_calendar_id).tz or 'UTC')
            first = zone.localize(datetime.combine(contract.date_start, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
            last = zone.localize(datetime.combine(contract.date_end + timedelta(days=1), time.min)).astimezone(pytz.utc).replace(tzinfo=None) if contract.date_end else datetime.max
            if first <= begin < end <= last:
                matches |= contract
        if len(matches) != 1 or matches.sl_shift_work_entry_source != _SOURCE:
            raise UserError(_('Every actual interval requires one effective same-company open/closed contract explicitly using Shift Summary (Explicit Manual Generation).'))
        return matches

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
        # Leave/holiday classification belongs to the payroll provider. Refuse
        # ambiguous overlaps instead of silently replacing native leave entries.
        leaves = self.env['resource.calendar.leaves'].sudo().search_count([
            ('resource_id', 'in', [False, self.employee_id.resource_id.id]),
            ('company_id', 'in', [False, self.company_id.id]),
            ('calendar_id', 'in', [False, self.employee_id.resource_calendar_id.id]),
            ('date_from', '<', window['next_start']), ('date_to', '>', window['start']),
        ])
        if leaves:
            raise UserError(_('A leave or public holiday overlaps this duty window. Resolve its provider-specific classification before generation.'))
        values = []
        remaining_regular = self.regular_hours
        remaining_overtime = self.approved_overtime_hours if self.state == 'approved' else 0
        for attendance in self.attendance_ids.sorted(lambda a: (a.check_in, a.id)):
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
                        contract = self._sl_effective_contract(instant, boundary)
                        entry_type = assignment.regular_type_id if kind == 'regular' else assignment.overtime_type_id
                        values.append({'name': '%s / %s / %s' % (self.employee_id.name, self.shift_date, kind),
                                       'employee_id': self.employee_id.id, 'contract_id': contract.id, 'company_id': self.company_id.id,
                                       'date_start': instant, 'date_stop': boundary,
                                       'work_entry_type_id': entry_type.id, 'state': 'draft', 'active': True,
                                       'sl_shift_day_id': self.id, 'sl_shift_kind': kind, 'sl_shift_digest': self.digest})
                        instant = boundary
                    if kind == 'regular':
                        remaining_regular -= duration
                    else:
                        remaining_overtime -= duration
        return values

    def action_generate_and_open_work_entries(self):
        entries = self.action_generate_work_entries()
        return {'type': 'ir.actions.act_window', 'name': _('Shift Work Entries'),
                'res_model': 'hr.work.entry', 'view_mode': 'tree,form',
                'domain': [('id', 'in', entries.ids)]}

    def action_generate_work_entries(self):
        if not (self.env.user.has_group('hr.group_hr_manager')
                and self.env.user.has_group('sl_employee_shift_attendance.group_shift_approver')):
            raise AccessError(_('Manual generation requires HR administrator and Shift Overtime Approver roles.'))
        self.check_access_rights('read')
        self.check_access_rule('read')
        if any(day.company_id not in self.env.companies for day in self):
            raise AccessError(_('The summary company is not enabled.'))
        with self.env.cr.savepoint():
            self.env['sl.shift.guard']._sl_lock(self.employee_id.ids)
            self.invalidate_cache()
            self._sl_assert_current()
            result = self.env['hr.work.entry']
            for day in self:
                payload = day._sl_entry_payload()
                existing = day.sudo().with_context(active_test=False).work_entry_ids
                compare = ['employee_id', 'contract_id', 'company_id', 'date_start', 'date_stop', 'work_entry_type_id',
                           'sl_shift_day_id', 'sl_shift_kind', 'sl_shift_digest', 'active']
                def normalized(values, compare=tuple(compare)):
                    return sorted([json.dumps({k: (str(v) if k in ('date_start', 'date_stop') else round(v, 8) if isinstance(v, float) else v)
                                               for k, v in row.items() if k in compare}, sort_keys=True) for row in values])
                stored = []
                for entry in existing:
                    stored.append({k: entry[k].id if entry._fields[k].type == 'many2one' else entry[k] for k in compare})
                if existing and normalized(stored) == normalized(payload):
                    result |= existing
                    continue
                day._sl_assert_mutable()
                starts = [v['date_start'] for v in payload]
                stops = [v['date_stop'] for v in payload]
                if starts:
                    foreign = self.env['hr.work.entry'].sudo().search_count([
                        ('employee_id', '=', day.employee_id.id), ('date_start', '<', max(stops)), ('date_stop', '>', min(starts)),
                        ('state', '!=', 'cancelled'), ('sl_shift_day_id', '=', False),
                    ])
                    if foreign:
                        raise UserError(_('Other native work entries already exist for these dates. Dry-run and reconcile their source; no entries were deleted.'))
                if existing:
                    internal(existing).unlink()
                if payload:
                    generated = internal(self.env['hr.work.entry']).create(payload)
                    result |= generated
                    for contract in generated.contract_id:
                        rows = generated.filtered(lambda e, contract=contract: e.contract_id == contract)
                        first, last = min(rows.mapped('date_start')), max(rows.mapped('date_stop'))
                        unused = contract.date_generated_from == contract.date_generated_to
                        contract.write({'date_generated_from': first if unused else min(first, contract.date_generated_from),
                                        'date_generated_to': last if unused else max(last, contract.date_generated_to)})
                    day._sl_audit('work_entries_generated', 'Explicit provider-neutral manual generation.',
                                  {'digest': day.digest, 'entry_ids': generated.ids,
                                   'regular_hours': day.regular_hours, 'approved_overtime_hours': day.approved_overtime_hours})
            return result


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    def _sl_before_mutation(self, proposed=None):
        result = super()._sl_before_mutation(proposed)
        # A check-in outside the roster can still span a managed finalized duty.
        # Check the complete old/new interval, not just its resolved start date.
        for attendance in self | (proposed or self.browse()):
            if not attendance.check_in or not attendance.check_out:
                continue
            assignments = self.env['sl.shift.assignment'].sudo().with_context(active_test=False).search([
                ('employee_id', '=', attendance.employee_id.id), ('attendance_policy', '=', 'shift'),
            ])
            for assignment in assignments:
                zone = pytz.timezone(assignment.schedule_tz)
                first = pytz.utc.localize(attendance.check_in).astimezone(zone).date() - timedelta(days=1)
                last = pytz.utc.localize(attendance.check_out).astimezone(zone).date()
                day = max(first, assignment.date_from)
                last = min(last, assignment.date_to) if assignment.date_to else last
                while day <= last:
                    window = assignment._sl_window(day)
                    if window and attendance.check_in < window['next_start'] and attendance.check_out > window['start']:
                        self.env['sl.shift.day']._sl_check_mutation(attendance.employee_id, window)
                    day += timedelta(days=1)
        return result


class HrWorkEntry(models.Model):
    _inherit = 'hr.work.entry'

    sl_shift_day_id = fields.Many2one('sl.shift.day', readonly=True, copy=False, ondelete='restrict', index=True)
    sl_shift_kind = fields.Selection([('regular', 'Regular'), ('overtime', 'Approved Overtime')], readonly=True, copy=False)
    sl_shift_digest = fields.Char(readonly=True, copy=False)
    _sql_constraints = [('sl_shift_entry_unique', 'UNIQUE(sl_shift_day_id, date_start, sl_shift_kind)', 'A shift/start/type can be generated only once.')]

    @api.model
    def _sl_managed_interval(self, employee_id, start, stop=None):
        if not employee_id or not start:
            return False
        start = fields.Datetime.to_datetime(start)
        stop = fields.Datetime.to_datetime(stop) if stop else start + timedelta(microseconds=1)
        assignments = self.env['sl.shift.assignment'].sudo().with_context(active_test=False).search([
            ('employee_id', '=', employee_id), ('work_entry_enabled', '=', True), ('attendance_policy', '=', 'shift'),
        ])
        for assignment in assignments:
            zone = pytz.timezone(assignment.schedule_tz)
            first = pytz.utc.localize(start).astimezone(zone).date() - timedelta(days=1)
            last = pytz.utc.localize(stop).astimezone(zone).date()
            day = max(first, assignment.date_from)
            last = min(last, assignment.date_to) if assignment.date_to else last
            while day <= last:
                window = assignment._sl_window(day)
                if window and start < window['next_start'] and stop > window['start']:
                    return True
                day += timedelta(days=1)
        return False

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access_rights('create')
        defaults = self.default_get(['employee_id', 'date_start', 'date_stop', 'contract_id'])
        self.env['sl.shift.guard']._sl_lock([v.get('employee_id', defaults.get('employee_id')) for v in vals_list if v.get('employee_id', defaults.get('employee_id'))])
        if not trusted(self.env):
            protected = {'sl_shift_day_id', 'sl_shift_kind', 'sl_shift_digest'}
            defaults = self.default_get(['employee_id', 'date_start', 'date_stop', 'contract_id'])
            for vals in vals_list:
                effective = self._set_current_contract(dict(defaults, **vals))
                contract = self.env['hr.contract'].sudo().browse(effective.get('contract_id'))
                if (protected.intersection(vals) or any('default_' + f in self.env.context for f in protected)
                        or contract.sl_shift_work_entry_source == _SOURCE
                        or self._sl_managed_interval(effective.get('employee_id'), effective.get('date_start'),
                            effective.get('date_stop') or (fields.Datetime.to_datetime(effective['date_start']) + timedelta(hours=effective.get('duration', 0)) if effective.get('date_start') else None))):
                    raise AccessError(_('Managed work-entry source links and amounts must be generated from an authoritative shift summary.'))
        return super().create(vals_list)

    def _sl_assert_not_finalized(self):
        self.env['sl.shift.guard']._sl_lock(self.employee_id.ids)
        self.invalidate_cache()
        for entry in self:
            if entry.state == 'validated' and (entry.sl_shift_day_id or self._sl_managed_interval(
                    entry.employee_id.id, entry.date_start, entry.date_stop)):
                raise UserError(_('Finalized work-entry evidence in a managed shift period is immutable. Use a separate authorized adjustment.'))

    def write(self, vals):
        self.check_access_rights('write')
        self.check_access_rule('write')
        self._sl_assert_not_finalized()
        managed = self.filtered('sl_shift_day_id')
        if managed:
            self.env['sl.shift.guard']._sl_lock(managed.employee_id.ids)
            managed.invalidate_cache()
            if any(entry.state == 'validated' for entry in managed):
                raise UserError(_('Finalized shift work entries are immutable. Use a separate authorized adjustment.'))
        if not trusted(self.env):
            protected = {'sl_shift_day_id', 'sl_shift_kind', 'sl_shift_digest'}
            financial = {'date_start', 'date_stop', 'duration', 'employee_id', 'contract_id', 'work_entry_type_id', 'company_id', 'active', 'state'}
            if protected.intersection(vals) or any('default_' + f in self.env.context for f in protected):
                raise AccessError(_('Shift source evidence cannot be edited.'))
            if managed and financial.intersection(vals):
                # Native conflict recalculation is allowed; it cannot approve,
                # cancel or change quantities. Validation has its own action.
                if vals != {'state': 'conflict'} and vals != {'state': 'draft'}:
                    raise AccessError(_('Use guarded shift regeneration/validation, not direct work-entry writes.'))
            target_contract = self.env['hr.contract'].sudo().browse(vals.get('contract_id'))
            if target_contract.sl_shift_work_entry_source == _SOURCE:
                raise AccessError(_('An unmanaged entry cannot be reparented to the manual shift source.'))
            for entry in self - managed:
                if self._sl_managed_interval(vals.get('employee_id', entry.employee_id.id), vals.get('date_start', entry.date_start),
                        (fields.Datetime.to_datetime(vals.get('date_start', entry.date_start)) + timedelta(hours=vals['duration'])) if 'duration' in vals else vals.get('date_stop', entry.date_stop)) and financial.intersection(vals):
                    raise AccessError(_('An unmanaged work entry cannot be moved into an authoritative shift period.'))
        return super().write(vals)

    def unlink(self):
        self.check_access_rights('unlink')
        self.check_access_rule('unlink')
        self._sl_assert_not_finalized()
        managed = self.filtered('sl_shift_day_id')
        if managed:
            self.env['sl.shift.guard']._sl_lock(managed.employee_id.ids)
            managed.invalidate_cache()
            if any(entry.state == 'validated' for entry in managed):
                raise UserError(_('Finalized shift work entries cannot be deleted.'))
            if not trusted(self.env):
                raise AccessError(_('Managed work entries can only be replaced by guarded regeneration.'))
        return super().unlink()

    def action_validate(self):
        managed = self.filtered('sl_shift_day_id')
        if managed:
            self.check_access_rights('write')
            self.check_access_rule('write')
            if not self.env.user.has_group('sl_employee_shift_attendance.group_shift_approver'):
                raise AccessError(_('A Shift Overtime Approver must validate managed work entries.'))
            self.env['sl.shift.guard']._sl_lock(managed.employee_id.ids)
            managed.invalidate_cache()
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
        if {'code', 'is_leave', 'active'}.intersection(vals):
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
