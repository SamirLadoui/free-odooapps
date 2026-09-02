# -*- coding: utf-8 -*-
"""The numbers a customer would count, and the ones on the paper."""
from odoo import release
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestLineNumbers(AccountTestInvoicingCommon):

    def setUp(self):
        # 14.0 has no class-level env: setUpClass cannot build fixtures.
        super().setUp()
        self.product = self.env['product.product'].create({'name': 'Widget'})
        self.other = self.env['product.product'].create({'name': 'Gadget'})
        self.third = self.env['product.product'].create({'name': 'Gizmo'})

    def _invoice(self, lines):
        return self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_line_ids': lines,
        })

    def _line(self, product=None, **values):
        return (0, 0, dict({
            'product_id': (product or self.product).id,
            'quantity': 1.0,
            'price_unit': 10.0,
        }, **values))

    def _heading(self, kind, name):
        return (0, 0, {'display_type': kind, 'name': name})

    # -- the numbers -------------------------------------------------------

    def test_lines_are_numbered_from_one(self):
        invoice = self._invoice([self._line(self.product),
                                 self._line(self.other),
                                 self._line(self.third)])
        self.assertEqual(invoice.invoice_line_ids.mapped('sl_line_number'),
                         [1, 2, 3])

    def test_a_single_line_is_line_one(self):
        invoice = self._invoice([self._line()])
        self.assertEqual(invoice.invoice_line_ids.sl_line_number, 1)

    def test_headings_are_not_numbered(self):
        """A section counted as a line makes every number after it wrong."""
        invoice = self._invoice([
            self._heading('line_section', 'Hardware'),
            self._line(self.product),
            self._heading('line_note', 'Delivered separately'),
            self._line(self.other),
        ])
        numbered = invoice.invoice_line_ids.filtered(
            lambda line: line.display_type not in ('line_section', 'line_note'))
        self.assertEqual(numbered.mapped('sl_line_number'), [1, 2])
        headings = invoice.line_ids.filtered(
            lambda line: line.display_type in ('line_section', 'line_note'))
        self.assertEqual(set(headings.mapped('sl_line_number')), {0})

    def test_reordering_renumbers(self):
        """Nothing is stored, so moving a line up is enough."""
        invoice = self._invoice([self._line(self.product),
                                 self._line(self.other)])
        first, second = invoice.invoice_line_ids
        first.sequence, second.sequence = 20, 10
        invoice.invalidate_cache(['invoice_line_ids'])
        self.assertEqual(second.sl_line_number, 1)
        self.assertEqual(first.sl_line_number, 2)

    def test_one_invoice_does_not_number_another(self):
        first = self._invoice([self._line(), self._line(self.other)])
        second = self._invoice([self._line(self.third)])
        self.assertEqual(second.invoice_line_ids.sl_line_number, 1)
        self.assertEqual(first.invoice_line_ids.mapped('sl_line_number'),
                         [1, 2])

    def test_a_bill_is_numbered_too(self):
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2024-01-01',
            'invoice_line_ids': [self._line(self.product),
                                 self._line(self.other)],
        })
        self.assertEqual(bill.invoice_line_ids.mapped('sl_line_number'),
                         [1, 2])

    def test_the_tax_and_total_lines_are_not_numbered(self):
        """Only what appears in the lines tab is counted."""
        invoice = self._invoice([self._line()])
        invoice.action_post()
        other_lines = invoice.line_ids - invoice.invoice_line_ids
        self.assertTrue(other_lines)
        self.assertEqual(set(other_lines.mapped('sl_line_number')), {0})

    # -- what gets printed -------------------------------------------------

    def _render(self, invoice):
        report = self.env['ir.actions.report']
        name = 'account.report_invoice'
        if release.version_info[0] >= 16:
            html, _kind = report._render_qweb_html(name, invoice.ids)
        else:
            html, _kind = report._get_report_from_name(name) \
                ._render_qweb_html(invoice.ids)
        return html.decode() if isinstance(html, bytes) else html

    def test_the_numbers_reach_the_printed_invoice(self):
        invoice = self._invoice([self._line(self.product),
                                 self._line(self.other)])
        invoice.action_post()
        html = self._render(invoice)
        self.assertIn('sl_line_number', html)
        marked = html.count('sl_line_number')
        self.assertGreaterEqual(marked, 2)

    def test_the_printed_invoice_still_has_its_lines(self):
        """A bad xpath would render a document with the table gone."""
        invoice = self._invoice([self._line(self.product)])
        invoice.action_post()
        html = self._render(invoice)
        self.assertIn('Widget', html)
