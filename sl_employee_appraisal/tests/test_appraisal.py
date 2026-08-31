# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAppraisal(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env['hr.employee'].create({'name': 'The Manager'})
        cls.employee = cls.env['hr.employee'].create({
            'name': 'The Employee', 'parent_id': cls.manager.id})
        cls.category = cls.env['sl.appraisal.category'].create({'name': 'Delivery'})
        cls.light = cls.env['sl.appraisal.criteria'].create({
            'name': 'Punctuality', 'category_id': cls.category.id, 'weight': 1.0})
        cls.heavy = cls.env['sl.appraisal.criteria'].create({
            'name': 'Quality', 'category_id': cls.category.id, 'weight': 3.0})

    def _appraisal(self, **values):
        return self.env['sl.appraisal'].create(dict({
            'employee_id': self.employee.id,
            'date_start': date(2026, 1, 1),
            'date_end': date(2026, 6, 30),
        }, **values))

    def _rate(self, appraisal, criterion, rating):
        line = appraisal.line_ids.filtered(lambda l: l.criteria_id == criterion)
        line.rating = rating
        return line

    # -- scoring, which is the whole point ---------------------------------

    def test_score_is_weighted_not_averaged(self):
        """Quality counts three times as much as punctuality."""
        appraisal = self._appraisal()
        appraisal.action_start()
        self._rate(appraisal, self.light, '1')
        self._rate(appraisal, self.heavy, '5')
        # (1*1 + 5*3) / 4 = 4.0, where a plain average would be 3.0
        self.assertAlmostEqual(appraisal.score, 4.0, places=4)

    def test_score_as_a_percentage(self):
        appraisal = self._appraisal()
        appraisal.action_start()
        self._rate(appraisal, self.light, '5')
        self._rate(appraisal, self.heavy, '5')
        self.assertAlmostEqual(appraisal.score, 5.0, places=4)
        self.assertAlmostEqual(appraisal.score_percent, 100.0, places=4)

    def test_unrated_criteria_are_ignored_not_counted_as_zero(self):
        """A half-finished appraisal should not read as a bad one."""
        appraisal = self._appraisal()
        appraisal.action_start()
        self._rate(appraisal, self.heavy, '4')
        self.assertAlmostEqual(appraisal.score, 4.0, places=4)
        self.assertEqual(appraisal.rated_count, 1)

    def test_empty_appraisal_scores_zero(self):
        appraisal = self._appraisal()
        self.assertEqual(appraisal.score, 0.0)
        self.assertEqual(appraisal.rated_count, 0)

    def test_score_updates_when_a_rating_changes(self):
        appraisal = self._appraisal()
        appraisal.action_start()
        line = self._rate(appraisal, self.heavy, '2')
        self.assertAlmostEqual(appraisal.score, 2.0, places=4)
        line.rating = '5'
        self.assertAlmostEqual(appraisal.score, 5.0, places=4)

    def test_line_weight_can_override_the_criterion(self):
        appraisal = self._appraisal()
        appraisal.action_start()
        self._rate(appraisal, self.light, '1')
        heavy_line = self._rate(appraisal, self.heavy, '5')
        heavy_line.weight = 1.0
        self.assertAlmostEqual(appraisal.score, 3.0, places=4)

    # -- loading criteria ---------------------------------------------------

    def test_start_loads_every_criterion(self):
        appraisal = self._appraisal()
        appraisal.action_start()
        self.assertEqual(len(appraisal.line_ids), 2)
        self.assertEqual(set(appraisal.line_ids.mapped('criteria_id')),
                         {self.light, self.heavy})

    def test_lines_take_the_criterion_weight(self):
        appraisal = self._appraisal()
        appraisal.action_start()
        heavy_line = appraisal.line_ids.filtered(lambda l: l.criteria_id == self.heavy)
        self.assertEqual(heavy_line.weight, 3.0)

    def test_loading_again_does_not_duplicate(self):
        appraisal = self._appraisal()
        appraisal.action_start()
        appraisal.action_load_criteria()
        self.assertEqual(len(appraisal.line_ids), 2)

    def test_loading_picks_up_new_criteria_only(self):
        appraisal = self._appraisal()
        appraisal.action_start()
        self.env['sl.appraisal.criteria'].create({
            'name': 'Teamwork', 'category_id': self.category.id, 'weight': 2.0})
        appraisal.action_load_criteria()
        self.assertEqual(len(appraisal.line_ids), 3)

    def test_a_criterion_cannot_appear_twice(self):
        appraisal = self._appraisal()
        appraisal.action_start()
        with self.assertRaises(ValidationError):
            appraisal.line_ids = [(0, 0, {'criteria_id': self.light.id, 'weight': 1.0})]

    # -- workflow -----------------------------------------------------------

    def test_cannot_complete_with_unrated_criteria(self):
        appraisal = self._appraisal()
        appraisal.action_start()
        self._rate(appraisal, self.light, '3')
        with self.assertRaises(ValidationError):
            appraisal.action_done()

    def test_completing_stamps_the_date(self):
        appraisal = self._appraisal()
        appraisal.action_start()
        self._rate(appraisal, self.light, '3')
        self._rate(appraisal, self.heavy, '4')
        appraisal.action_done()
        self.assertEqual(appraisal.state, 'done')
        self.assertTrue(appraisal.date_close)

    def test_cancel_and_reset(self):
        appraisal = self._appraisal()
        appraisal.action_cancel()
        self.assertEqual(appraisal.state, 'cancelled')
        appraisal.action_reset_to_draft()
        self.assertEqual(appraisal.state, 'draft')

    # -- guards -------------------------------------------------------------

    def test_period_must_be_in_order(self):
        with self.assertRaises(ValidationError):
            self._appraisal(date_start=date(2026, 7, 1), date_end=date(2026, 1, 1))

    def test_overlapping_appraisals_are_refused(self):
        """One appraisal per employee per period, or the history stops meaning
        anything."""
        self._appraisal()
        with self.assertRaises(ValidationError):
            self._appraisal(date_start=date(2026, 3, 1), date_end=date(2026, 9, 30))

    def test_adjacent_periods_are_fine(self):
        self._appraisal()
        later = self._appraisal(date_start=date(2026, 7, 1), date_end=date(2026, 12, 31))
        self.assertTrue(later)

    def test_a_cancelled_appraisal_frees_the_period(self):
        first = self._appraisal()
        first.action_cancel()
        self.assertTrue(self._appraisal())

    def test_another_employee_can_share_the_period(self):
        self._appraisal()
        other = self.env['hr.employee'].create({'name': 'Someone Else'})
        self.assertTrue(self._appraisal(employee_id=other.id))

    def test_criteria_weight_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self.env['sl.appraisal.criteria'].create({
                'name': 'Weightless', 'category_id': self.category.id, 'weight': 0})

    # -- conveniences -------------------------------------------------------

    def test_reference_is_generated(self):
        self.assertTrue(self._appraisal().code.startswith('APR/'))

    def test_manager_defaults_from_the_employee(self):
        appraisal = self.env['sl.appraisal'].new({'employee_id': self.employee.id})
        appraisal._onchange_employee_id()
        self.assertEqual(appraisal.manager_id, self.manager)

    def test_employee_rollup(self):
        appraisal = self._appraisal()
        appraisal.action_start()
        self._rate(appraisal, self.light, '4')
        self._rate(appraisal, self.heavy, '4')
        appraisal.action_done()
        self.assertEqual(self.employee.appraisal_count, 1)
        self.assertAlmostEqual(self.employee.last_appraisal_score, 4.0, places=4)
