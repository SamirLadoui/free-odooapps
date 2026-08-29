# -*- coding: utf-8 -*-
import base64
import io
from collections import OrderedDict

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountReportWizard(models.TransientModel):
    _name = 'sl.account.report.wizard'
    _description = 'Standard Accounting Report'

    report_type = fields.Selection(
        [('general_ledger', 'General Ledger'),
         ('trial_balance', 'Trial Balance'),
         ('partner_ledger', 'Partner Ledger')],
        default='general_ledger', required=True)

    date_from = fields.Date(required=True, default=lambda self: self._default_date_from())
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    target_move = fields.Selection(
        [('posted', 'Posted entries only'), ('all', 'Posted and draft entries')],
        default='posted', required=True)
    display_account = fields.Selection(
        [('movement', 'With movements in the period'),
         ('not_zero', 'With a non-zero balance'),
         ('all', 'All accounts')],
        default='movement', required=True)

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    journal_ids = fields.Many2many('account.journal', string='Journals')
    account_ids = fields.Many2many('account.account', string='Accounts')
    partner_ids = fields.Many2many('res.partner', string='Partners')

    file_data = fields.Binary(readonly=True, attachment=False)
    file_name = fields.Char(readonly=True)

    @api.model
    def _default_date_from(self):
        today = fields.Date.context_today(self)
        return today.replace(month=1, day=1)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_to < wizard.date_from:
                raise ValidationError(_("The end date is before the start date."))

    # -- data --------------------------------------------------------------

    def _base_domain(self):
        """Everything except the date window, which differs between the
        in-period lines and the opening balance."""
        self.ensure_one()
        domain = [('company_id', '=', self.company_id.id)]
        domain += ([('parent_state', '=', 'posted')] if self.target_move == 'posted'
                   else [('parent_state', 'in', ('posted', 'draft'))])
        if self.journal_ids:
            domain += [('journal_id', 'in', self.journal_ids.ids)]
        if self.account_ids:
            domain += [('account_id', 'in', self.account_ids.ids)]
        if self.partner_ids:
            domain += [('partner_id', 'in', self.partner_ids.ids)]
        return domain

    def _period_domain(self):
        self.ensure_one()
        return self._base_domain() + [
            ('date', '>=', self.date_from), ('date', '<=', self.date_to)]

    def _opening_domain(self):
        self.ensure_one()
        return self._base_domain() + [('date', '<', self.date_from)]

    def _opening_balances(self):
        """{(account_id, partner_id): balance} carried into the period."""
        self.ensure_one()
        grouped = self.env['account.move.line'].read_group(
            self._opening_domain(),
            ['balance:sum'], ['account_id', 'partner_id'], lazy=False)
        opening = {}
        for row in grouped:
            key = (row['account_id'][0] if row['account_id'] else False,
                   row['partner_id'][0] if row['partner_id'] else False)
            opening[key] = row['balance']
        return opening

    def _lines(self):
        self.ensure_one()
        return self.env['account.move.line'].search(
            self._period_domain(), order='account_id, partner_id, date, id')

    def _keep_account(self, opening, movement, balance):
        self.ensure_one()
        if self.display_account == 'all':
            return True
        if self.display_account == 'movement':
            return bool(movement) or bool(opening)
        return bool(self.company_id.currency_id.compare_amounts(balance, 0.0))

    def _collect(self):
        """Report rows as plain dicts, so the shape can be tested without
        rendering a PDF or parsing a spreadsheet."""
        self.ensure_one()
        by_partner = self.report_type == 'partner_ledger'
        detailed = self.report_type != 'trial_balance'
        opening = self._opening_balances()

        groups = OrderedDict()
        for line in self._lines():
            key = (line.account_id.id, line.partner_id.id if by_partner else False)
            groups.setdefault(key, []).append(line)

        # Accounts with an opening balance but no movement still belong in the
        # report when the user asked for them.
        for key in opening:
            normalised = key if by_partner else (key[0], False)
            groups.setdefault(normalised, [])

        Account = self.env['account.account']
        Partner = self.env['res.partner']
        result = []
        for (account_id, partner_id), lines in groups.items():
            account = Account.browse(account_id)
            carried = sum(value for (acc, prt), value in opening.items()
                          if acc == account_id and (not by_partner or prt == partner_id))
            # `lines` is a plain list of records, not a recordset.
            debit = sum(line.debit for line in lines)
            credit = sum(line.credit for line in lines)
            balance = carried + debit - credit
            if not self._keep_account(carried, lines, balance):
                continue
            result.append({
                'account_code': account.code or '',
                'account_name': account.name or '',
                'partner_name': Partner.browse(partner_id).display_name if partner_id else '',
                'opening': carried,
                'debit': debit,
                'credit': credit,
                'balance': balance,
                'lines': [{
                    'date': line.date,
                    'move': line.move_id.name,
                    'journal': line.journal_id.code or line.journal_id.name,
                    'partner': line.partner_id.display_name or '',
                    'label': line.name or '',
                    'debit': line.debit,
                    'credit': line.credit,
                    'reconciled': bool(line.full_reconcile_id),
                } for line in lines] if detailed else [],
            })
        result.sort(key=lambda row: (row['account_code'], row['partner_name']))
        return result

    def _totals(self, rows):
        return {
            'opening': sum(row['opening'] for row in rows),
            'debit': sum(row['debit'] for row in rows),
            'credit': sum(row['credit'] for row in rows),
            'balance': sum(row['balance'] for row in rows),
        }

    # -- output ------------------------------------------------------------

    def _report_title(self):
        self.ensure_one()
        return dict(self._fields['report_type'].selection)[self.report_type]

    def action_print_pdf(self):
        self.ensure_one()
        if not self._collect():
            raise UserError(_("No entries match these filters."))
        return self.env.ref(
            'sl_account_standard_report.action_report_account_standard'
        ).report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        rows = self._collect()
        if not rows:
            raise UserError(_("No entries match these filters."))
        self.write({
            'file_data': base64.b64encode(self._build_xlsx(rows)),
            'file_name': '%s_%s_%s.xlsx' % (
                self.report_type, self.date_from, self.date_to),
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%s/file_data/%s?download=true' % (
                self._name, self.id, self.file_name),
            'target': 'self',
        }

    def _build_xlsx(self, rows):
        self.ensure_one()
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})
        sheet = book.add_worksheet(self._report_title()[:31])

        title = book.add_format({'bold': True, 'font_size': 14})
        head = book.add_format({'bold': True, 'bg_color': '#DDDDDD', 'border': 1})
        text = book.add_format({'border': 1})
        money = book.add_format({'border': 1, 'num_format': '#,##0.00'})
        bold_money = book.add_format({'border': 1, 'bold': True, 'num_format': '#,##0.00'})

        sheet.write(0, 0, self._report_title(), title)
        sheet.write(1, 0, _("%(company)s - %(start)s to %(end)s") % {
            'company': self.company_id.name,
            'start': self.date_from, 'end': self.date_to})
        sheet.write(2, 0, dict(self._fields['target_move'].selection)[self.target_move])

        columns = ['Code', 'Account']
        if self.report_type == 'partner_ledger':
            columns.append('Partner')
        columns += ['Opening', 'Debit', 'Credit', 'Balance']
        header_row = 4
        for index, label in enumerate(columns):
            sheet.write(header_row, index, label, head)
        sheet.set_column(0, 0, 14)
        sheet.set_column(1, 1, 42)
        sheet.set_column(2, len(columns) - 1, 16)

        row_index = header_row + 1
        for row in rows:
            values = [row['account_code'], row['account_name']]
            if self.report_type == 'partner_ledger':
                values.append(row['partner_name'])
            values += [row['opening'], row['debit'], row['credit'], row['balance']]
            for index, value in enumerate(values):
                sheet.write(row_index, index, value,
                            money if isinstance(value, float) else text)
            row_index += 1

        totals = self._totals(rows)
        sheet.write(row_index, 0, _("Total"), head)
        offset = len(columns) - 4
        for index, key in enumerate(('opening', 'debit', 'credit', 'balance')):
            sheet.write(row_index, offset + index, totals[key], bold_money)

        sheet.freeze_panes(header_row + 1, 0)
        book.close()
        return stream.getvalue()
