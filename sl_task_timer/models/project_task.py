# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Below this a "session" is a misclick, not work.
MIN_MINUTES = 1


class ProjectTask(models.Model):
    _inherit = 'project.task'

    sl_timer_start = fields.Datetime(
        string='Timer Started', readonly=True, copy=False,
        help="When the current timer was started. Empty when nothing is running.")
    sl_timer_user_id = fields.Many2one(
        'res.users', string='Timer Owner', readonly=True, copy=False)
    sl_timer_running = fields.Boolean(
        compute='_compute_timer', help="A timer is running for the current user.")
    sl_timer_elapsed = fields.Float(
        compute='_compute_timer', string='Running For (hours)')

    @api.depends('sl_timer_start', 'sl_timer_user_id')
    def _compute_timer(self):
        now = fields.Datetime.now()
        for task in self:
            running = bool(task.sl_timer_start
                           and task.sl_timer_user_id == self.env.user)
            task.sl_timer_running = running
            task.sl_timer_elapsed = (
                (now - task.sl_timer_start).total_seconds() / 3600.0
                if task.sl_timer_start else 0.0)

    # -- finding what is already running -----------------------------------

    @api.model
    def _running_timer_for(self, user=None):
        """The task this user currently has a timer on, if any.

        One timer per person is the whole point: two running at once means at
        least one of them is recording time the person was not spending.
        """
        user = user or self.env.user
        return self.search([
            ('sl_timer_start', '!=', False),
            ('sl_timer_user_id', '=', user.id),
        ], limit=1)

    # -- actions -----------------------------------------------------------

    def action_timer_start(self):
        self.ensure_one()
        running = self._running_timer_for()
        if running == self:
            raise UserError(_("The timer is already running on this task."))
        if running:
            raise UserError(_(
                "A timer is already running on '%s'. Stop it first: two timers "
                "at once means one of them is recording time you were not "
                "spending.") % running.display_name)
        self.write({
            'sl_timer_start': fields.Datetime.now(),
            'sl_timer_user_id': self.env.user.id,
        })
        return True

    def action_timer_stop(self):
        """Stop the timer and record the time as a timesheet line."""
        self.ensure_one()
        if not self.sl_timer_start:
            raise UserError(_("No timer is running on this task."))
        if self.sl_timer_user_id != self.env.user:
            raise UserError(_(
                "That timer belongs to %s.") % self.sl_timer_user_id.name)

        hours = self._elapsed_hours()
        self._clear_timer()
        if hours * 60 < MIN_MINUTES:
            # A notification, not a UserError: raising would roll back the
            # write above, leaving the timer running while telling the user it
            # had stopped.
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Timer stopped"),
                    'message': _("Less than a minute, so nothing was recorded."),
                    'type': 'warning',
                    'sticky': False,
                },
            }
        return self._create_timesheet(hours)

    def action_timer_cancel(self):
        """Throw the running time away without recording it."""
        self.ensure_one()
        if not self.sl_timer_start:
            raise UserError(_("No timer is running on this task."))
        if self.sl_timer_user_id != self.env.user:
            raise UserError(_(
                "That timer belongs to %s.") % self.sl_timer_user_id.name)
        self._clear_timer()
        return True

    # -- internals ---------------------------------------------------------

    def _elapsed_hours(self):
        self.ensure_one()
        delta = fields.Datetime.now() - self.sl_timer_start
        return max(0.0, delta.total_seconds() / 3600.0)

    def _clear_timer(self):
        self.ensure_one()
        self.write({'sl_timer_start': False, 'sl_timer_user_id': False})

    def _create_timesheet(self, hours):
        self.ensure_one()
        employee = self.env['hr.employee'].search(
            [('user_id', '=', self.env.user.id)], limit=1)
        if not employee:
            raise UserError(_(
                "%s has no employee record, so the time cannot be recorded on a "
                "timesheet.") % self.env.user.name)
        return self.env['account.analytic.line'].create({
            'name': _("Timed work on %s") % self.name,
            'task_id': self.id,
            'project_id': self.project_id.id,
            'employee_id': employee.id,
            'unit_amount': round(hours, 2),
            'date': fields.Date.context_today(self),
        })
