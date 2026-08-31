# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSaleRental(TransactionCase):

    def setUp(self):
        # 14.0 has no class-level env: setUpClass cannot build fixtures.
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Rental Customer'})
        self.drill = self.env['product.product'].create({
            'name': 'Hire Drill', 'type': 'consu',
            'sl_rentable': True, 'sl_rental_units': 2,
            'sl_rental_price_day': 10.0,
            'sl_rental_price_week': 60.0,
            'sl_rental_price_month': 200.0,
        })
        self.daily_only = self.env['product.product'].create({
            'name': 'Daily Only', 'type': 'consu',
            'sl_rentable': True, 'sl_rental_price_day': 5.0})
        self.not_rentable = self.env['product.product'].create({
            'name': 'Sale Only', 'type': 'consu'})
        self.start = date(2026, 6, 1)

    def _order(self, **line_values):
        order = self.env['sale.order'].create({'partner_id': self.partner.id})
        self.env['sale.order.line'].create(dict({
            'order_id': order.id,
            'product_id': self.drill.id,
            'product_uom_qty': 1,
            'sl_is_rental': True,
            'sl_rental_start': self.start,
            'sl_rental_return': self.start + timedelta(days=2),
        }, **line_values))
        return order

    # -- pricing -----------------------------------------------------------

    def test_days_use_the_daily_rate(self):
        self.assertAlmostEqual(self.drill._rental_price_for(3), 30.0, places=2)

    def test_a_week_uses_the_weekly_rate(self):
        """Seven days at the week rate, not seven times the day rate."""
        self.assertAlmostEqual(self.drill._rental_price_for(7), 60.0, places=2)

    def test_a_month_uses_the_monthly_rate(self):
        self.assertAlmostEqual(self.drill._rental_price_for(30), 200.0, places=2)

    def test_mixed_periods(self):
        # 38 days = 1 month (200) + 1 week (60) + 1 day (10)
        self.assertAlmostEqual(self.drill._rental_price_for(38), 270.0, places=2)

    def test_a_block_may_overshoot_when_it_is_cheaper(self):
        """29 days greedily costs 4 weeks + a day = 250, but a month is 200.
        Charging more for less time is a bug customers notice."""
        self.assertAlmostEqual(self.drill._rental_price_for(29), 200.0, places=2)
        self.assertAlmostEqual(self.drill._rental_price_for(6), 60.0, places=2)

    def test_a_longer_hire_is_never_dearer_than_a_shorter_one(self):
        for days in range(1, 60):
            self.assertLessEqual(
                self.drill._rental_price_for(days),
                self.drill._rental_price_for(days + 1) + 0.001,
                'price went down between %s and %s days' % (days, days + 1))

    def test_a_product_with_only_a_daily_rate(self):
        self.assertAlmostEqual(self.daily_only._rental_price_for(10), 50.0, places=2)

    def test_zero_days_costs_nothing(self):
        self.assertEqual(self.drill._rental_price_for(0), 0.0)

    def test_a_remainder_with_no_daily_rate_is_still_charged(self):
        """Nothing goes out free because a rate happens to be missing."""
        weekly = self.env['product.product'].create({
            'name': 'Weekly Only', 'type': 'consu',
            'sl_rentable': True, 'sl_rental_price_week': 70.0})
        self.assertGreater(weekly._rental_price_for(9), 70.0)

    # -- duration ----------------------------------------------------------

    def test_both_ends_are_inclusive(self):
        """Out and back the same day is one day's hire, not zero."""
        order = self._order(sl_rental_return=self.start)
        self.assertEqual(order.order_line.sl_rental_days, 1)

    def test_three_day_hire(self):
        order = self._order()
        self.assertEqual(order.order_line.sl_rental_days, 3)

    def test_a_non_rental_line_has_no_days(self):
        order = self.env['sale.order'].create({'partner_id': self.partner.id})
        line = self.env['sale.order.line'].create({
            'order_id': order.id, 'product_id': self.not_rentable.id,
            'product_uom_qty': 1})
        self.assertEqual(line.sl_rental_days, 0)

    # -- guards ------------------------------------------------------------

    def test_returning_before_collection_is_refused(self):
        with self.assertRaises(ValidationError):
            self._order(sl_rental_return=self.start - timedelta(days=1))

    def test_a_rental_line_needs_both_dates(self):
        with self.assertRaises(ValidationError):
            self._order(sl_rental_return=False)

    def test_a_product_that_is_not_rentable_is_refused(self):
        with self.assertRaises(ValidationError):
            self._order(product_id=self.not_rentable.id)

    def test_a_rentable_product_needs_a_price(self):
        with self.assertRaises(ValidationError):
            self.env['product.product'].create({
                'name': 'Priceless', 'type': 'consu', 'sl_rentable': True})

    def test_negative_rental_prices_are_refused(self):
        with self.assertRaises(ValidationError):
            self.drill.sl_rental_price_day = -1

    def test_a_rentable_product_needs_at_least_one_unit(self):
        with self.assertRaises(ValidationError):
            self.drill.sl_rental_units = 0

    # -- availability ------------------------------------------------------

    def test_quotations_do_not_hold_stock(self):
        """One abandoned draft must not block the item forever."""
        self._order(product_uom_qty=2)
        self.assertEqual(
            self.drill._rented_quantity_between(
                self.start, self.start + timedelta(days=2)),
            0, "a draft order holds nothing")

    def test_a_confirmed_order_holds_its_units(self):
        order = self._order(product_uom_qty=2)
        order.action_confirm()
        self.assertEqual(
            self.drill._rented_quantity_between(
                self.start, self.start + timedelta(days=2)),
            2)

    def test_booking_past_the_units_owned_is_refused(self):
        first = self._order(product_uom_qty=2)
        first.action_confirm()
        second = self._order(product_uom_qty=1)
        with self.assertRaises(ValidationError):
            second.action_confirm()

    def test_a_later_window_is_free(self):
        first = self._order(product_uom_qty=2)
        first.action_confirm()
        later = self._order(
            product_uom_qty=2,
            sl_rental_start=self.start + timedelta(days=10),
            sl_rental_return=self.start + timedelta(days=12))
        later.action_confirm()
        self.assertEqual(later.state, 'sale')

    def test_partial_availability_is_allowed(self):
        first = self._order(product_uom_qty=1)
        first.action_confirm()
        second = self._order(product_uom_qty=1)
        second.action_confirm()
        self.assertEqual(second.state, 'sale')

    def test_the_rental_line_count(self):
        order = self._order()
        self.assertEqual(order.sl_rental_line_count, 1)
