# -*- coding: utf-8 -*-
"""Where the line is drawn, and where it deliberately is not.

Half of this module's value is what it leaves alone: a rule that refused
receipts, or refused everywhere, would be turned off within a day.
"""
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestNegativeStock(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.stock = self.env.ref('stock.stock_location_stock')
        self.customers = self.env.ref('stock.stock_location_customers')
        self.suppliers = self.env.ref('stock.stock_location_suppliers')
        self.shelf = self.env['stock.location'].create({
            'name': 'Shelf A', 'usage': 'internal', 'location_id': self.stock.id})
        self.category = self.env['product.category'].create({'name': 'Watched'})
        # 18.0 split storability out of the type: before it, a counted product
        # is type 'product'; from it, type 'consu' with is_storable set.
        self.storable = (
            {'type': 'consu', 'is_storable': True}
            if 'is_storable' in self.env['product.template']._fields
            else {'type': 'product'})
        self.product = self.env['product.product'].create(dict(
            self.storable, name='Counted Widget', categ_id=self.category.id))
        self.service = self.env['product.product'].create({
            'name': 'Advice', 'type': 'service'})

    def _rule(self, **values):
        return self.env['sl.negative.stock.rule'].create(dict({
            'name': 'Main stock must not go negative',
            'location_id': self.stock.id,
        }, **values))

    def _put(self, quantity, location=None):
        # The one way of putting stock on a shelf that reads the same on every
        # release; the inventory adjustment wizard does not.
        self.env['stock.quant']._update_available_quantity(
            self.product, location or self.stock, quantity)

    def _move(self, quantity, source=None, destination=None, product=None):
        values = {
            'product_id': (product or self.product).id,
            'product_uom_qty': quantity,
            'product_uom': (product or self.product).uom_id.id,
            'location_id': (source or self.stock).id,
            'location_dest_id': (destination or self.customers).id,
        }
        # Required up to 17.0, gone in 19.0, where the description is computed.
        if 'name' in self.env['stock.move']._fields:
            values['name'] = 'Test move'
        move = self.env['stock.move'].create(values)
        move._action_confirm()
        move._action_assign()
        field = 'quantity' if 'quantity' in move._fields else 'quantity_done'
        move.write({field: quantity})
        if 'picked' in move._fields:
            move.picked = True
        return move

    # -- refusing ----------------------------------------------------------

    def test_taking_more_than_is_there_is_refused(self):
        self._rule()
        self._put(5)
        move = self._move(8)
        with self.assertRaises(UserError):
            move._action_done()

    def test_taking_exactly_what_is_there_is_allowed(self):
        """The boundary: five out of five is not negative."""
        self._rule()
        self._put(5)
        move = self._move(5)
        move._action_done()
        self.assertEqual(move.state, 'done')

    def test_taking_less_is_allowed(self):
        self._rule()
        self._put(5)
        move = self._move(3)
        move._action_done()
        self.assertEqual(move.state, 'done')

    def test_the_refusal_says_what_and_where(self):
        self._rule()
        self._put(2)
        move = self._move(6)
        with self.assertRaises(UserError) as caught:
            move._action_done()
        message = str(caught.exception)
        self.assertIn('Counted Widget', message)
        self.assertIn('Main stock', message)

    # -- what is left alone ------------------------------------------------

    def test_without_a_rule_nothing_changes(self):
        """Odoo's own behaviour, untouched, is the default."""
        self._put(1)
        move = self._move(9)
        move._action_done()
        self.assertEqual(move.state, 'done')

    def test_a_receipt_is_never_refused(self):
        """Goods arriving are not coming off anybody's shelf."""
        self._rule()
        move = self._move(50, source=self.suppliers, destination=self.stock)
        move._action_done()
        self.assertEqual(move.state, 'done')

    def test_a_service_is_left_alone(self):
        self._rule()
        move = self._move(5, product=self.service)
        move._action_done()
        self.assertEqual(move.state, 'done')

    def test_a_rule_elsewhere_does_not_bind_here(self):
        other = self.env['stock.location'].create({
            'name': 'Other Warehouse', 'usage': 'internal'})
        self._rule(location_id=other.id)
        self._put(1)
        move = self._move(9)
        move._action_done()
        self.assertEqual(move.state, 'done')

    # -- where the rule reaches -------------------------------------------

    def test_a_rule_on_a_warehouse_covers_its_shelves(self):
        self._rule(include_children=True)
        self._put(2, location=self.shelf)
        move = self._move(5, source=self.shelf)
        with self.assertRaises(UserError):
            move._action_done()

    def test_it_can_be_told_not_to(self):
        self._rule(include_children=False)
        self._put(2, location=self.shelf)
        move = self._move(5, source=self.shelf)
        move._action_done()
        self.assertEqual(move.state, 'done')

    def test_a_rule_can_name_its_products(self):
        other = self.env['product.product'].create(
            dict(self.storable, name='Unwatched'))
        self._rule(product_ids=[(6, 0, self.product.ids)])
        move = self._move(5, product=other)
        move._action_done()
        self.assertEqual(move.state, 'done')

    def test_a_rule_can_name_a_category(self):
        self._rule(category_ids=[(6, 0, self.category.ids)])
        self._put(1)
        move = self._move(4)
        with self.assertRaises(UserError):
            move._action_done()

    # -- recording rather than refusing -----------------------------------

    def test_a_warning_rule_lets_it_through(self):
        """Right where going under is normal but worth knowing about."""
        self._rule(behaviour='warn')
        self._put(1)
        move = self._move(4)
        move._action_done()
        self.assertEqual(move.state, 'done')

    def test_a_warning_is_written_on_the_transfer(self):
        """Allowing it silently would be the same as not having the rule."""
        self._rule(behaviour='warn')
        self._put(1)
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': self.stock.id,
            'location_dest_id': self.customers.id,
        })
        move = self._move(4)
        move.picking_id = picking
        before = len(picking.message_ids)
        move._action_done()
        self.assertEqual(move.state, 'done')
        self.assertGreater(len(picking.message_ids), before)
        self.assertIn('Counted Widget', picking.message_ids[0].body)

    # -- which rule wins ---------------------------------------------------

    def test_the_first_rule_that_fits_is_the_one_applied(self):
        """Two rules about the same shelf is a question the order answers."""
        self._rule(name='Allowed here', behaviour='warn', sequence=1)
        self._rule(name='Refused here', behaviour='block', sequence=10)
        self._put(1)
        move = self._move(4)
        move._action_done()
        self.assertEqual(move.state, 'done')

    # -- the rules refuse nonsense ----------------------------------------

    def test_a_location_from_another_company_is_refused(self):
        other_company = self.env['res.company'].create({'name': 'Elsewhere Ltd'})
        location = self.env['stock.location'].create({
            'name': 'Their Shelf', 'usage': 'internal',
            'company_id': other_company.id})
        with self.assertRaises(ValidationError):
            self._rule(location_id=location.id)
