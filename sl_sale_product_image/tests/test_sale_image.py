# -*- coding: utf-8 -*-
import base64
import inspect

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

PIXEL = base64.b64encode(base64.b64decode(
    b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='))


@tagged('post_install', '-at_install')
class TestSaleProductImage(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': 'Image Customer'})
        cls.product = cls.env['product.product'].create({
            'name': 'Pictured Product', 'type': 'consu',
            'list_price': 20.0, 'image_1920': PIXEL})
        cls.plain = cls.env['product.product'].create({
            'name': 'No Picture', 'type': 'consu', 'list_price': 5.0})
        cls.order = cls.env['sale.order'].create({
            'partner_id': cls.partner.id,
            'order_line': [
                (0, 0, {'product_id': cls.product.id, 'product_uom_qty': 1}),
                (0, 0, {'product_id': cls.plain.id, 'product_uom_qty': 1}),
            ],
        })

    def _render(self):
        report = self.env.ref('sale.action_report_saleorder')
        if 'report_ref' in inspect.signature(report._render_qweb_html).parameters:
            content, _t = report._render_qweb_html(report.report_name, self.order.ids)
        else:
            content, _t = report._render_qweb_html(self.order.ids)
        return content.decode()

    # -- the setting -------------------------------------------------------

    def test_off_by_default(self):
        """Turning it on is a choice; existing quotations should not change."""
        self.assertFalse(self.company.sale_report_show_image)

    def test_size_is_bounded(self):
        for bad in (1, 5, 500, -10):
            with self.assertRaises(ValidationError, msg='accepted size %s' % bad):
                self.company.sale_report_image_size = bad

    def test_a_sensible_size_is_accepted(self):
        self.company.sale_report_image_size = 64
        self.assertEqual(self.company._sale_report_image_size(), 64)

    def test_an_unset_size_falls_back(self):
        self.company.sale_report_image_size = 0
        self.assertEqual(self.company._sale_report_image_size(), 48)

    # -- the report --------------------------------------------------------

    # The report layout always embeds the company logo as a base64 png, so
    # these count the class on our own img rather than base64 data.
    def test_no_images_when_the_setting_is_off(self):
        self.company.sale_report_show_image = False
        html = self._render()
        self.assertIn('Pictured Product', html)
        self.assertNotIn('o_sl_product_image', html)

    def test_images_appear_when_the_setting_is_on(self):
        self.company.sale_report_show_image = True
        html = self._render()
        self.assertIn('o_sl_product_image', html)

    def test_a_product_without_an_image_is_skipped(self):
        """One image, not two: the plain product must not get an empty box."""
        self.company.sale_report_show_image = True
        self.assertEqual(self._render().count('o_sl_product_image'), 1)

    def test_the_configured_size_reaches_the_report(self):
        self.company.write({'sale_report_show_image': True,
                            'sale_report_image_size': 72})
        self.assertIn('max-height: 72px', self._render())

    def test_the_report_still_renders_normally(self):
        self.company.sale_report_show_image = True
        html = self._render()
        self.assertIn('Pictured Product', html)
        self.assertIn('No Picture', html)
