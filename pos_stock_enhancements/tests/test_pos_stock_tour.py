# -*- coding: utf-8 -*-
"""The stock check at the till, driven in a real browser.

The other tests in this module prove the server answers the right stock
figures. This one covers what they cannot: that a product with none left is
actually refused at the screen, with a reason, and nothing lands on the order.
"""
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestPosStockTour(HttpCase):

    # The product screen lays out differently on a narrow window, so pin a
    # size and always meet the same screen.
    browser_size = '1920x1080'

    def setUp(self):
        super().setUp()
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        self.shelf = warehouse.lot_stock_id

        storable = ({'is_storable': True, 'type': 'consu'}
                    if 'is_storable' in self.env['product.product']._fields
                    else {'type': 'product'})
        # Nothing is ever put in stock for this one, which is the point.
        self.sold_out = self.env['product.product'].create(
            dict(storable, name='Sold Out Thing', available_in_pos=True,
                 list_price=10.0, taxes_id=False))

        self.config = self.env['pos.config'].create({
            'name': 'Stock Tour Till',
            'enforce_pos_stock_check': True,
            'available_stock_location_ids': [(6, 0, self.shelf.ids)],
        })
        if hasattr(self.env, 'invalidate_all'):
            self.env.invalidate_all()
        else:
            self.env.cache.invalidate()
        self._give_it_a_payment_method(self.config)
        self._give_it_a_sequence(self.config)
        self.config.open_ui()
        if not self.config.current_session_id and hasattr(
                self.config, 'open_session_cb'):
            self.config.open_session_cb()

    def test_a_product_with_no_stock_is_refused_at_the_till(self):
        self._flush()
        self.start_tour("/pos/ui?config_id=%d" % self.config.id,
                        'sl_pos_stock_tour', login='admin')

    # -- fixture -----------------------------------------------------------

    def _give_it_a_sequence(self, config):
        sequence = self.env['ir.sequence'].sudo()
        if 'sequence_id' not in config._fields:
            return
        if not config.sequence_id:
            config.sudo().sequence_id = sequence.create({
                'name': 'Stock Tour Order', 'padding': 4, 'prefix': 'STKPOS/',
                'code': 'pos.order', 'implementation': 'standard'}).id
        if 'sequence_line_id' in config._fields and not config.sequence_line_id:
            config.sudo().sequence_line_id = sequence.create({
                'name': 'Stock Tour Line', 'padding': 4, 'prefix': 'STKPOSL/',
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
                    'name': 'Stock Tour Cash', 'code': 'STKCS',
                    'type': 'cash', 'company_id': self.env.company.id})
            if 'profit_account_id' in journal._fields:
                spare = self._spare_account()
                if not journal.profit_account_id:
                    journal.profit_account_id = spare.id
                if not journal.loss_account_id:
                    journal.loss_account_id = spare.id
            method_model = self.env['pos.payment.method']
            values = {'name': 'Stock Tour Cash'}
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
        values = {'name': 'Stock Tour Sundry', 'code': 'STSUN1',
                  'reconcile': True}
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
