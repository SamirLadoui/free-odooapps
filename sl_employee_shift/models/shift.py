# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

HOURS_IN_DAY = 24.0


class ShiftAssignmentGuard(models.Model):
    _name = 'sl.shift.assignment.guard'
    _description = 'Shift Assignment Mutation Coordination'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade', index=True)
    generation = fields.Integer(default=0)

    _sql_constraints = [
        ('employee_unique', 'UNIQUE(employee_id)', 'One assignment coordination row per employee.'),
    ]

    @api.model
    def _sl_lock(self, employee_ids):
        # Updating an addon-owned unique row makes stale REPEATABLE READ
        # assignment writers serialize instead of both passing a search check.
        for employee_id in sorted(set(employee_ids)):
            if not employee_id:
                continue
            self.env.cr.execute('''
                INSERT INTO sl_shift_assignment_guard (employee_id, generation)
                VALUES (%s, 1)
                ON CONFLICT (employee_id) DO UPDATE
                SET generation = sl_shift_assignment_guard.generation + 1
                RETURNING id
            ''', (employee_id,))
            self.env.cr.fetchone()

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Assignment coordination rows are maintained internally.'))

    def write(self, vals):
        raise AccessError(_('Assignment coordination rows are maintained internally.'))

    def unlink(self):
        raise AccessError(_('Assignment coordination rows are maintained internally.'))


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
        # Template edits and assignment mutations update the same row. Under
        # REPEATABLE READ, a stale participant loses rather than applying a
        # policy change using a snapshot from before the other transaction.
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


class Shift(models.Model):
    _name = 'sl.shift'
    _description = 'Work Shift'
    _order = 'start_time, name'

    name = fields.Char(required=True)
    code = fields.Char()
    color = fields.Integer(string='Colour')
    active = fields.Boolean(default=True)

    start_time = fields.Float(
        string='Starts At', required=True, default=9.0,
        help="Hour of the day the shift begins, as a decimal: 8.5 is 08:30.")
    end_time = fields.Float(
        string='Ends At', required=True, default=17.0,
        help="Hour of the day the shift ends. Earlier than the start means it "
             "runs overnight.")
    break_minutes = fields.Integer(string='Unpaid Break (minutes)', default=0)

    overnight = fields.Boolean(compute='_compute_duration', store=True)
    duration = fields.Float(
        string='Paid Hours', compute='_compute_duration', store=True,
        help="Length of the shift, less the unpaid break.")

    assignment_ids = fields.One2many('sl.shift.assignment', 'shift_id')
    assignment_count = fields.Integer(compute='_compute_assignment_count')

    @api.depends('start_time', 'end_time', 'break_minutes')
    def _compute_duration(self):
        """A shift ending earlier than it starts runs past midnight.

        Treating 22:00-06:00 as minus sixteen hours is the classic way a
        night shift ends up unpaid.
        """
        for shift in self:
            span = shift.end_time - shift.start_time
            shift.overnight = span < 0
            if span < 0:
                span += HOURS_IN_DAY
            shift.duration = max(0.0, span - (shift.break_minutes or 0) / 60.0)

    @api.depends('assignment_ids')
    def _compute_assignment_count(self):
        for shift in self:
            shift.assignment_count = len(shift.assignment_ids)

    def write(self, vals):
        if {'start_time', 'end_time', 'break_minutes'}.intersection(vals):
            self.env['sl.shift.template.guard']._sl_lock(self.ids)
        return super().write(vals)

    @api.constrains('start_time', 'end_time')
    def _check_times(self):
        for shift in self:
            for value, label in ((shift.start_time, _("start")),
                                 (shift.end_time, _("end"))):
                if not 0.0 <= value < HOURS_IN_DAY:
                    raise ValidationError(_(
                        "The %(label)s time must be between 0 and 24.")
                        % {'label': label})
            if shift.start_time == shift.end_time:
                raise ValidationError(_(
                    "%s starts and ends at the same moment.") % shift.name)

    @api.constrains('break_minutes', 'start_time', 'end_time')
    def _check_break(self):
        for shift in self:
            if shift.break_minutes < 0:
                raise ValidationError(_("A break cannot be negative."))
            span = shift.end_time - shift.start_time
            if span < 0:
                span += HOURS_IN_DAY
            if (shift.break_minutes or 0) / 60.0 >= span:
                raise ValidationError(_(
                    "The break on %s is as long as the shift itself.") % shift.name)

    @api.constrains('code')
    def _check_code_unique(self):
        for shift in self.filtered('code'):
            if self.search_count([('id', '!=', shift.id), ('code', '=ilike', shift.code)]):
                raise ValidationError(_("Shift code '%s' is already used.") % shift.code)


class ShiftAssignment(models.Model):
    _name = 'sl.shift.assignment'
    _description = 'Shift Assignment'
    _inherit = ['mail.thread']
    _order = 'date_from desc, id desc'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True,
        ondelete='cascade', tracking=True)
    shift_id = fields.Many2one(
        'sl.shift', string='Shift', required=True, ondelete='restrict', tracking=True)
    department_id = fields.Many2one(related='employee_id.department_id', store=True)

    date_from = fields.Date(
        string='From', required=True, default=fields.Date.context_today, tracking=True)
    date_to = fields.Date(
        string='To', tracking=True,
        help="Leave empty for an assignment with no end date.")
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access_rights('create')
        defaults = self.default_get(['employee_id', 'shift_id'])
        employee_ids = [vals.get('employee_id', defaults.get('employee_id')) for vals in vals_list]
        shift_ids = [vals.get('shift_id', defaults.get('shift_id')) for vals in vals_list]
        self.env['sl.shift.assignment.guard']._sl_lock(employee_ids)
        self.env['sl.shift.template.guard']._sl_lock(shift_ids)
        return super().create(vals_list)

    def write(self, vals):
        self.check_access_rights('write')
        self.check_access_rule('write')
        assignment_guard_fields = {'employee_id', 'date_from', 'date_to'}
        if assignment_guard_fields.intersection(vals):
            employee_ids = self.employee_id.ids
            if vals.get('employee_id'):
                employee_ids.append(vals['employee_id'])
            self.env['sl.shift.assignment.guard']._sl_lock(employee_ids)
        template_guard_fields = {
            'employee_id', 'shift_id', 'date_from', 'date_to', 'active',
            'attendance_policy', 'schedule_tz', 'workdays', 'break_window_set', 'break_start',
        }
        if template_guard_fields.intersection(vals):
            shift_ids = self.mapped('shift_id').ids
            if vals.get('shift_id'):
                shift_ids.append(vals['shift_id'])
            self.env['sl.shift.template.guard']._sl_lock(shift_ids)
        return super().write(vals)

    @api.depends('employee_id', 'shift_id')
    def _compute_display_name(self):
        for assignment in self:
            assignment.display_name = '%s - %s' % (
                assignment.employee_id.name or '', assignment.shift_id.name or '')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for assignment in self:
            if assignment.date_to and assignment.date_to < assignment.date_from:
                raise ValidationError(_("The assignment ends before it starts."))

    @api.constrains('employee_id', 'date_from', 'date_to')
    def _check_no_overlap(self):
        """One shift at a time. Two overlapping assignments means no report can
        say which shift somebody was actually on."""
        for assignment in self:
            domain = [
                ('id', '!=', assignment.id),
                ('employee_id', '=', assignment.employee_id.id),
                ('date_from', '<=', assignment.date_to or '9999-12-31'),
                '|', ('date_to', '=', False),
                     ('date_to', '>=', assignment.date_from),
            ]
            clash = self.with_context(active_test=False).search(domain, limit=1)
            if clash:
                raise ValidationError(_(
                    "%(employee)s is already on %(shift)s from %(start)s.") % {
                        'employee': assignment.employee_id.name,
                        'shift': clash.shift_id.name,
                        'start': clash.date_from})


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    shift_assignment_ids = fields.One2many(
        'sl.shift.assignment', 'employee_id', string='Shift Assignments')
    current_shift_id = fields.Many2one(
        'sl.shift', string='Current Shift', compute='_compute_current_shift')

    @api.depends('shift_assignment_ids.date_from', 'shift_assignment_ids.date_to',
                 'shift_assignment_ids.shift_id')
    def _compute_current_shift(self):
        today = fields.Date.context_today(self)
        for employee in self:
            current = employee.shift_assignment_ids.filtered(
                lambda a: a.date_from <= today and (not a.date_to or a.date_to >= today))
            employee.current_shift_id = current[:1].shift_id
