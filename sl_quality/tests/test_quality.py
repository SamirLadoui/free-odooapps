# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestQuality(TransactionCase):

    def setUp(self):
        # 14.0 has no class-level env: setUpClass cannot build fixtures.
        super().setUp()
        self.today = fields.Date.context_today(self.env['sl.quality.nonconformity'])

    def _nc(self, **values):
        return self.env['sl.quality.nonconformity'].create(dict({
            'name': 'Wrong labels on batch 42',
            'description': 'Labels showed the wrong expiry date.',
            'date_reported': self.today,
        }, **values))

    def _action(self, nc, **values):
        return self.env['sl.quality.action'].create(dict({
            'nonconformity_id': nc.id,
            'name': 'Retrain the labelling team',
        }, **values))

    # -- the workflow gate -------------------------------------------------

    def test_reference_is_generated(self):
        self.assertTrue(self._nc().code.startswith('NC/'))

    def test_actions_need_a_root_cause_first(self):
        """An action without a cause is a guess."""
        nc = self._nc()
        nc.action_start_analysis()
        self._action(nc)
        with self.assertRaises(ValidationError):
            nc.action_start_actions()

    def test_actions_need_at_least_one_action(self):
        nc = self._nc(root_cause='Operator used an old template.')
        nc.action_start_analysis()
        with self.assertRaises(ValidationError):
            nc.action_start_actions()

    def test_analysis_to_actions_when_both_are_present(self):
        nc = self._nc(root_cause='Operator used an old template.')
        nc.action_start_analysis()
        self._action(nc)
        nc.action_start_actions()
        self.assertEqual(nc.state, 'action')

    # -- closing must be earned --------------------------------------------

    def test_cannot_close_without_a_root_cause(self):
        nc = self._nc()
        nc.state = 'action'
        with self.assertRaises(ValidationError):
            nc.action_close()

    def test_cannot_close_with_open_actions(self):
        """Closing claims it will not happen again."""
        nc = self._nc(root_cause='Old template.')
        self._action(nc)
        nc.state = 'action'
        with self.assertRaises(ValidationError):
            nc.action_close()

    def test_closes_once_every_action_is_resolved(self):
        nc = self._nc(root_cause='Old template.')
        first = self._action(nc)
        second = self._action(nc, name='Update the template')
        nc.state = 'action'
        first.action_done()
        second.action_cancel()
        nc.action_close()
        self.assertEqual(nc.state, 'closed')
        self.assertEqual(nc.date_closed, self.today)

    def test_cancelled_actions_do_not_block_closing(self):
        nc = self._nc(root_cause='Old template.')
        self._action(nc).action_cancel()
        nc.state = 'action'
        nc.action_close()
        self.assertEqual(nc.state, 'closed')

    def test_reopening_clears_the_close_date(self):
        nc = self._nc(root_cause='Old template.')
        self._action(nc).action_done()
        nc.state = 'action'
        nc.action_close()
        nc.action_reset_to_draft()
        self.assertEqual(nc.state, 'draft')
        self.assertFalse(nc.date_closed)

    # -- action state ------------------------------------------------------

    def test_action_defaults_to_open(self):
        self.assertEqual(self._action(self._nc()).state, 'open')

    def test_done_stamps_the_date(self):
        action = self._action(self._nc())
        action.action_done()
        self.assertEqual(action.state, 'done')
        self.assertEqual(action.date_done, self.today)

    def test_reopen_clears_the_done_date(self):
        action = self._action(self._nc())
        action.action_done()
        action.action_reopen()
        self.assertEqual(action.state, 'open')
        self.assertFalse(action.date_done)

    # -- overdue -----------------------------------------------------------

    def test_past_deadline_is_overdue(self):
        nc = self._nc(date_reported=self.today - timedelta(days=30))
        action = self._action(nc, deadline=self.today - timedelta(days=1))
        self.assertTrue(action.is_overdue)

    def test_today_is_not_yet_overdue(self):
        action = self._action(self._nc(), deadline=self.today)
        self.assertFalse(action.is_overdue)

    def test_future_deadline_is_not_overdue(self):
        action = self._action(self._nc(), deadline=self.today + timedelta(days=7))
        self.assertFalse(action.is_overdue)

    def test_no_deadline_is_never_overdue(self):
        self.assertFalse(self._action(self._nc()).is_overdue)

    def test_a_done_action_stops_being_overdue(self):
        """Finishing late is still finishing."""
        nc = self._nc(date_reported=self.today - timedelta(days=30))
        action = self._action(nc, deadline=self.today - timedelta(days=5))
        self.assertTrue(action.is_overdue)
        action.action_done()
        self.assertFalse(action.is_overdue)

    def test_deadline_cannot_precede_the_report(self):
        nc = self._nc()
        with self.assertRaises(ValidationError):
            self._action(nc, deadline=self.today - timedelta(days=1))

    # -- rollups -----------------------------------------------------------

    def test_counts(self):
        nc = self._nc(date_reported=self.today - timedelta(days=30))
        self._action(nc)
        self._action(nc, name='Second', deadline=self.today - timedelta(days=2))
        self._action(nc, name='Third').action_done()
        self.assertEqual(nc.action_count, 3)
        self.assertEqual(nc.open_action_count, 2)
        self.assertEqual(nc.overdue_action_count, 1)

    def test_display_name_includes_the_reference(self):
        nc = self._nc()
        self.assertIn(nc.code, nc.display_name)
        self.assertIn('Wrong labels', nc.display_name)
