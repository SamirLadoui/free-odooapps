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
        cls.product = cls.env['product.product'].create({
            'name': 'Formatted Product', 'default_code': 'FMT-1',
            'list_price': 50.0, 'type': 'service'})
        journal = cls.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', cls.company.id)], limit=1)
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
