# -*- coding: utf-8 -*-
"""What the till is told about stock, checked against what stock says.

The point of the module is that the number shown in the point of sale is the
number in the locations that till actually sells from. So the tests put real
quants in real locations and ask the same question the till asks.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPosStock(TransactionCase):

    def setUp(self):
        super().setUp()
        self.warehouse = self.env['stock.location'].create({
            'name': 'Shop Floor', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_locations').id,
        })
        self.backroom = self.env['stock.location'].create({
            'name': 'Back Room', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_locations').id,
        })
        self.product = self.env['product.product'].create({
            'name': 'Counted Thing', 'type': 'product'})

    def _put(self, product, location, quantity):
        self.env['stock.quant'].create({
            'product_id': product.id,
            'location_id': location.id,
            'quantity': quantity,
        })

    def test_the_quantity_comes_from_the_named_locations(self):
        self._put(self.product, self.warehouse, 7)
        answer = self.env['product.product'].get_product_stock_for_pos(
            [self.product.id], [self.warehouse.id])
        self.assertEqual(answer[self.product.id], 7)

    def test_stock_somewhere_else_is_not_counted(self):
        """The whole reason the locations are configurable: a till must not
        promise what is sitting in another shop."""
        self._put(self.product, self.backroom, 12)
        answer = self.env['product.product'].get_product_stock_for_pos(
            [self.product.id], [self.warehouse.id])
        self.assertEqual(answer[self.product.id], 0)

    def test_several_locations_are_added_up(self):
        self._put(self.product, self.warehouse, 4)
        self._put(self.product, self.backroom, 6)
        answer = self.env['product.product'].get_product_stock_for_pos(
            [self.product.id], [self.warehouse.id, self.backroom.id])
        self.assertEqual(answer[self.product.id], 10)

    def test_a_product_with_no_stock_is_zero_not_missing(self):
        """The till reads the answer by product id, so a missing key is a crash
        rather than an out-of-stock product."""
        answer = self.env['product.product'].get_product_stock_for_pos(
            [self.product.id], [self.warehouse.id])
        self.assertEqual(answer, {self.product.id: 0})

    def test_a_service_is_never_out_of_stock(self):
        service = self.env['product.product'].create({
            'name': 'Gift Wrapping', 'type': 'service'})
        answer = self.env['product.product'].get_product_stock_for_pos(
            [service.id], [self.warehouse.id])
        self.assertEqual(answer, {service.id: 0})

    def test_asking_about_nothing_is_answered_not_refused(self):
        self.assertEqual(
            self.env['product.product'].get_product_stock_for_pos([], []), {})
        self.assertEqual(
            self.env['product.product'].get_product_stock_for_pos(
                [self.product.id], []),
            {self.product.id: 0})

    def test_turning_the_check_off_clears_the_locations(self):
        """Locations left behind on a till that no longer checks stock are the
        ones that come back wrong when it is switched on again."""
        config = self.env['pos.config'].new({
            'name': 'Test Till',
            'available_stock_location_ids': [(6, 0, [self.warehouse.id])],
            'enforce_pos_stock_check': True,
        })
        config.enforce_pos_stock_check = False
        config._onchange_enforce_pos_stock_check()
        self.assertFalse(config.available_stock_location_ids)
