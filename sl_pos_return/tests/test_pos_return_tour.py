# -*- coding: utf-8 -*-
"""The point of sale interface, driven in a real browser.

The other tests in this module exercise the server. This one covers what they
cannot reach: that the Return button is on the product screen, that pressing it
asks for a receipt number, and that the lines come back on the order as a
refund. Odoo tests its own point of sale the same way, with a tour.
"""
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestPosReturnTour(HttpCase):

    # The point of sale lays the product screen out differently on a narrow
    # window: the control buttons move behind a popup. Pin a desktop size so
    # the tour always meets the same screen.
    browser_size = '1920x1080'

    def setUp(self):
        super().setUp()
        self.config = self.env['pos.config'].create({
            'name': 'Return Tour Till', 'sl_allow_returns': True})
        if hasattr(self.env, 'invalidate_all'):
            self.env.invalidate_all()
        else:
            self.env.cache.invalidate()
        self._give_it_a_payment_method(self.config)
        self._give_it_a_sequence(self.config)
        self.product = self.env['product.product'].create({
            'name': 'Returnable Thing', 'available_in_pos': True,
            'list_price': 25.0, 'taxes_id': False})
        self.partner = self.env['res.partner'].create({'name': 'Tour Customer'})
        # The session has to exist or /pos/ui does not render the interface at
        # all. Whether the cashier then sees a login screen or goes straight to
        # the opening dialog depends on the till, so the tour copes with both.
        self.config.open_ui()
        if not self.config.current_session_id and hasattr(
                self.config, 'open_session_cb'):
            self.config.open_session_cb()

    def test_returning_from_the_till(self):
        """A cashier types a receipt number and gets the items back.

        The receipt was rung up on another till, which is the ordinary case: a
        customer comes back later, to whoever is free. It also keeps the order
        out of the session this tour opens, so the screen starts empty.
        """
        self._paid_order('SLRET-0001', self.product, 2)
        self._flush()
        self.start_tour("/pos/ui?config_id=%d" % self.config.id,
                        'sl_pos_return_tour', login='admin')

    # -- fixture -----------------------------------------------------------

    def _paid_order(self, reference, product, qty):
        values = {
            'session_id': self._history_session().id,
            'company_id': self.env.company.id,
            'pricelist_id': self.config.pricelist_id.id
                            or self.env['product.pricelist'].search([], limit=1).id,
            'partner_id': self.partner.id,
            'name': 'POS/%s' % reference,
            'pos_reference': reference,
            'amount_tax': 0.0,
            'amount_total': product.list_price * qty,
            'amount_paid': product.list_price * qty,
            'amount_return': 0.0,
            'lines': [(0, 0, {
                'product_id': product.id, 'qty': qty,
                'price_unit': product.list_price,
                'price_subtotal': product.list_price * qty,
                'price_subtotal_incl': product.list_price * qty,
            })],
        }
        # Created in draft and moved to paid: 16.0 and earlier compute the
        # order name inside create from an empty recordset.
        order = self.env['pos.order'].create(values)
        order.write({'state': 'paid'})
        return order

    def _give_it_a_sequence(self, config):
        sequence = self.env['ir.sequence'].sudo()
        if 'sequence_id' not in config._fields:
            return
        if not config.sequence_id:
            config.sudo().sequence_id = sequence.create({
                'name': 'Tour POS Order', 'padding': 4, 'prefix': 'TOURPOS/',
                'code': 'pos.order', 'implementation': 'standard'}).id
        if 'sequence_line_id' in config._fields and not config.sequence_line_id:
            config.sudo().sequence_line_id = sequence.create({
                'name': 'Tour POS Line', 'padding': 4, 'prefix': 'TOURPOSL/',
                'code': 'pos.order.line', 'implementation': 'standard'}).id

    def _give_it_a_payment_method(self, config):
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
                    'name': 'Tour Cash Journal', 'code': 'TRCSH',
                    'type': 'cash', 'company_id': self.env.company.id})
            if 'profit_account_id' in journal._fields:
                spare = self._spare_account()
                if not journal.profit_account_id:
                    journal.profit_account_id = spare.id
                if not journal.loss_account_id:
                    journal.loss_account_id = spare.id
            method_model = self.env['pos.payment.method']
            values = {'name': 'Tour Cash'}
            if 'receivable_account_id' in method_model._fields:
                values['receivable_account_id'] = self._spare_account().id
            if 'journal_id' in method_model._fields:
                values['journal_id'] = journal.id
            elif 'cash_journal_id' in method_model._fields:
                values['is_cash_count'] = True
                values['cash_journal_id'] = journal.id
            method = method_model.create(values)
        config.payment_method_ids = [(6, 0, method.ids)]

    def _spare_account(self):
        accounts = self.env['account.account']
        found = accounts.search([], limit=1)
        if found:
            return found
        values = {'name': 'Tour Sundry', 'code': 'TSUN02', 'reconcile': True}
        if 'account_type' in accounts._fields:
            values['account_type'] = 'asset_receivable'
        else:
            values['user_type_id'] = self.env.ref(
                'account.data_account_type_receivable').id
        return accounts.create(values)

    def _flush(self):
        if hasattr(self.env, 'flush_all'):
            self.env.flush_all()
        elif hasattr(self.env.cr, 'flush'):
            self.env.cr.flush()
        else:
            self.env['base'].flush()

    def _history_session(self):
        """A session on another till, holding what was sold earlier.

        The point of sale loads the current session's orders into the browser
        at start up. An order built by a test is not complete enough for that
        - it has no price detail for the client to recompute - so it lives on
        a till the tour does not open.
        """
        if getattr(self, '_history', None):
            return self._history
        config = self.env['pos.config'].create({'name': 'History Till'})
        if hasattr(self.env, 'invalidate_all'):
            self.env.invalidate_all()
        else:
            self.env.cache.invalidate()
        self._give_it_a_payment_method(config)
        self._give_it_a_sequence(config)
        config.open_ui()
        if not config.current_session_id and hasattr(config, 'open_session_cb'):
            config.open_session_cb()
        self._history = config.current_session_id
        return self._history
