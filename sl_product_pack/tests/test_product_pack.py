# -*- coding: utf-8 -*-
"""What ends up on the order, and what ends up in the warehouse's hands."""
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestProductPack(TransactionCase):

    def setUp(self):
        super().setUp()
        self.warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)
        self.storable = ({'type': 'consu', 'is_storable': True}
                         if 'is_storable' in self.env['product.template']._fields
                         else {'type': 'product'})
        self.mug = self.part('Mug', 4.0)
        self.spoon = self.part('Spoon', 1.5)
        self.customer = self.env['res.partner'].create({'name': 'Buyer Ltd'})
        self.kit = self.pack('Breakfast Kit', 10.0, [(self.mug, 1), (self.spoon, 2)])

    def part(self, name, price):
        return self.env['product.product'].create(
            dict(self.storable, name=name, list_price=price))

    def pack(self, name, price, contents, pack_type='fixed'):
        return self.env['product.product'].create({
            'name': name,
            'type': 'service',
            'list_price': price,
            'sl_pack_ok': True,
            'sl_pack_type': pack_type,
            'sl_pack_line_ids': [
                (0, 0, {'product_id': product.id, 'quantity': quantity})
                for product, quantity in contents],
        })

    def order(self, product, quantity=1):
        return self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [(0, 0, {'product_id': product.id,
                                   'product_uom_qty': quantity})],
        })

    def parts_of(self, sale):
        return sale.order_line.filtered(lambda l: l.sl_pack_parent_id)

    # -- what lands on the order -------------------------------------------

    def test_confirming_puts_the_parts_on_the_order(self):
        sale = self.order(self.kit)
        sale.action_confirm()
        self.assertEqual(set(self.parts_of(sale).mapped('product_id')),
                         {self.mug, self.spoon})

    def test_a_quotation_still_reads_the_way_it_was_sold(self):
        """The parts arrive at confirmation, not while it is being typed."""
        sale = self.order(self.kit)
        self.assertEqual(len(sale.order_line), 1)
        self.assertFalse(self.parts_of(sale))

    def test_the_quantities_are_multiplied_out(self):
        sale = self.order(self.kit, quantity=3)
        sale.action_confirm()
        quantities = {line.product_id: line.product_uom_qty
                      for line in self.parts_of(sale)}
        self.assertEqual(quantities[self.mug], 3)
        self.assertEqual(quantities[self.spoon], 6)

    def test_each_part_knows_which_pack_it_came_from(self):
        sale = self.order(self.kit)
        sale.action_confirm()
        pack_line = sale.order_line.filtered(
            lambda l: l.product_id == self.kit)
        self.assertEqual(set(self.parts_of(sale).mapped('sl_pack_parent_id')),
                         {pack_line})
        self.assertEqual(len(pack_line.sl_pack_child_ids), 2)

    def test_it_can_be_done_before_confirming_from_a_button(self):
        sale = self.order(self.kit)
        sale.action_sl_explode_packs()
        self.assertEqual(len(self.parts_of(sale)), 2)
        self.assertEqual(sale.state, 'draft')

    # -- pricing -----------------------------------------------------------

    def test_one_price_for_the_pack_leaves_the_parts_at_nothing(self):
        sale = self.order(self.kit)
        sale.action_confirm()
        pack_line = sale.order_line.filtered(
            lambda l: l.product_id == self.kit)
        self.assertEqual(pack_line.price_unit, 10.0)
        self.assertEqual(set(self.parts_of(sale).mapped('price_unit')), {0.0})

    def test_the_total_is_the_pack_price_and_nothing_more(self):
        sale = self.order(self.kit)
        sale.action_confirm()
        self.assertEqual(sale.amount_untaxed, 10.0)

    def test_priced_line_by_line_charges_for_the_parts(self):
        detailed = self.pack('Detailed Kit', 99.0,
                             [(self.mug, 1), (self.spoon, 2)],
                             pack_type='detailed')
        sale = self.order(detailed)
        sale.action_confirm()
        pack_line = sale.order_line.filtered(
            lambda l: l.product_id == detailed)
        self.assertEqual(pack_line.price_unit, 0.0)
        prices = {line.product_id: line.price_unit
                  for line in self.parts_of(sale)}
        self.assertEqual(prices[self.mug], 4.0)
        self.assertEqual(prices[self.spoon], 1.5)
        # one mug at 4.00 and two spoons at 1.50
        self.assertEqual(sale.amount_untaxed, 7.0)

    # -- done once ---------------------------------------------------------

    def test_exploding_twice_does_not_double_the_contents(self):
        """An order cancelled and confirmed again must not ship two kits."""
        sale = self.order(self.kit)
        sale.action_confirm()
        sale.action_sl_explode_packs()
        self.assertEqual(len(self.parts_of(sale)), 2)

    def test_a_cancelled_and_reconfirmed_order_keeps_one_set_of_parts(self):
        sale = self.order(self.kit)
        sale.action_confirm()
        sale._action_cancel()
        sale.action_draft()
        sale.action_confirm()
        self.assertEqual(len(self.parts_of(sale)), 2)

    # -- what is left alone ------------------------------------------------

    def test_an_ordinary_product_is_untouched(self):
        sale = self.order(self.mug, quantity=2)
        sale.action_confirm()
        self.assertEqual(len(sale.order_line), 1)
        self.assertFalse(self.parts_of(sale))

    def test_an_order_with_both_only_explodes_the_pack(self):
        sale = self.order(self.mug)
        self.env['sale.order.line'].create({
            'order_id': sale.id, 'product_id': self.kit.id,
            'product_uom_qty': 1})
        sale.action_confirm()
        self.assertEqual(len(self.parts_of(sale)), 2)
        self.assertEqual(len(sale.order_line), 4)

    # -- the warehouse -----------------------------------------------------

    def test_the_delivery_holds_the_parts_and_not_the_pack(self):
        """The whole point: pickers pick things that exist."""
        sale = self.order(self.kit)
        sale.action_confirm()
        picking = sale.picking_ids
        self.assertTrue(picking)
        moves = (picking.move_ids if 'move_ids' in picking._fields
                 else picking.move_lines)
        self.assertEqual(set(moves.mapped('product_id')),
                         {self.mug, self.spoon})
        self.assertNotIn(self.kit, moves.mapped('product_id'))

    def test_the_delivery_quantities_follow_the_pack_quantity(self):
        sale = self.order(self.kit, quantity=2)
        sale.action_confirm()
        moves = (sale.picking_ids.move_ids
                 if 'move_ids' in sale.picking_ids._fields
                 else sale.picking_ids.move_lines)
        quantities = {move.product_id: move.product_uom_qty for move in moves}
        self.assertEqual(quantities[self.mug], 2)
        self.assertEqual(quantities[self.spoon], 4)

    # -- what the rules refuse ---------------------------------------------

    def test_a_counted_product_cannot_be_a_pack(self):
        """Counted, it would reserve itself and its contents at once."""
        with self.assertRaises(ValidationError):
            self.env['product.product'].create(dict(
                self.storable, name='Bad Kit', sl_pack_ok=True,
                sl_pack_line_ids=[(0, 0, {'product_id': self.mug.id,
                                          'quantity': 1})]))

    def test_a_pack_with_nothing_in_it_is_refused(self):
        with self.assertRaises(ValidationError):
            self.env['product.product'].create({
                'name': 'Empty Kit', 'type': 'service', 'sl_pack_ok': True})

    def test_a_part_with_no_quantity_is_refused(self):
        with self.assertRaises(ValidationError):
            self.pack('Zero Kit', 5.0, [(self.mug, 0)])

    def test_a_pack_cannot_go_inside_a_pack(self):
        """Otherwise a pack can eventually contain itself."""
        with self.assertRaises(ValidationError):
            self.pack('Kit Of Kits', 20.0, [(self.kit, 1)])

    def test_emptying_a_pack_that_is_in_use_is_refused(self):
        with self.assertRaises(ValidationError):
            self.kit.product_tmpl_id.sl_pack_line_ids = [(5, 0, 0)]
