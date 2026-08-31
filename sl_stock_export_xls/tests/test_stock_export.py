# -*- coding: utf-8 -*-
import base64
import io
import zipfile

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestStockExport(TransactionCase):

    def setUp(self):
        # 14.0 has no class-level env: setUpClass cannot build fixtures.
        super().setUp()
        self.category = self.env['product.category'].create({'name': 'Export Test'})
        self.other_category = self.env['product.category'].create({'name': 'Not Exported'})
        self.warehouse = self.env['stock.warehouse'].search([], limit=1)
        self.stock_location = self.warehouse.lot_stock_id

        storable = ({'is_storable': True, 'type': 'consu'}
                    if 'is_storable' in self.env['product.product']._fields
                    else {'type': 'product'})
        self.widget = self.env['product.product'].create(dict(
            storable, name='Widget', default_code='W-1',
            categ_id=self.category.id, standard_price=10.0))
        self.gadget = self.env['product.product'].create(dict(
            storable, name='Gadget', default_code='G-1',
            categ_id=self.category.id, standard_price=4.0))
        self.outsider = self.env['product.product'].create(dict(
            storable, name='Outsider', default_code='O-1',
            categ_id=self.other_category.id, standard_price=1.0))

        self.env['stock.quant']._update_available_quantity(
            self.widget, self.stock_location, 7)
        self.env['stock.quant']._update_available_quantity(
            self.outsider, self.stock_location, 3)
        # gadget deliberately left with no stock

    def _wizard(self, **values):
        return self.env['sl.stock.export.wizard'].create(
            dict({'category_ids': [(6, 0, self.category.ids)]}, **values))

    def _by_code(self, rows):
        return {row['default_code']: row for row in rows}

    def test_rows_respect_category_filter(self):
        rows = self._by_code(self._wizard()._collect_rows())
        self.assertIn('W-1', rows)
        self.assertNotIn('O-1', rows, "another category must not leak into the export")

    def test_zero_stock_excluded_by_default(self):
        rows = self._by_code(self._wizard()._collect_rows())
        self.assertNotIn('G-1', rows, "a product with no stock should be skipped")

    def test_zero_stock_included_on_request(self):
        rows = self._by_code(self._wizard(include_zero=True)._collect_rows())
        self.assertIn('G-1', rows)
        self.assertEqual(rows['G-1']['quantity'], 0)

    def test_quantities_and_valuation(self):
        row = self._by_code(self._wizard()._collect_rows())['W-1']
        self.assertEqual(row['quantity'], 7)
        self.assertEqual(row['cost'], 10.0)
        self.assertEqual(row['value'], 70.0, "value is quantity times unit cost")
        self.assertEqual(row['name'], self.widget.display_name)
        self.assertEqual(row['uom'], self.widget.uom_id.name)

    def test_naming_a_product_narrows_rather_than_widens(self):
        """Filters combine; naming a product outside the chosen category
        must not pull it back into the export."""
        wizard = self._wizard(product_ids=[(6, 0, self.outsider.ids)])
        self.assertEqual(wizard._collect_rows(), [])

    def test_location_mode_reports_each_location(self):
        rows = self._wizard(mode='location')._collect_rows()
        widget_rows = [r for r in rows if r['default_code'] == 'W-1']
        self.assertTrue(widget_rows)
        self.assertEqual(sum(r['quantity'] for r in widget_rows), 7)
        self.assertTrue(all(r['location'] for r in widget_rows),
                        "every location row must name its location")

    def test_columns_follow_the_options(self):
        self.assertNotIn('location', self._wizard()._active_columns())
        self.assertIn('location', self._wizard(mode='location')._active_columns())
        self.assertNotIn('lot', self._wizard(mode='location')._active_columns())
        self.assertIn('lot', self._wizard(mode='location', include_lots=True)._active_columns())
        no_value = self._wizard(include_valuation=False)._active_columns()
        self.assertNotIn('cost', no_value)
        self.assertNotIn('value', no_value)

    def test_export_produces_a_real_xlsx(self):
        wizard = self._wizard()
        wizard.action_export()
        self.assertTrue(wizard.file_data)
        self.assertTrue(wizard.file_name.endswith('.xlsx'))
        content = base64.b64decode(wizard.file_data)
        with zipfile.ZipFile(io.BytesIO(content)) as book:
            names = book.namelist()
        self.assertIn('xl/workbook.xml', names, "should be a valid xlsx package")

    def test_empty_export_explains_itself(self):
        wizard = self._wizard(category_ids=[(6, 0, self.other_category.ids)],
                              product_ids=[(6, 0, self.gadget.ids)])
        with self.assertRaises(UserError):
            wizard.action_export()
