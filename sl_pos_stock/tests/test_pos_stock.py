# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPosStock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search([], limit=1)
        cls.shelf = cls.warehouse.lot_stock_id
        cls.other_location = cls.env['stock.location'].create({
            'name': 'Far Away Shelf', 'usage': 'internal',
            'location_id': cls.warehouse.view_location_id.id})

        storable = ({'is_storable': True, 'type': 'consu'}
                    if 'is_storable' in cls.env['product.product']._fields
                    else {'type': 'product'})
        cls.widget = cls.env['product.product'].create(
            dict(storable, name='POS Widget', available_in_pos=True))
        cls.service = cls.env['product.product'].create({
            'name': 'POS Service', 'type': 'service', 'available_in_pos': True})

        cls.env['stock.quant']._update_available_quantity(cls.widget, cls.shelf, 7)
        cls.env['stock.quant']._update_available_quantity(
            cls.widget, cls.other_location, 5)

        cls.config = cls.env['pos.config'].create({
            'name': 'Stock Checked POS',
            'enforce_pos_stock_check': True,
            'available_stock_location_ids': [(6, 0, cls.shelf.ids)],
        })

    # -- the stock query, which is the whole point -------------------------

    def test_quantity_comes_from_the_chosen_location(self):
        result = self.env['product.product'].get_product_stock_for_pos(
            [self.widget.id], self.shelf.ids)
        self.assertEqual(result[self.widget.id], 7)

    def test_stock_elsewhere_is_not_counted(self):
        """A POS that counts its own shelf must not see the far warehouse."""
        result = self.env['product.product'].get_product_stock_for_pos(
            [self.widget.id], self.shelf.ids)
        self.assertEqual(result[self.widget.id], 7, "the other 5 are elsewhere")

    def test_several_locations_are_summed(self):
        result = self.env['product.product'].get_product_stock_for_pos(
            [self.widget.id], (self.shelf | self.other_location).ids)
        self.assertEqual(result[self.widget.id], 12)

    def test_every_requested_id_is_answered(self):
        """The caller should never have to guess whether a missing key is zero."""
        missing = self.env['product.product'].create({'name': 'Never Stocked'})
        result = self.env['product.product'].get_product_stock_for_pos(
            [self.widget.id, missing.id], self.shelf.ids)
        self.assertIn(missing.id, result)
        self.assertEqual(result[missing.id], 0)

    def test_services_report_zero_not_an_error(self):
        result = self.env['product.product'].get_product_stock_for_pos(
            [self.service.id], self.shelf.ids)
        self.assertEqual(result[self.service.id], 0)

    def test_no_locations_gives_zero_for_everything(self):
        result = self.env['product.product'].get_product_stock_for_pos(
            [self.widget.id], [])
        self.assertEqual(result[self.widget.id], 0)

    def test_empty_product_list_is_harmless(self):
        self.assertEqual(
            self.env['product.product'].get_product_stock_for_pos([], self.shelf.ids), {})

    def test_deleted_product_does_not_break_the_call(self):
        victim = self.env['product.product'].create({'name': 'Doomed'})
        victim_id = victim.id
        victim.unlink()
        result = self.env['product.product'].get_product_stock_for_pos(
            [self.widget.id, victim_id], self.shelf.ids)
        self.assertEqual(result[victim_id], 0)
        self.assertEqual(result[self.widget.id], 7)

    def test_quantity_follows_a_movement(self):
        self.env['stock.quant']._update_available_quantity(self.widget, self.shelf, -3)
        result = self.env['product.product'].get_product_stock_for_pos(
            [self.widget.id], self.shelf.ids)
        self.assertEqual(result[self.widget.id], 4)

    # -- configuration guards ----------------------------------------------

    def test_enforcing_without_locations_is_refused(self):
        """Otherwise every product reads as out of stock and the module looks broken."""
        with self.assertRaises(ValidationError):
            self.env['pos.config'].create({
                'name': 'Misconfigured POS',
                'enforce_pos_stock_check': True,
            })

    def test_removing_the_last_location_is_refused(self):
        with self.assertRaises(ValidationError):
            self.config.available_stock_location_ids = [(5, 0, 0)]

    def test_turning_the_check_off_allows_no_locations(self):
        self.config.write({
            'enforce_pos_stock_check': False,
            'available_stock_location_ids': [(5, 0, 0)],
        })
        self.assertFalse(self.config.available_stock_location_ids)

    def test_enabling_the_check_keeps_the_locations(self):
        """The original wiped them on every change, including when enabling."""
        self.config.enforce_pos_stock_check = False
        self.config.available_stock_location_ids = [(6, 0, self.shelf.ids)]
        self.config.enforce_pos_stock_check = True
        self.config._onchange_enforce_pos_stock_check()
        self.assertEqual(self.config.available_stock_location_ids, self.shelf)

    def test_disabling_the_check_clears_the_locations(self):
        self.config.enforce_pos_stock_check = False
        self.config._onchange_enforce_pos_stock_check()
        self.assertFalse(self.config.available_stock_location_ids)

    def test_only_internal_locations_are_offered(self):
        field = self.env['pos.config']._fields['available_stock_location_ids']
        self.assertIn('internal', str(field.domain))
