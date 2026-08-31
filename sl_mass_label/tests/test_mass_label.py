# -*- coding: utf-8 -*-
import inspect

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMassLabel(TransactionCase):

    def setUp(self):
        # 14.0 has no class-level env: setUpClass cannot build fixtures.
        super().setUp()
        self.products = self.env['product.product'].create([
            {'name': 'Label Product %s' % i,
             'default_code': 'LP%s' % i,
             'barcode': '900000000%s' % i,
             'list_price': 10.0 + i}
            for i in range(5)
        ])
        self.partner = self.env['res.partner'].create({'name': 'Label Partner'})
        # Without a document layout, report_action returns the "configure your
        # layout" wizard instead of the report - core behaviour on a bare db.
        self.env.company.external_report_layout_id = self.env.ref(
            'web.external_layout_standard')

    def _wizard(self, records=None, **values):
        records = self.products if records is None else records
        return self.env['sl.label.wizard'].create(dict({
            'res_model': records._name,
            'res_ids': ','.join(str(r.id) for r in records),
        }, **values))

    # -- the grid ----------------------------------------------------------

    def test_labels_are_laid_out_across_then_down(self):
        pages = self._wizard(columns=2, rows=2)._label_pages()
        self.assertEqual(len(pages), 2, '5 labels at 4 per page is 2 pages')
        self.assertEqual(len(pages[0]), 2)
        self.assertEqual(len(pages[0][0]), 2)

    def test_the_last_row_is_padded(self):
        """An unpadded final row stretches its cells and every label on it
        lands in the wrong place on the sheet."""
        pages = self._wizard(columns=3, rows=5)._label_pages()
        last_row = pages[-1][-1]
        self.assertEqual(len(last_row), 3)
        self.assertIsNone(last_row[-1])

    def test_a_full_last_row_is_not_padded(self):
        pages = self._wizard(records=self.products[:4], columns=2, rows=5)._label_pages()
        self.assertTrue(all(cell is not None for cell in pages[-1][-1]))

    def test_copies_multiply_the_labels(self):
        pages = self._wizard(records=self.products[:1], copies=7,
                             columns=1, rows=10)._label_pages()
        printed = [c for page in pages for row in page for c in row if c]
        self.assertEqual(len(printed), 7)

    def test_every_record_is_printed(self):
        pages = self._wizard(columns=4, rows=4)._label_pages()
        printed = [c for page in pages for row in page for c in row if c]
        self.assertEqual(len(printed), 5)

    # -- what lands on a label --------------------------------------------

    def test_a_label_carries_what_was_asked_for(self):
        wizard = self._wizard(show_price=True)
        values = wizard._label_values(self.products[0])
        self.assertEqual(values['code'], 'LP0')
        self.assertEqual(values['barcode'], '9000000000')
        self.assertIn('10.0', values['price'])

    def test_switches_leave_fields_off_the_label(self):
        wizard = self._wizard(show_code=False, show_barcode=False, show_price=False)
        values = wizard._label_values(self.products[0])
        self.assertFalse(values['code'])
        self.assertFalse(values['barcode'])
        self.assertFalse(values['price'])
        self.assertTrue(values['name'])

    def test_a_model_without_those_fields_still_prints(self):
        """The same wizard has to work on a contact, which has no default_code
        and no list_price."""
        wizard = self._wizard(records=self.partner, show_price=True)
        values = wizard._label_values(self.partner)
        self.assertEqual(values['name'], 'Label Partner')
        self.assertEqual(values['code'], '')
        self.assertEqual(values['price'], '')

    # -- bounds and bad input ---------------------------------------------

    def test_the_grid_is_bounded(self):
        for bad in ({'columns': 0}, {'columns': 11}, {'rows': 0}, {'rows': 31}):
            with self.assertRaises(ValidationError, msg='accepted %s' % bad):
                self._wizard(**bad)

    def test_copies_are_bounded(self):
        for bad in (0, -1, 101):
            with self.assertRaises(ValidationError, msg='accepted %s copies' % bad):
                self._wizard(copies=bad)

    def test_an_unknown_model_is_refused(self):
        wizard = self._wizard()
        wizard.res_model = 'no.such.model'
        with self.assertRaises(UserError):
            wizard._label_pages()

    def test_printing_nothing_is_refused(self):
        wizard = self._wizard()
        wizard.res_ids = '999999999'
        with self.assertRaises(UserError):
            wizard._label_pages()

    def test_deleted_records_are_dropped_not_fatal(self):
        """A record can be deleted between opening the wizard and printing."""
        wizard = self._wizard()
        self.products[0].unlink()
        printed = [c for page in wizard._label_pages() for row in page
                   for c in row if c]
        self.assertEqual(len(printed), 4)

    def test_the_record_count_is_shown(self):
        self.assertEqual(self._wizard().record_count, 5)

    # -- the action and the pdf -------------------------------------------

    def test_the_wizard_picks_up_the_selection(self):
        wizard = self.env['sl.label.wizard'].with_context(
            active_model='product.product',
            active_ids=self.products.ids,
        ).create({})
        self.assertEqual(wizard.res_model, 'product.product')
        self.assertEqual(wizard.record_count, 5)

    def test_print_returns_a_report_action(self):
        action = self._wizard().action_print()
        self.assertEqual(action['type'], 'ir.actions.report')

    def test_the_sheet_renders(self):
        wizard = self._wizard(columns=2, rows=2, show_price=True)
        report = self.env.ref('sl_mass_label.action_report_label_sheet')
        # 16.0 added report_ref as the first argument.
        if 'report_ref' in inspect.signature(
                report._render_qweb_html).parameters:
            html, _t = report._render_qweb_html(report.report_name, wizard.ids)
        else:
            html, _t = report._render_qweb_html(wizard.ids)
        html = html.decode()
        self.assertIn('Label Product 0', html)
        self.assertIn('LP0', html)
        self.assertIn('sl_label_sheet', html)
