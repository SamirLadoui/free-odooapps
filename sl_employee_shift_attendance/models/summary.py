# SPDX-License-Identifier: LGPL-3.0-or-later
"""Custom authoritative shift engine, only for explicitly opted-in assignments."""
import hashlib
import json
import math

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

# RPC/context values cannot reproduce an object identity. Never use a boolean
# context escape hatch for authoritative writes.
_CAPABILITY = object()
_KEY = '_sl_shift_capability'
_RAW_EVIDENCE_GROUP = 'hr_attendance.group_hr_attendance_officer'
_RAW_EVIDENCE_MANAGER_GROUP = 'hr_attendance.group_hr_attendance_manager'
_RESTRICTED_EVIDENCE_KEYS = frozenset(('punches', 'removed_native_lines'))
_AUDIT_IDENTIFIER_KEYS = frozenset(('attendance_ids', 'entry_ids'))
_REDACTED_EVIDENCE = {'redacted': True}


def _contains_forbidden_raw_evidence(value, root=False):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _AUDIT_IDENTIFIER_KEYS:
                return True
            if key == 'removed_native_lines' and item:
                return True
            if key == 'punches' and not root:
                return True
            if _contains_forbidden_raw_evidence(item):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_raw_evidence(item) for item in value)
    return False


def _valid_punch_ids(evidence):
    if 'punches' not in evidence:
        return set()
    punches = evidence['punches']
    if not isinstance(punches, (list, tuple)):
        return None
    punch_ids = []
    for punch in punches:
        if not isinstance(punch, (list, tuple)) or not punch:
            return None
        punch_id = punch[0]
        if isinstance(punch_id, bool) or not isinstance(punch_id, int) or punch_id <= 0:
            return None
        punch_ids.append(punch_id)
    if len(set(punch_ids)) != len(punch_ids):
        return None
    return set(punch_ids)


def _record_can_read_raw_evidence(record):
    env = record.env
    if env.su or env.user.has_group(_RAW_EVIDENCE_MANAGER_GROUP):
        return True
    if not env.user.has_group(_RAW_EVIDENCE_GROUP):
        return False
    evidence = record.evidence
    if not isinstance(evidence, dict):
        return False
    if _contains_forbidden_raw_evidence(evidence, root=True):
        return False
    punch_ids = _valid_punch_ids(evidence)
    if punch_ids is None:
        return False
    if not punch_ids:
        return True
    try:
        accessible = record.env['hr.attendance'].sudo().search([
            ('id', 'in', list(punch_ids)),
        ]).with_user(env.user)._filtered_access('read')
    except AccessError:
        return False
    return set(accessible.ids) == punch_ids


def _can_read_raw_evidence(env, records=None):
    if env.su or env.user.has_group(_RAW_EVIDENCE_MANAGER_GROUP):
        return True
    if not env.user.has_group(_RAW_EVIDENCE_GROUP) or records is None:
        return False
    return all(_record_can_read_raw_evidence(record) for record in records)


def _sanitize_evidence(value):
    if isinstance(value, dict):
        sanitized = _sanitize_audit_evidence(value)
        return {
            key: _sanitize_evidence(item)
            for key, item in sanitized.items()
            if key not in _RESTRICTED_EVIDENCE_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_evidence(item) for item in value]
    return value


def _sanitize_audit_evidence(value):
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if key in _AUDIT_IDENTIFIER_KEYS:
                values = item if isinstance(item, (list, tuple)) else []
                prefix = key[:-4]
                sanitized[prefix + '_count'] = len(values)
                canonical_values = []
                for audit_value in values:
                    try:
                        canonical_values.append(json.dumps(
                            audit_value, sort_keys=True, separators=(',', ':'),
                        ))
                    except (TypeError, ValueError):
                        canonical_values.append(json.dumps(
                            {'malformed': type(audit_value).__name__},
                            sort_keys=True, separators=(',', ':'),
                        ))
                sanitized[prefix + '_digest'] = hashlib.sha256(
                    ('[' + ','.join(sorted(canonical_values)) + ']').encode(),
                ).hexdigest()
            else:
                sanitized[key] = _sanitize_audit_evidence(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_audit_evidence(item) for item in value]
    return value


def _sanitize_read_evidence(records, rows, fields):
    if fields is not None and 'evidence' not in fields:
        return rows
    for row in rows:
        if 'evidence' in row and not _record_can_read_raw_evidence(records.browse(row['id'])):
            row['evidence'] = (
                _sanitize_evidence(row['evidence'])
                if isinstance(row['evidence'], dict)
                else dict(_REDACTED_EVIDENCE)
            )
    return rows


def _filter_read_relations(records, rows, fields, relations):
    if fields is not None:
        relation_names = set(fields)
    else:
        relation_names = set(relations)
    for field_name, (comodel, inverse_name) in relations.items():
        if field_name not in relation_names:
            continue
        try:
            children = records.env[comodel].sudo().with_context(active_test=False).search([
                (inverse_name, 'in', records.ids),
            ]).with_user(records.env.user)
            allowed_ids = set(children._filtered_access('read').ids)
        except AccessError:
            allowed_ids = set()
        for row in rows:
            if field_name in row:
                row[field_name] = [child_id for child_id in row[field_name] if child_id in allowed_ids]
    return rows


def _group_field_name(spec):
    if not isinstance(spec, str):
        return None
    root = spec.split('/', 1)[0].split(':', 1)[0]
    if root == 'evidence' or spec.endswith('(evidence)'):
        return 'evidence'
    return root


def _contains_evidence_spec(spec):
    if not isinstance(spec, str):
        return False
    return spec.endswith('(evidence)') or any(
        _group_field_name(segment) == 'evidence' for segment in spec.split('/')
    )


def _contains_nested_evidence_spec(spec):
    if not isinstance(spec, str) or '/' not in spec:
        return False
    return any(_group_field_name(segment) == 'evidence' for segment in spec.split('/'))


def _check_evidence_export_access(env, records, fields_to_export):
    if any(_contains_nested_evidence_spec(field) for field in fields_to_export):
        if not (env.su or env.user.has_group(_RAW_EVIDENCE_MANAGER_GROUP)):
            raise AccessError(_('Raw shift evidence cannot be exported by this user.'))
    if any(_contains_evidence_spec(field) for field in fields_to_export):
        if not _can_read_raw_evidence(env, records):
            raise AccessError(_('Raw shift evidence cannot be exported by this user.'))


def _safe_group_fields(model, domain, fields, groupby):
    groupby = [groupby] if isinstance(groupby, str) else (groupby or [])
    if any(_contains_evidence_spec(spec) for spec in groupby):
        raise AccessError(_('Raw shift evidence cannot be used as a grouping key.'))
    if _can_read_raw_evidence(model.env, model.search(domain)):
        return fields
    return [field for field in fields if not _contains_evidence_spec(field)]


def internal(records):
    # Never carry caller-controlled relational defaults into privileged creates.
    context = {k: v for k, v in records.env.context.items() if not k.startswith('default_')}
    context[_KEY] = _CAPABILITY
    return records.with_context(context)


def trusted(env):
    return env.context.get(_KEY) is _CAPABILITY


class ShiftAudit(models.Model):
    _name = 'sl.shift.audit'
    _description = 'Shift Integration Audit'
    _order = 'id desc'

    day_id = fields.Many2one('sl.shift.day', required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one(related='day_id.company_id', store=True)
    actor_id = fields.Many2one('res.users', required=True)
    occurred_at = fields.Datetime(required=True)
    event = fields.Char(required=True)
    reason = fields.Text(required=True)
    evidence = fields.Json(required=True)

    def _read_format(self, fnames, load='_classic_read'):
        rows = super()._read_format(fnames=fnames, load=load)
        return _sanitize_read_evidence(self, rows, fnames)

    def export_data(self, fields_to_export):
        _check_evidence_export_access(self.env, self, fields_to_export)
        return super().export_data(fields_to_export)

    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        fields = _safe_group_fields(self, domain, fields, groupby)
        return super().read_group(domain, fields, groupby, offset=offset, limit=limit,
                                  orderby=orderby, lazy=lazy)

    def web_read_group(self, domain, fields, groupby, limit=None, offset=0, orderby=False, lazy=True):
        fields = _safe_group_fields(self, domain, fields, groupby)
        return super().web_read_group(domain, fields, groupby, limit=limit, offset=offset,
                                      orderby=orderby, lazy=lazy)

    @api.model_create_multi
    def create(self, vals_list):
        if not trusted(self.env):
            raise AccessError(_('Audit events are maintained internally.'))
        vals_list = [dict(values, evidence=_sanitize_audit_evidence(values.get('evidence')))
                     if 'evidence' in values else values for values in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        raise AccessError(_('Audit events cannot be changed.'))

    def unlink(self):
        raise AccessError(_('Audit events cannot be deleted.'))


class ShiftDay(models.Model):
    _name = 'sl.shift.day'
    _description = 'Logical Shift Attendance Summary'
    _order = 'shift_date desc, employee_id'

    assignment_id = fields.Many2one('sl.shift.assignment', required=True, ondelete='restrict', index=True, readonly=True)
    employee_id = fields.Many2one('hr.employee', required=True, ondelete='restrict', index=True, readonly=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True, index=True)
    shift_date = fields.Date(required=True, index=True, readonly=True)
    start = fields.Datetime(readonly=True)
    stop = fields.Datetime(readonly=True)
    expected_hours = fields.Float(readonly=True)
    elapsed_hours = fields.Float(readonly=True)
    net_hours = fields.Float(readonly=True)
    regular_hours = fields.Float(readonly=True)
    raw_overtime_hours = fields.Float(readonly=True)
    approved_overtime_hours = fields.Float(readonly=True)
    presence_days = fields.Integer(readonly=True)
    state = fields.Selection([('open', 'Incomplete'), ('pending', 'Pending Approval'),
                              ('approved', 'Approved'), ('refused', 'Refused'), ('void', 'No Punches')],
                             required=True, default='pending', readonly=True)
    digest = fields.Char(required=True, readonly=True)
    evidence = fields.Json(readonly=True)
    approver_id = fields.Many2one('res.users', readonly=True)
    approved_at = fields.Datetime(readonly=True)
    decision_reason = fields.Text(readonly=True)
    attendance_ids = fields.One2many(
        'hr.attendance', 'sl_shift_day_id', readonly=True,
        groups='hr_attendance.group_hr_attendance_officer',
    )
    audit_ids = fields.One2many('sl.shift.audit', 'day_id', readonly=True)

    _sql_constraints = [('employee_date_unique', 'UNIQUE(employee_id, shift_date)', 'One presence anchor per employee and shift-start date.')]

    def _read_format(self, fnames, load='_classic_read'):
        rows = super()._read_format(fnames=fnames, load=load)
        rows = _sanitize_read_evidence(self, rows, fnames)
        return _filter_read_relations(
            self, rows, fnames, {'attendance_ids': ('hr.attendance', 'sl_shift_day_id')},
        )

    def export_data(self, fields_to_export):
        _check_evidence_export_access(self.env, self, fields_to_export)
        return super().export_data(fields_to_export)

    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        fields = _safe_group_fields(self, domain, fields, groupby)
        return super().read_group(domain, fields, groupby, offset=offset, limit=limit,
                                  orderby=orderby, lazy=lazy)

    def web_read_group(self, domain, fields, groupby, limit=None, offset=0, orderby=False, lazy=True):
        fields = _safe_group_fields(self, domain, fields, groupby)
        return super().web_read_group(domain, fields, groupby, limit=limit, offset=offset,
                                      orderby=orderby, lazy=lazy)

    @api.model_create_multi
    def create(self, vals_list):
        if not trusted(self.env):
            raise AccessError(_('Shift summaries are maintained by the attendance engine.'))
        return super().create(vals_list)

    def write(self, vals):
        if not trusted(self.env):
            raise AccessError(_('Use the approval or repair action; summaries cannot be edited directly.'))
        return super().write(vals)

    def unlink(self):
        raise AccessError(_('Shift evidence is retained; use repair instead of deletion.'))

    def _sl_audit(self, event, reason, evidence=None):
        for day in self:
            internal(self.env['sl.shift.audit'].sudo()).create({
                'day_id': day.id, 'actor_id': self.env.uid,
                'occurred_at': fields.Datetime.now(), 'event': event,
                'reason': reason, 'evidence': evidence if evidence is not None else day.evidence,
            })

    def _sl_assert_mutable(self):
        """Optional work-entry bridge extends this boundary."""
        return True

    def _sl_sources_changed(self):
        return True

    def _sl_decision_changed(self):
        return True

    @api.model
    def _sl_check_mutation(self, employee, window):
        days = self.sudo().search([('employee_id', '=', employee.id), ('shift_date', '=', window['date'])])
        days._sl_assert_mutable()

    @api.model
    def _sl_values(self, assignment, window, attendances):
        punches = []
        elapsed = net = 0.0
        incomplete = False
        for attendance in attendances.sorted(lambda a: (a.check_in, a.id)):
            incomplete |= not bool(attendance.check_out)
            punches.append([attendance.id, fields.Datetime.to_string(attendance.check_in),
                            fields.Datetime.to_string(attendance.check_out)])
            if attendance.check_out:
                if attendance.check_out > window['next_start']:
                    raise ValidationError(_('A punch crosses the next shift start. Split it explicitly before repair.'))
                elapsed += (attendance.check_out - attendance.check_in).total_seconds() / 3600
                net += attendance._sl_net_in_window(window, attendance.check_in, attendance.check_out)
        evidence = {'assignment': assignment.id, 'date': str(window['date']),
                    'timezone': assignment.schedule_tz, 'workdays': assignment.workdays,
                    'start': str(window['start']), 'stop': str(window['stop']),
                    'break_start': str(window['break_start']), 'break_stop': str(window['break_stop']),
                    'expected': window['expected'], 'punches': punches,
                    'policy': 'custom_shift_net_v1', 'presence_policy': 'local_shift_start',
                    'hour_policy': 'actual_local_date', 'no_statutory_rates': True}
        digest = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
        payable = 0 if incomplete else net
        return {'assignment_id': assignment.id, 'employee_id': assignment.employee_id.id,
                'company_id': assignment.company_id.id, 'shift_date': window['date'],
                'start': window['start'], 'stop': window['stop'], 'expected_hours': window['expected'],
                'elapsed_hours': elapsed, 'net_hours': payable,
                'regular_hours': min(payable, window['expected']),
                'raw_overtime_hours': max(0, payable - window['expected']),
                'presence_days': int(bool(attendances) and not incomplete and net > 0),
                'state': 'open' if incomplete else ('pending' if attendances else 'void'),
                'digest': digest, 'evidence': evidence}

    @api.model
    def _sl_sync(self, attendances, previous=None):
        """Rebuild affected logical days from stored punches, not imported totals."""
        days = (previous or self.browse()) | attendances.sl_shift_day_id
        keys = {(d.employee_id.id, d.shift_date): (d.assignment_id, None) for d in days}
        for attendance in attendances:
            assignment, window = attendance._sl_assignment()
            if assignment:
                keys[(attendance.employee_id.id, window['date'])] = (assignment, window)
        for (employee_id, shift_date), (assignment, window) in sorted(keys.items()):
            day = self.sudo().search([('employee_id', '=', employee_id), ('shift_date', '=', shift_date)], limit=1)
            if not window:
                window = assignment._sl_window(shift_date, check_workday=False)
            candidates = self.env['hr.attendance'].sudo().search([
                ('employee_id', '=', employee_id), ('check_in', '>=', window['start']),
                ('check_in', '<', window['next_start']),
            ])
            matching = candidates.filtered(lambda a: a._sl_assignment()[0] == assignment
                                            and a._sl_assignment()[1]['date'] == shift_date)
            if not matching and not day:
                continue
            day._sl_assert_mutable()
            native_lines, native_blocked = matching._sl_native_history()
            if native_blocked:
                raise UserError(_('Existing native overtime has a decision, manual quantity, or no auditable approval provenance. Reconcile it while integration is off before adopting this history.'))
            native_evidence = native_lines.read(['date', 'duration', 'duration_real', 'adjustment']) if native_lines else []
            for native_row in native_evidence:
                native_row['date'] = fields.Date.to_string(native_row['date'])
            if native_lines:
                internal(native_lines).unlink()
            values = self._sl_values(assignment, window, matching)
            changed = not day or day.digest != values['digest']
            old_links = day.attendance_ids if day else self.env['hr.attendance']
            if changed:
                day._sl_sources_changed()
                values.update(approved_overtime_hours=0, approver_id=False, approved_at=False, decision_reason=False)
                if day:
                    internal(day).write(values)
                else:
                    day = internal(self.sudo()).create(values)
                day.with_user(self.env.user)._sl_audit('recomputed', 'Punch or schedule evidence changed; any earlier approval was revoked.',
                                                     dict(values['evidence'], removed_native_lines=native_evidence))
            removed = old_links - matching
            if removed:
                internal(removed).write({'sl_shift_day_id': False})
            if matching:
                internal(matching).write({'sl_shift_day_id': day.id})
            for field_name in ('worked_hours', 'overtime_hours', 'validated_overtime_hours', 'overtime_status', 'expected_hours'):
                if field_name in self.env['hr.attendance']._fields:
                    self.env.add_to_compute(self.env['hr.attendance']._fields[field_name], matching | removed)
        return self.sudo().search([('id', 'in', days.ids)]) | attendances.sl_shift_day_id

    def _sl_authorize_decision(self):
        if not self.env.user.has_group('sl_employee_shift_attendance.group_shift_approver'):
            raise AccessError(_('Only a Shift Overtime Approver can decide overtime.'))
        self.check_access('read')
        if any(day.employee_id.user_id.id == self.env.uid for day in self):
            raise AccessError(_('You cannot decide overtime for your own shift day.'))
        if any(d.company_id not in self.env.companies for d in self):
            raise AccessError(_('The summary company is not enabled.'))
        self.env['sl.shift.guard']._sl_lock(self.employee_id.ids)
        self.invalidate_recordset()
        self._sl_assert_mutable()
        # Re-read authoritative punches after locking, not caller context totals.
        self.env['sl.shift.day']._sl_sync(self.sudo().attendance_ids, self)
        self.invalidate_recordset()

    def action_approve(self, hours=None, reason=None):
        self.ensure_one()
        self._sl_authorize_decision()
        hours = self.raw_overtime_hours if hours is None else hours
        if isinstance(hours, bool) or not isinstance(hours, (int, float)) or not math.isfinite(hours):
            raise ValidationError(_('Approved hours must be a finite number.'))
        if not reason or not reason.strip():
            raise ValidationError(_('An approval reason is required.'))
        if self.state in ('open', 'void') or not 0 <= hours <= self.raw_overtime_hours:
            raise ValidationError(_('Approve only existing completed overtime, up to its raw hours.'))
        if self.state == 'approved' and self.approved_overtime_hours == hours and self.decision_reason == reason:
            return True
        self._sl_decision_changed()
        internal(self.sudo()).write({'state': 'approved', 'approved_overtime_hours': hours,
                              'approver_id': self.env.uid, 'approved_at': fields.Datetime.now(), 'decision_reason': reason})
        self._sl_audit('approved', reason, {'digest': self.digest, 'approved_hours': hours, 'raw_hours': self.raw_overtime_hours})
        return True

    def action_refuse(self, reason=None):
        self.ensure_one()
        self._sl_authorize_decision()
        if not reason or not reason.strip() or self.state in ('open', 'void'):
            raise ValidationError(_('A refusal reason and completed shift are required.'))
        self._sl_decision_changed()
        internal(self.sudo()).write({'state': 'refused', 'approved_overtime_hours': 0,
                              'approver_id': self.env.uid, 'approved_at': fields.Datetime.now(), 'decision_reason': reason})
        self._sl_audit('refused', reason, {'digest': self.digest, 'raw_hours': self.raw_overtime_hours})
        return True
