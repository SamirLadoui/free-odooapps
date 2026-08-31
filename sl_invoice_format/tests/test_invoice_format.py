# -*- coding: utf-8 -*-
import inspect

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestInvoiceFormat(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': 'Format Customer'})
        books = cls._ensure_accounting()
        cls.product = cls.env['product.product'].create({
            'name': 'Formatted Product', 'default_code': 'FMT-1',
            'list_price': 50.0, 'type': 'service',
            'property_account_income_id': books['income'].id})
        cls.partner.write({
            'property_account_receivable_id': books['receivable'].id,
            'property_account_payable_id': books['payable'].id,
        })
        journal = cls.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', cls.company.id)], limit=1)
        if not journal:
            # A bare database has no chart of accounts and so no sale journal.
            journal = cls.env['account.journal'].create({
                'name': 'Invoice Format Sales', 'code': 'IFSAL',
                'type': 'sale', 'company_id': cls.company.id})
        cls.invoice = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': cls.partner.id,
            'journal_id': journal.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': cls.product.id,
                'quantity': 3.0,
                'price_unit': 50.0,
                'name': 'Formatted line',
            })],
        })

    def _render(self):
        report = self.env.ref('account.account_invoices')
        if 'report_ref' in inspect.signature(report._render_qweb_html).parameters:
            content, _t = report._render_qweb_html(report.report_name, self.invoice.ids)
        else:
            content, _t = report._render_qweb_html(self.invoice.ids)
        return content.decode()

    # -- defaults ----------------------------------------------------------

    def test_defaults_show_the_usual_columns(self):
        self.assertTrue(self.company.invoice_show_quantity)
        self.assertTrue(self.company.invoice_show_price_unit)
        self.assertTrue(self.company.invoice_show_taxes)

    def test_default_render_has_quantity_and_price(self):
        html = self._render()
        self.assertIn('Quantity', html)
        self.assertIn('Unit Price', html)

    # -- hiding columns ----------------------------------------------------

    def test_hiding_quantity_removes_the_column(self):
        self.company.invoice_show_quantity = False
        html = self._render()
        self.assertNotIn('>Quantity<', html)
        self.assertIn('Unit Price', html, "the price column should still be there")

    def test_hiding_price_removes_the_column(self):
        self.company.invoice_show_price_unit = False
        html = self._render()
        self.assertNotIn('>Unit Price<', html)

    def test_cannot_hide_both_quantity_and_price(self):
        """A line with neither leaves the customer nothing to check."""
        self.company.invoice_show_quantity = False
        with self.assertRaises(ValidationError):
            self.company.invoice_show_price_unit = False

    # -- relabelling -------------------------------------------------------

    def test_custom_headings_are_used(self):
        self.company.write({
            'invoice_label_description': 'Item',
            'invoice_label_quantity': 'Qty',
            'invoice_label_price_unit': 'Rate',
        })
        html = self._render()
        self.assertIn('Item', html)
        self.assertIn('Qty', html)
        self.assertIn('Rate', html)

    def test_empty_heading_falls_back_to_the_default(self):
        self.company.invoice_label_quantity = False
        self.assertEqual(self.company._invoice_label('quantity'), 'Quantity')

    def test_label_helper_returns_the_override(self):
        self.company.invoice_label_subtotal = 'Line Total'
        self.assertEqual(self.company._invoice_label('subtotal'), 'Line Total')

    def test_unknown_label_key_is_harmless(self):
        self.assertEqual(self.company._invoice_label('nonexistent'), '')

    # -- footer ------------------------------------------------------------

    def test_footer_note_is_printed(self):
        self.company.invoice_footer_note = 'Payment within 30 days.'
        self.assertIn('Payment within 30 days.', self._render())

    def test_no_footer_note_prints_nothing_extra(self):
        self.company.invoice_footer_note = False
        self.assertNotIn('sl_invoice_footer_note', self._render())

    # -- the report still renders -----------------------------------------

    def test_report_renders_with_every_option_off(self):
        self.company.write({
            'invoice_show_quantity': True,
            'invoice_show_price_unit': True,
            'invoice_show_taxes': False,
            'invoice_show_product_image': False,
        })
        html = self._render()
        self.assertIn('Formatted line', html)

    def test_product_image_option_renders(self):
        self.company.invoice_show_product_image = True
        html = self._render()
        self.assertIn('Formatted line', html, "the invoice must still render")

    @classmethod
    def _ensure_accounting(cls):
        """A bare database has no chart of accounts, so an invoice line has no
        income account and the customer no receivable to balance against."""
        accounts = cls.env['account.account']
        modern = 'account_type' in accounts._fields
        legacy = {
            'income': 'account.data_account_type_revenue',
            'asset_receivable': 'account.data_account_type_receivable',
            'liability_payable': 'account.data_account_type_payable',
        }

        def account_of(kind, name, code):
            if modern:
                found = accounts.search([('account_type', '=', kind)], limit=1)
            else:
                found = accounts.search(
                    [('user_type_id', '=', cls.env.ref(legacy[kind]).id)],
                    limit=1)
            if found:
                return found
            values = {'name': name, 'code': code}
            if modern:
                values['account_type'] = kind
            else:
                values['user_type_id'] = cls.env.ref(legacy[kind]).id
            if kind != 'income':
                values['reconcile'] = True
            return accounts.create(values)

        return {
            'income': account_of('income', 'Format Income', 'FMTI01'),
            'receivable': account_of('asset_receivable', 'Format Receivable', 'FMTR01'),
            'payable': account_of('liability_payable', 'Format Payable', 'FMTP01'),
        }
