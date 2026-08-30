# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPosReturn(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env['pos.config'].create({'name': 'Return Till'})
        cls.product = cls.env['product.product'].create({
            'name': 'Returnable Thing', 'available_in_pos': True,
            'list_price': 25.0, 'taxes_id': False})
        cls.other = cls.env['product.product'].create({
            'name': 'Other Thing', 'available_in_pos': True,
            'list_price': 10.0, 'taxes_id': False})
        cls.partner = cls.env['res.partner'].create({'name': 'Return Customer'})
        cls.config.open_ui()
        cls.session = cls.config.current_session_id

    def _order(self, lines, reference='Order 0001-0001-0001', **values):
        """A paid order, written the way the point of sale writes one."""
        order_lines = [(0, 0, {
            'product_id': product.id,
            'qty': qty,
            'price_unit': product.list_price,
            'price_subtotal': product.list_price * qty,
            'price_subtotal_incl': product.list_price * qty,
        }) for product, qty in lines]
        total = sum(p.list_price * q for p, q in lines)
        return self.env['pos.order'].create(dict({
            'session_id': self.session.id,
            # A real order gets a name from the session sequence; without one
            # every fixture would sit at '/' and match every other lookup.
            'name': 'POS/%s' % reference,
            'partner_id': self.partner.id,
            'pos_reference': reference,
            'amount_tax': 0.0,
            'amount_total': total,
            'amount_paid': total,
            'amount_return': 0.0,
            'lines': order_lines,
            'state': 'paid',
        }, **values))

    # -- finding the order -------------------------------------------------

    def test_an_order_is_found_by_its_receipt_reference(self):
        order = self._order([(self.product, 2)], reference='Order 0007')
        payload = self.env['pos.order'].sl_find_returnable('Order 0007')
        self.assertEqual(payload['order_id'], order.id)

    def test_an_order_is_found_by_its_name(self):
        order = self._order([(self.product, 2)])
        payload = self.env['pos.order'].sl_find_returnable(order.name)
        self.assertEqual(payload['order_id'], order.id)

    def test_surrounding_spaces_are_ignored(self):
        order = self._order([(self.product, 1)], reference='Order 0009')
        payload = self.env['pos.order'].sl_find_returnable('  Order 0009  ')
        self.assertEqual(payload['order_id'], order.id)

    def test_an_empty_reference_is_refused(self):
        for bad in ('', '   ', None):
            with self.assertRaises(UserError):
                self.env['pos.order'].sl_find_returnable(bad)

    def test_an_unknown_reference_is_refused(self):
        with self.assertRaises(UserError):
            self.env['pos.order'].sl_find_returnable('no-such-receipt')

    def test_an_unpaid_order_is_not_returnable(self):
        self._order([(self.product, 1)], reference='Draft 1', state='draft')
        with self.assertRaises(UserError):
            self.env['pos.order'].sl_find_returnable('Draft 1')

    # -- what is left to return -------------------------------------------

    def test_everything_is_returnable_at_first(self):
        self._order([(self.product, 4)], reference='R1')
        payload = self.env['pos.order'].sl_find_returnable('R1')
        line = payload['lines'][0]
        self.assertEqual(line['qty_sold'], 4)
        self.assertEqual(line['qty_returned'], 0)
        self.assertEqual(line['qty_returnable'], 4)

    def test_a_partial_return_leaves_the_rest(self):
        original = self._order([(self.product, 5)], reference='R2')
        self._return(original, [(self.product, 3)])
        payload = self.env['pos.order'].sl_find_returnable('R2')
        line = payload['lines'][0]
        self.assertEqual(line['qty_returned'], 3)
        self.assertEqual(line['qty_returnable'], 2)

    def test_returns_accumulate_across_visits(self):
        """Three back today and two next week is five, not five each time."""
        original = self._order([(self.product, 5)], reference='R3')
        self._return(original, [(self.product, 3)])
        self._return(original, [(self.product, 2)])
        payload = self.env['pos.order'].sl_find_returnable('R3')
        self.assertEqual(payload['lines'], [],
                         'a fully returned order still offers lines')

    def test_a_fully_returned_line_is_not_offered(self):
        original = self._order([(self.product, 2), (self.other, 1)],
                               reference='R4')
        self._return(original, [(self.product, 2)])
        payload = self.env['pos.order'].sl_find_returnable('R4')
        products = [l['product_id'] for l in payload['lines']]
        self.assertNotIn(self.product.id, products)
        self.assertIn(self.other.id, products)

    def test_the_returned_quantity_is_readable_on_the_line(self):
        original = self._order([(self.product, 4)], reference='R5')
        self._return(original, [(self.product, 1)])
        line = original.lines[0]
        line.invalidate_recordset(['sl_returned_qty']) \
            if hasattr(line, 'invalidate_recordset') else line.invalidate_cache()
        self.assertEqual(line.sl_returned_qty, 1)

    # -- what is refused ---------------------------------------------------

    def test_a_return_cannot_be_returned(self):
        original = self._order([(self.product, 2)], reference='R6')
        refund = self._return(original, [(self.product, 1)])
        with self.assertRaises(ValidationError):
            self._return(refund, [(self.product, 1)])

    def test_an_order_cannot_return_itself(self):
        order = self._order([(self.product, 1)], reference='R7')
        with self.assertRaises(ValidationError):
            order.sl_return_of_order_id = order.id

    def test_a_return_is_not_offered_as_a_returnable_order(self):
        original = self._order([(self.product, 2)], reference='R8')
        refund = self._return(original, [(self.product, 1)])
        with self.assertRaises(UserError):
            self.env['pos.order'].sl_find_returnable(refund.name)

    # -- the setting -------------------------------------------------------

    def test_returns_are_off_until_switched_on(self):
        self.assertFalse(self.env['pos.config'].create(
            {'name': 'Plain Till'}).sl_allow_returns)

    def test_the_setting_reaches_the_config(self):
        settings = self.env['res.config.settings'].create({})
        settings.pos_config_id = self.config
        settings.pos_sl_allow_returns = True
        settings.execute()
        self.assertTrue(self.config.sl_allow_returns)

    # -- helper ------------------------------------------------------------

    def _return(self, original, lines):
        """Record a return the way the screen does: negative quantities."""
        return self._order(
            [(product, -qty) for product, qty in lines],
            reference='%s-RET' % original.pos_reference,
            sl_return_of_order_id=original.id)
