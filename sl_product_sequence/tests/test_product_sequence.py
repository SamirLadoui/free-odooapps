# -*- coding: utf-8 -*-
"""Which number a product gets, and when it is left alone."""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestProductSequence(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.company.sl_product_sequence_id = False
        self.furniture = self.env['product.category'].create(
            {'name': 'Furniture'})
        self.chairs = self.env['product.category'].create(
            {'name': 'Office Chairs', 'parent_id': self.furniture.id})
        self.loose = self.env['product.category'].create({'name': 'Loose Ends'})

    def _sequence(self, prefix, padding=4):
        return self.env['ir.sequence'].create({
            'name': 'Test %s' % prefix, 'prefix': prefix,
            'padding': padding, 'number_next': 1, 'number_increment': 1,
            'company_id': False,
        })

    def _product(self, category=None, **values):
        return self.env['product.template'].create(dict({
            'name': 'A Product',
            'categ_id': (category or self.loose).id,
        }, **values))

    # -- where the number comes from ---------------------------------------

    def test_a_category_numbers_its_products(self):
        self.furniture.sl_sequence_id = self._sequence('FUR')
        product = self._product(self.furniture)
        self.assertEqual(product.default_code, 'FUR0001')

    def test_the_next_product_gets_the_next_number(self):
        self.furniture.sl_sequence_id = self._sequence('FUR')
        first = self._product(self.furniture)
        second = self._product(self.furniture)
        self.assertEqual(first.default_code, 'FUR0001')
        self.assertEqual(second.default_code, 'FUR0002')

    def test_a_child_category_inherits_from_its_parent(self):
        """One sequence on Furniture should cover everything beneath it."""
        self.furniture.sl_sequence_id = self._sequence('FUR')
        product = self._product(self.chairs)
        self.assertEqual(product.default_code, 'FUR0001')

    def test_a_child_with_its_own_numbering_uses_it(self):
        self.furniture.sl_sequence_id = self._sequence('FUR')
        self.chairs.sl_sequence_id = self._sequence('CHR')
        product = self._product(self.chairs)
        self.assertEqual(product.default_code, 'CHR0001')

    def test_the_company_covers_what_is_left(self):
        self.company.sl_product_sequence_id = self._sequence('GEN')
        product = self._product(self.loose)
        self.assertEqual(product.default_code, 'GEN0001')

    def test_a_category_beats_the_company(self):
        self.company.sl_product_sequence_id = self._sequence('GEN')
        self.furniture.sl_sequence_id = self._sequence('FUR')
        self.assertEqual(self._product(self.furniture).default_code, 'FUR0001')
        self.assertEqual(self._product(self.loose).default_code, 'GEN0001')

    # -- when nothing happens ----------------------------------------------

    def test_with_no_numbering_anywhere_nothing_changes(self):
        """Installing it must not start renaming things on its own."""
        product = self._product(self.loose)
        self.assertFalse(product.default_code)

    def test_a_reference_typed_in_is_kept(self):
        """A manufacturer's part number is worth more than one we invented."""
        self.furniture.sl_sequence_id = self._sequence('FUR')
        product = self._product(self.furniture, default_code='MFR-99-X')
        self.assertEqual(product.default_code, 'MFR-99-X')

    def test_a_typed_reference_does_not_burn_a_number(self):
        self.furniture.sl_sequence_id = self._sequence('FUR')
        self._product(self.furniture, default_code='MFR-99-X')
        self.assertEqual(self._product(self.furniture).default_code, 'FUR0001')

    # -- the products already there ----------------------------------------

    def _wizard(self, templates):
        return self.env['sl.product.reference.wizard'].with_context(
            active_model='product.template', active_ids=templates.ids,
        ).create({})

    def test_existing_products_can_be_numbered_afterwards(self):
        blank = self._product(self.furniture)
        self.assertFalse(blank.default_code)
        self.furniture.sl_sequence_id = self._sequence('FUR')
        self._wizard(blank).action_assign()
        self.assertEqual(blank.default_code, 'FUR0001')

    def test_the_wizard_skips_the_ones_that_have_one(self):
        kept = self._product(self.furniture, default_code='MFR-1')
        blank = self._product(self.loose)
        self.company.sl_product_sequence_id = self._sequence('GEN')
        self._wizard(kept | blank).action_assign()
        self.assertEqual(kept.default_code, 'MFR-1')
        self.assertEqual(blank.default_code, 'GEN0001')

    def test_the_wizard_counts_what_it_will_touch(self):
        """Both created before the numbering exists, or the blank one would
        not be blank: creating a product is exactly when it gets numbered."""
        kept = self._product(self.furniture, default_code='MFR-1')
        blank = self._product(self.furniture)
        self.assertFalse(blank.default_code)
        self.furniture.sl_sequence_id = self._sequence('FUR')
        wizard = self._wizard(kept | blank)
        self.assertEqual(wizard.product_count, 2)
        self.assertEqual(wizard.todo_count, 1)

    def test_nothing_to_do_is_said_rather_than_done_silently(self):
        self.furniture.sl_sequence_id = self._sequence('FUR')
        product = self._product(self.furniture, default_code='MFR-1')
        with self.assertRaises(UserError):
            self._wizard(product).action_assign()

    def test_without_numbering_the_wizard_says_so(self):
        blank = self._product(self.loose)
        with self.assertRaises(UserError):
            self._wizard(blank).action_assign()

    def test_selecting_variants_reaches_their_templates(self):
        self.furniture.sl_sequence_id = self._sequence('FUR')
        blank = self._product(self.furniture)
        blank.default_code = False
        variant = blank.product_variant_ids[0]
        wizard = self.env['sl.product.reference.wizard'].with_context(
            active_model='product.product', active_ids=variant.ids,
        ).create({})
        wizard.action_assign()
        self.assertTrue(blank.default_code)
