# -*- coding: utf-8 -*-
import psycopg2

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestProductBrand(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.brand = cls.env['sl.product.brand'].create({'name': 'Acme', 'code': 'ACM'})
        cls.product = cls.env['product.template'].create({
            'name': 'Acme Anvil', 'sl_brand_id': cls.brand.id})

    def test_brand_reaches_the_variant(self):
        variant = self.product.product_variant_ids[0]
        self.assertEqual(variant.sl_brand_id, self.brand)

    def test_product_count(self):
        self.assertEqual(self.brand.product_count, 1)
        self.env['product.template'].create({
            'name': 'Acme Rocket', 'sl_brand_id': self.brand.id})
        self.assertEqual(self.brand.product_count, 2)

    def test_names_are_unique(self):
        """The same brand typed twice quietly splits your reporting."""
        with self.assertRaises(ValidationError):
            self.env['sl.product.brand'].create({'name': 'acme'})

    def test_codes_are_unique(self):
        with self.assertRaises(ValidationError):
            self.env['sl.product.brand'].create({'name': 'Other', 'code': 'acm'})

    def test_a_brand_without_a_code_is_fine(self):
        self.assertTrue(self.env['sl.product.brand'].create({'name': 'No Code'}))

    def test_two_brands_without_codes_are_fine(self):
        self.env['sl.product.brand'].create({'name': 'First No Code'})
        self.assertTrue(self.env['sl.product.brand'].create({'name': 'Second No Code'}))

    @mute_logger('odoo.sql_db')
    def test_a_brand_in_use_cannot_be_deleted(self):
        """Historical orders must keep meaning what they meant."""
        with self.assertRaises(psycopg2.IntegrityError):
            with self.cr.savepoint():
                self.brand.unlink()

    def test_an_unused_brand_can_be_deleted(self):
        spare = self.env['sl.product.brand'].create({'name': 'Unused'})
        spare.unlink()
        self.assertFalse(spare.exists())

    def test_products_action_is_filtered(self):
        action = self.brand.action_view_products()
        self.assertEqual(action['res_model'], 'product.template')
        self.assertIn(('sl_brand_id', '=', self.brand.id), action['domain'])
