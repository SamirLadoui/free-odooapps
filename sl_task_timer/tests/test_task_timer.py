# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTaskTimer(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env['project.project'].create({
            'name': 'Timed Project', 'allow_timesheets': True})
        cls.task = cls.env['project.task'].create({
            'name': 'Timed Task', 'project_id': cls.project.id})
        cls.other_task = cls.env['project.task'].create({
            'name': 'Other Task', 'project_id': cls.project.id})
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Timer Person', 'user_id': cls.env.user.id})

    def _backdate(self, task, minutes):
        """Pretend the timer started `minutes` ago."""
        task.sudo().write({
            'sl_timer_start': fields.Datetime.now() - timedelta(minutes=minutes)})

    # -- starting ----------------------------------------------------------

    def test_start_sets_the_timer(self):
        self.task.action_timer_start()
        self.assertTrue(self.task.sl_timer_start)
        self.assertEqual(self.task.sl_timer_user_id, self.env.user)
        self.assertTrue(self.task.sl_timer_running)

    def test_starting_twice_on_the_same_task_is_refused(self):
        self.task.action_timer_start()
        with self.assertRaises(UserError):
            self.task.action_timer_start()

    def test_only_one_timer_per_person(self):
        """Two at once means one is recording time nobody spent."""
        self.task.action_timer_start()
        with self.assertRaises(UserError):
            self.other_task.action_timer_start()

    def test_the_refusal_names_the_other_task(self):
        self.task.action_timer_start()
        with self.assertRaises(UserError) as caught:
            self.other_task.action_timer_start()
        self.assertIn('Timed Task', str(caught.exception))

    def test_another_user_can_time_the_same_task(self):
        other_user = self.env['res.users'].create({
            'name': 'Second Timer', 'login': 'sl_timer_second'})
        self.env['hr.employee'].create({
            'name': 'Second Person', 'user_id': other_user.id})
        self.task.action_timer_start()
        self.task.with_user(other_user).action_timer_start()
        self.assertTrue(self.task.exists())

    # -- stopping ----------------------------------------------------------

    def test_stop_creates_a_timesheet(self):
        self.task.action_timer_start()
        self._backdate(self.task, 90)
        line = self.task.action_timer_stop()
        self.assertEqual(line.task_id, self.task)
        self.assertEqual(line.employee_id, self.employee)
        self.assertAlmostEqual(line.unit_amount, 1.5, places=1)

    def test_stop_clears_the_timer(self):
        self.task.action_timer_start()
        self._backdate(self.task, 30)
        self.task.action_timer_stop()
        self.assertFalse(self.task.sl_timer_start)
        self.assertFalse(self.task.sl_timer_running)

    def test_stopping_without_a_timer_is_refused(self):
        with self.assertRaises(UserError):
            self.task.action_timer_stop()

    def test_a_misclick_records_nothing(self):
        """Under a minute is a misclick, not work - but the timer must really
        stop, so this returns a notification rather than raising: an exception
        would roll back the very write that stopped it."""
        before = self.env['account.analytic.line'].search_count(
            [('task_id', '=', self.task.id)])
        self.task.action_timer_start()
        result = self.task.action_timer_stop()

        self.assertEqual(result.get('tag'), 'display_notification')
        self.assertFalse(self.task.sl_timer_start,
                         "the timer must actually have stopped")
        self.assertEqual(
            self.env['account.analytic.line'].search_count(
                [('task_id', '=', self.task.id)]),
            before, "nothing should have been recorded")

    def test_stopping_someone_elses_timer_is_refused(self):
        other_user = self.env['res.users'].create({
            'name': 'Owner', 'login': 'sl_timer_owner'})
        self.task.with_user(other_user).action_timer_start()
        with self.assertRaises(UserError):
            self.task.action_timer_stop()

    def test_a_user_without_an_employee_record_is_told(self):
        self.employee.unlink()
        self.task.action_timer_start()
        self._backdate(self.task, 30)
        with self.assertRaises(UserError) as caught:
            self.task.action_timer_stop()
        self.assertIn('employee', str(caught.exception).lower())

    # -- discarding --------------------------------------------------------

    def test_cancel_throws_the_time_away(self):
        before = self.env['account.analytic.line'].search_count(
            [('task_id', '=', self.task.id)])
        self.task.action_timer_start()
        self._backdate(self.task, 45)
        self.task.action_timer_cancel()
        self.assertFalse(self.task.sl_timer_start)
        self.assertEqual(
            self.env['account.analytic.line'].search_count(
                [('task_id', '=', self.task.id)]),
            before, "cancelling must not record anything")

    def test_cancelling_without_a_timer_is_refused(self):
        with self.assertRaises(UserError):
            self.task.action_timer_cancel()

    # -- elapsed -----------------------------------------------------------

    def test_elapsed_counts_up(self):
        self.task.action_timer_start()
        self._backdate(self.task, 120)
        self.task.invalidate_cache(['sl_timer_elapsed'])
        self.assertAlmostEqual(self.task.sl_timer_elapsed, 2.0, places=1)

    def test_elapsed_is_zero_without_a_timer(self):
        self.assertEqual(self.task.sl_timer_elapsed, 0.0)

    def test_running_timer_lookup(self):
        self.assertFalse(self.env['project.task']._running_timer_for())
        self.task.action_timer_start()
        self.assertEqual(self.env['project.task']._running_timer_for(), self.task)
