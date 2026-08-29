# -*- coding: utf-8 -*-
import base64
import io
from collections import OrderedDict

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import UserError

COLUMNS = OrderedDict([
    ('default_code', ('Reference', 18)),
    ('name', ('Product', 42)),
    ('category', ('Category', 24)),
    ('uom', ('UoM', 10)),
    ('location', ('Location', 28)),
    ('lot', ('Lot / Serial', 20)),
    ('quantity', ('On Hand', 12)),
    ('reserved', ('Reserved', 12)),
    ('available', ('Available', 12)),
    ('forecast', ('Forecasted', 12)),
    ('cost', ('Unit Cost', 14)),
    ('value', ('Value', 16)),
])


class StockExportWizard(models.TransientModel):
    _name = 'sl.stock.export.wizard'
    _description = 'Export Product Stock to Excel'

    mode = fields.Selection(
        [('product', 'One row per product'),
         ('location', 'One row per product and location')],
        default='product', required=True,
        help="Per product gives you a stock summary. Per location breaks the "
             "same quantities down by where they physically are.")

    warehouse_ids = fields.Many2many(
        'stock.warehouse', string='Warehouses',
        help="Leave empty to cover every warehouse.")
    location_ids = fields.Many2many(
        'stock.location', string='Locations',
        domain="[('usage', '=', 'internal')]",
        help="Leave empty to cover every internal location of the selected warehouses.")
    category_ids = fields.Many2many('product.category', string='Product Categories')
    product_ids = fields.Many2many(
        'product.product', string='Products',
        help="Leave empty to export every storable product matching the other filters.")

    include_zero = fields.Boolean(
        string='Include Products With No Stock', default=False)
    include_lots = fields.Boolean(
        string='Break Down By Lot / Serial', default=False,
        help="Only meaningful when exporting one row per location.")
    include_valuation = fields.Boolean(
        string='Include Cost And Value', default=True)

    file_data = fields.Binary(readonly=True, attachment=False)
    file_name = fields.Char(readonly=True)

    @api.onchange('mode')
    def _onchange_mode(self):
        if self.mode == 'product':
            self.include_lots = False

    # -- data --------------------------------------------------------------

    def _product_domain(self):
        """Every filter narrows the selection; naming products does not widen it."""
        self.ensure_one()
        # 18.0 replaced the 'product' product type with consu + is_storable.
        storable = ([('is_storable', '=', True)]
                    if 'is_storable' in self.env['product.product']._fields
                    else [('type', '=', 'product')])
        domain = list(storable)
        if self.product_ids:
            domain += [('id', 'in', self.product_ids.ids)]
        if self.category_ids:
            domain += [('categ_id', 'child_of', self.category_ids.ids)]
        return domain

    def _locations(self):
        """The internal locations this export covers, or an empty recordset for all."""
        self.ensure_one()
        if self.location_ids:
            return self.location_ids
        if self.warehouse_ids:
            return self.warehouse_ids.mapped('view_location_id')
        return self.env['stock.location']

    def _collect_rows(self):
        """Return the export as a list of dicts keyed by COLUMNS.

        Kept separate from the spreadsheet writing so the selection logic can be
        tested without parsing a binary file.
        """
        self.ensure_one()
        return (self._collect_by_location() if self.mode == 'location'
                else self._collect_by_product())

    def _collect_by_product(self):
        self.ensure_one()
        locations = self._locations()
        products = self.env['product.product'].search(self._product_domain(), order='default_code, name')
        if locations:
            products = products.with_context(location=locations.ids)

        rows = []
        for product in products:
            quantity = product.qty_available
            if not quantity and not self.include_zero:
                continue
            rows.append({
                'default_code': product.default_code or '',
                'name': product.display_name,
                'category': product.categ_id.display_name or '',
                'uom': product.uom_id.name or '',
                'location': '',
                'lot': '',
                'quantity': quantity,
                'reserved': product.outgoing_qty,
                'available': quantity - product.outgoing_qty,
                'forecast': product.virtual_available,
                'cost': product.standard_price,
                'value': quantity * product.standard_price,
            })
        return rows

    def _collect_by_location(self):
        self.ensure_one()
        domain = [('location_id.usage', '=', 'internal')]
        locations = self._locations()
        if locations:
            domain += [('location_id', 'child_of', locations.ids)]
        products = self.env['product.product'].search(self._product_domain())
        domain += [('product_id', 'in', products.ids)]

        quants = self.env['stock.quant'].search(domain, order='product_id, location_id')
        rows = []
        for quant in quants:
            if not quant.quantity and not self.include_zero:
                continue
            rows.append({
                'default_code': quant.product_id.default_code or '',
                'name': quant.product_id.display_name,
                'category': quant.product_id.categ_id.display_name or '',
                'uom': quant.product_uom_id.name or '',
                'location': quant.location_id.complete_name or '',
                'lot': quant.lot_id.name or '' if self.include_lots else '',
                'quantity': quant.quantity,
                'reserved': quant.reserved_quantity,
                'available': quant.quantity - quant.reserved_quantity,
                'forecast': quant.quantity,
                'cost': quant.product_id.standard_price,
                'value': quant.quantity * quant.product_id.standard_price,
            })
        return rows

    def _active_columns(self):
        self.ensure_one()
        skip = set()
        if self.mode == 'product':
            skip |= {'location', 'lot'}
        elif not self.include_lots:
            skip.add('lot')
        if not self.include_valuation:
            skip |= {'cost', 'value'}
        return [key for key in COLUMNS if key not in skip]

    # -- spreadsheet -------------------------------------------------------

    def _build_xlsx(self, rows, columns):
        self.ensure_one()
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})
        sheet = book.add_worksheet(_('Stock'))

        title = book.add_format({'bold': True, 'font_size': 14})
        head = book.add_format({'bold': True, 'bg_color': '#DDDDDD', 'border': 1,
                                'align': 'center', 'valign': 'vcenter', 'text_wrap': True})
        text = book.add_format({'border': 1})
        number = book.add_format({'border': 1, 'num_format': '#,##0.00'})

        sheet.write(0, 0, _('Stock Export'), title)
        sheet.write(1, 0, _('Generated on %s') % fields.Datetime.now())
        header_row = 3

        for index, key in enumerate(columns):
            label, width = COLUMNS[key]
            sheet.write(header_row, index, label, head)
            sheet.set_column(index, index, width)

        numeric = {'quantity', 'reserved', 'available', 'forecast', 'cost', 'value'}
        for offset, row in enumerate(rows, start=header_row + 1):
            for index, key in enumerate(columns):
                value = row[key]
                sheet.write(offset, index, value, number if key in numeric else text)

        sheet.freeze_panes(header_row + 1, 0)
        if rows:
            sheet.autofilter(header_row, 0, header_row + len(rows), len(columns) - 1)
        book.close()
        return stream.getvalue()

    def action_export(self):
        self.ensure_one()
        rows = self._collect_rows()
        if not rows:
            raise UserError(_(
                "Nothing to export. No stock matches these filters - tick "
                "'Include Products With No Stock' if you wanted an empty-stock listing."))

        content = self._build_xlsx(rows, self._active_columns())
        self.write({
            'file_data': base64.b64encode(content),
            'file_name': 'stock_export_%s.xlsx' % fields.Date.today(),
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%s/file_data/%s?download=true' % (
                self._name, self.id, self.file_name),
            'target': 'self',
        }
