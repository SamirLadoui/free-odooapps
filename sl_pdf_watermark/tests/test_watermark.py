# -*- coding: utf-8 -*-
"""What reaches the printed page, and what deliberately does not.

The report is built here rather than borrowed from accounting: the module
hooks the layout every document passes through, and a test that needed
invoices would be testing accounting as much as this.
"""
import base64
import re

from odoo import release
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

ARCH = """<t t-name="sl_pdf_watermark.test_report">
    <t t-call="web.html_container">
        <t t-foreach="docs" t-as="o">
            <t t-call="web.external_layout">
                <div class="page"><span t-esc="o.name"/></div>
            </t>
        </t>
    </t>
</t>"""


@tagged('post_install', '-at_install')
class TestWatermark(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Printed Ltd'})
        self.other = self.env['res.partner'].create({'name': 'Unmarked Ltd'})
        self.model = self.env['ir.model']._get('res.partner')
        self.env['ir.ui.view'].create({
            'name': 'sl watermark test report',
            'type': 'qweb',
            'key': 'sl_pdf_watermark.test_report',
            'arch': ARCH,
        })
        self.report = self.env['ir.actions.report'].create({
            'name': 'Watermark Test',
            'model': 'res.partner',
            'report_type': 'qweb-html',
            'report_name': 'sl_pdf_watermark.test_report',
        })

    def _rule(self, **values):
        return self.env['sl.watermark.rule'].create(dict({
            'name': 'Test watermark',
            'model_id': self.model.id,
            'text': 'DRAFT',
        }, **values))

    def _render(self, record):
        if release.version_info[0] >= 16:
            html, _kind = self.env['ir.actions.report']._render_qweb_html(
                self.report.report_name, record.ids)
        else:
            html, _kind = self.report._render_qweb_html(record.ids)
        return html.decode() if isinstance(html, bytes) else html

    def _watermark_svg(self, html):
        """The watermark image, decoded.

        Matched on the whole data URI including its media type: a report also
        carries the company logo as base64, and a looser pattern finds that
        PNG first and decodes it as text.
        """
        found = re.search(r'data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)', html)
        return base64.b64decode(found.group(1)).decode() if found else None

    def _watermark_text(self, html):
        """The words actually drawn on the page, read back out of the SVG."""
        svg = self._watermark_svg(html)
        if svg is None:
            return None
        drawn = re.search(r'>([^<]*)</text>', svg)
        return drawn.group(1) if drawn else ''

    # -- what gets printed -------------------------------------------------

    def test_a_rule_puts_its_word_on_the_page(self):
        self._rule(text='DRAFT')
        self.assertEqual(self._watermark_text(self._render(self.partner)),
                         'DRAFT')

    def test_without_a_rule_nothing_is_added(self):
        """A document with no watermark carries no trace of the module.

        Checked against this module's own marks rather than against
        "background-image": 15.0's standard layout writes that property
        itself, empty, whether anything is behind the page or not.
        """
        html = self._render(self.partner)
        self.assertIsNone(self._watermark_text(html))
        self.assertNotIn('data:image/svg+xml', html)
        self.assertNotIn('background-repeat: repeat', html)

    def test_the_document_still_prints(self):
        """A bad hook would render a page with the content gone."""
        self._rule()
        self.assertIn('Printed Ltd', self._render(self.partner))

    def test_the_word_is_whatever_the_rule_says(self):
        self._rule(text='COPY ONLY')
        self.assertEqual(self._watermark_text(self._render(self.partner)),
                         'COPY ONLY')

    def test_the_look_comes_from_the_rule(self):
        self._rule(color='#00aa00', opacity=0.5, angle=45, font_size=90)
        svg = self._watermark_svg(self._render(self.partner))
        self.assertIn('#00aa00', svg)
        self.assertIn('0.5', svg)
        self.assertIn('rotate(45', svg)
        self.assertIn('font-size="90"', svg)

    def test_it_is_tiled_behind_the_page(self):
        self._rule()
        html = self._render(self.partner)
        self.assertIn('background-repeat: repeat', html)

    # -- which documents it applies to -------------------------------------

    def test_a_domain_narrows_it_to_some_documents(self):
        self._rule(domain="[('name', '=', 'Printed Ltd')]")
        self.assertEqual(self._watermark_text(self._render(self.partner)),
                         'DRAFT')
        self.assertIsNone(self._watermark_text(self._render(self.other)))

    def test_a_rule_for_another_model_does_not_apply(self):
        self._rule(model_id=self.env['ir.model']._get('res.country').id)
        self.assertIsNone(self._watermark_text(self._render(self.partner)))

    def test_the_first_rule_that_fits_wins(self):
        """Two rules about one document is a question the order answers."""
        self._rule(name='Broad', text='SECOND', sequence=20)
        self._rule(name='Narrow', text='FIRST', sequence=1)
        self.assertEqual(self._watermark_text(self._render(self.partner)),
                         'FIRST')

    def test_an_archived_rule_is_not_used(self):
        rule = self._rule()
        rule.active = False
        self.assertIsNone(self._watermark_text(self._render(self.partner)))

    # -- the rules refuse nonsense -----------------------------------------

    def test_a_domain_that_does_not_work_is_refused(self):
        with self.assertRaises(ValidationError):
            self._rule(domain="[('not_a_field', '=', 1)]")

    def test_an_impossible_opacity_is_refused(self):
        with self.assertRaises(ValidationError):
            self._rule(opacity=0)
        with self.assertRaises(ValidationError):
            self._rule(opacity=1.5)

    def test_a_word_with_an_angle_bracket_cannot_break_the_drawing(self):
        """The text goes into an SVG, so it has to be escaped."""
        self._rule(text='<DRAFT>')
        svg = self._watermark_svg(self._render(self.partner))
        self.assertIn('&lt;DRAFT&gt;', svg)
        self.assertNotIn('<DRAFT>', svg)
