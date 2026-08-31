# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPosReturn(TransactionCase):

    def setUp(self):
        # Instance level throughout: 14.0 builds no environment until setUp.
        super().setUp()
        self.config = self.env['pos.config'].create({'name': 'Return Till'})
        self.product = self.env['product.product'].create({
            'name': 'Returnable Thing', 'available_in_pos': True,
            'list_price': 25.0, 'taxes_id': False})
        self.other = self.env['product.product'].create({
            'name': 'Other Thing', 'available_in_pos': True,
            'list_price': 10.0, 'taxes_id': False})
        self.partner = self.env['res.partner'].create({'name': 'Return Customer'})
        # pos.config.create installs modules and warns that the environment
        # is no longer valid afterwards, so 16.0 reads sequence_id as False
        # unless the cache is dropped first.
        if hasattr(self.env, 'invalidate_all'):
            self.env.cache.invalidate()
        else:
            self.env.cache.invalidate()
        self._give_it_a_payment_method(self.config)
        self._give_it_a_sequence(self.config)
        self.config.open_ui()
        if not self.config.current_session_id and hasattr(
                self.config, 'open_session_cb'):
            # Before 16.0 open_ui only returns the url action; the session is
            # opened by open_session_cb.
            self.config.open_session_cb()
        self.session = self.config.current_session_id

    def _give_it_a_sequence(self, config):
        """pos.order takes its name from the config sequence, and a config
        built in a test does not always end up with one."""
        sequence = self.env['ir.sequence'].sudo()
        if 'sequence_id' not in config._fields:
            return  # 19.0 dropped it; the order name comes from elsewhere
        if not config.sequence_id:
            config.sudo().sequence_id = sequence.create({
                'name': 'Test POS Order', 'padding': 4, 'prefix': 'TSTPOS/',
                'code': 'pos.order', 'implementation': 'standard'}).id
        if 'sequence_line_id' in config._fields and not config.sequence_line_id:
            config.sudo().sequence_line_id = sequence.create({
                'name': 'Test POS Line', 'padding': 4, 'prefix': 'TSTPOSL/',
                'code': 'pos.order.line', 'implementation': 'standard'}).id

    def _give_it_a_payment_method(self, config):
        """A session refuses to open without one, and a config created in a
        test does not inherit the demo methods on every version."""
        if config.payment_method_ids:
            return
        method = self.env['pos.payment.method'].search(
            [('company_id', '=', self.env.company.id)], limit=1)
        if not method:
            journal = self.env['account.journal'].search(
                [('type', 'in', ('cash', 'bank')),
                 ('company_id', '=', self.env.company.id)], limit=1)
            if not journal:
                journal = self.env['account.journal'].create({
                    'name': 'Test Cash Journal', 'code': 'TCSH',
                    'type': 'cash', 'company_id': self.env.company.id})
            # A session refuses to open on a cash journal with no profit and
            # loss accounts to book a difference to.
            if 'profit_account_id' in journal._fields:
                spare = self._spare_account()
                if not journal.profit_account_id:
                    journal.profit_account_id = spare.id
                if not journal.loss_account_id:
                    journal.loss_account_id = spare.id
            # 14.0 has no journal_id on a payment method: a cash method is
            # flagged with is_cash_count and points at cash_journal_id.
            method_model = self.env['pos.payment.method']
            values = {'name': 'Test Cash'}
            if 'receivable_account_id' in method_model._fields:
                # Required on 14.0, and a bare database has no chart of
                # accounts to default it from.
                values['receivable_account_id'] = \
                    self._receivable_account().id
            if 'journal_id' in method_model._fields:
                values['journal_id'] = journal.id
            elif 'cash_journal_id' in method_model._fields:
                values['is_cash_count'] = True
                values['cash_journal_id'] = journal.id
            method = method_model.create(values)
        config.payment_method_ids = [(6, 0, method.ids)]

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
        values = dict({
            'session_id': self.session.id,
            # Not defaulted from the session before 16.0, and neither column
            # is nullable.
            'company_id': self.env.company.id,
            'pricelist_id': self.config.pricelist_id.id
                            or self.env['product.pricelist'].search([], limit=1).id,
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
        }, **values)
        # Create in draft and move to paid afterwards, the way the till does.
        # 16.0 computes the order name inside create from an empty recordset,
        # so a state of 'paid' in the create values dereferences a sequence
        # that is not there.
        state = values.pop('state')
        order = self.env['pos.order'].create(values)
        order.write({'state': state})
        return order

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
        line.invalidate_cache(['sl_returned_qty']) \
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
        settings_model = self.env['res.config.settings']
        if 'pos_config_id' not in settings_model._fields:
            # Before 16.0 there is no per-config section in Settings, so the
            # switch is set on the point of sale's own form instead.
            self.assertIn('sl_allow_returns', self.config._fields)
            return
        settings = settings_model.create({})
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

    def _receivable_account(self):
        """A receivable account, made if the database has none."""
        accounts = self.env['account.account']
        modern = 'account_type' in accounts._fields
        if modern:
            found = accounts.search(
                [('account_type', '=', 'asset_receivable')], limit=1)
        else:
            found = accounts.search(
                [('user_type_id', '=',
                  self.env.ref('account.data_account_type_receivable').id)],
                limit=1)
        if found:
            return found
        values = {'name': 'Test Receivable', 'code': 'TREC01', 'reconcile': True}
        if modern:
            values['account_type'] = 'asset_receivable'
        else:
            values['user_type_id'] = self.env.ref(
                'account.data_account_type_receivable').id
        return accounts.create(values)

    def _spare_account(self):
        """Any account a cash difference can be booked to."""
        accounts = self.env['account.account']
        found = accounts.search([], limit=1)
        if found:
            return found
        values = {'name': 'Test Sundry', 'code': 'TSUN01'}
        if 'account_type' in accounts._fields:
            values['account_type'] = 'income_other'
        else:
            values['user_type_id'] = self.env.ref(
                'account.data_account_type_other_income').id
        return accounts.create(values)
