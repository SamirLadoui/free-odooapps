# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

MAX_COLUMNS = 10
MAX_ROWS = 30
MAX_COPIES = 100


class LabelWizard(models.TransientModel):
    _name = 'sl.label.wizard'
    _description = 'Print Labels'

    res_model = fields.Char(
        string='Model', required=True, readonly=True,
        help='Technical name of the model the labels are printed for.')
    res_ids = fields.Text(
        string='Records', required=True, readonly=True,
        help='Comma separated ids of the records to print.')
    record_count = fields.Integer(
        string='Records Selected', compute='_compute_record_count')

    columns = fields.Integer(string='Labels per Row', default=3, required=True)
    rows = fields.Integer(string='Rows per Page', default=8, required=True)
    copies = fields.Integer(
        string='Copies of Each', default=1, required=True,
        help='How many identical labels to print for every record selected.')

    show_code = fields.Boolean(
        string='Print Internal Reference', default=True,
        help='Only has an effect on models that have a reference field.')
    show_barcode = fields.Boolean(
        string='Print Barcode', default=True,
        help='Only has an effect on models that have a barcode field.')
    show_price = fields.Boolean(
        string='Print Sales Price',
        help='Only has an effect on models that have a sales price.')

    # -- validation --------------------------------------------------------

    @api.constrains('columns', 'rows')
    def _check_grid(self):
        for wizard in self:
            if not 1 <= wizard.columns <= MAX_COLUMNS:
                raise ValidationError(_(
                    'Labels per row must be between 1 and %s.', MAX_COLUMNS))
            if not 1 <= wizard.rows <= MAX_ROWS:
                raise ValidationError(_(
                    'Rows per page must be between 1 and %s.', MAX_ROWS))

    @api.constrains('copies')
    def _check_copies(self):
        for wizard in self:
            if not 1 <= wizard.copies <= MAX_COPIES:
                raise ValidationError(_(
                    'Copies of each must be between 1 and %s.', MAX_COPIES))

    @api.depends('res_ids')
    def _compute_record_count(self):
        for wizard in self:
            wizard.record_count = len(wizard._selected_ids())

    # -- the records -------------------------------------------------------

    def _selected_ids(self):
        """The ids stored on the wizard, as a clean list of integers."""
        self.ensure_one()
        ids = []
        for chunk in (self.res_ids or '').split(','):
            chunk = chunk.strip()
            if chunk.isdigit():
                ids.append(int(chunk))
        return ids

    def _selected_records(self):
        """The records still present, checked against the user's rights.

        A record can be deleted between opening the wizard and printing it, so
        the ids are filtered rather than read blindly.
        """
        self.ensure_one()
        if self.res_model not in self.env:
            raise UserError(_('Labels cannot be printed for "%s".', self.res_model))
        records = self.env[self.res_model].browse(self._selected_ids()).exists()
        records.check_access_rights('read')
        records.check_access_rule('read')
        return records

    # -- what goes on a label ---------------------------------------------

    def _label_values(self, record):
        """One label's worth of text. Fields the model does not have are
        skipped rather than raising, so this works on any model."""
        self.ensure_one()
        fields_ = record._fields
        values = {'name': record.display_name, 'code': '', 'barcode': '', 'price': ''}
        if self.show_code and 'default_code' in fields_:
            values['code'] = record.default_code or ''
        if self.show_barcode and 'barcode' in fields_:
            values['barcode'] = record.barcode or ''
        if self.show_price and 'list_price' in fields_:
            currency = record.currency_id if 'currency_id' in fields_ else None
            symbol = currency.symbol if currency else ''
            values['price'] = '%s %s' % (symbol, record.list_price) if symbol \
                else '%s' % record.list_price
        return values

    def _label_pages(self):
        """The labels laid out as pages of rows of cells.

        The last row of the last page is padded with empty cells so the table
        keeps its shape; without the padding the final row stretches its cells
        across the page and the labels do not line up with the sheet.
        """
        self.ensure_one()
        records = self._selected_records()
        if not records:
            raise UserError(_('There is nothing selected to print.'))

        labels = []
        for record in records:
            labels.extend([self._label_values(record)] * self.copies)

        per_page = self.columns * self.rows
        pages = []
        for start in range(0, len(labels), per_page):
            page = labels[start:start + per_page]
            rows = [page[i:i + self.columns]
                    for i in range(0, len(page), self.columns)]
            rows[-1] += [None] * (self.columns - len(rows[-1]))
            pages.append(rows)
        return pages

    # -- printing ----------------------------------------------------------

    def action_print(self):
        self.ensure_one()
        self._label_pages()  # fail here rather than inside the pdf renderer
        return self.env.ref('sl_mass_label.action_report_label_sheet') \
            .report_action(self)

    @api.model
    def default_get(self, fields_list):
        """Pick the selection up from the context the action passes in."""
        result = super().default_get(fields_list)
        context = self.env.context
        model = context.get('active_model')
        ids = context.get('active_ids') or (
            [context['active_id']] if context.get('active_id') else [])
        if model:
            result['res_model'] = model
        if ids:
            result['res_ids'] = ','.join(str(i) for i in ids)
        return result
