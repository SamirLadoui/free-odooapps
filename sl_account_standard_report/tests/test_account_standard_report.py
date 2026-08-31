# -*- coding: utf-8 -*-
import base64
import inspect
import io
import zipfile
from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAccountStandardReport(TransactionCase):

    def setUp(self):
        # 14.0 has no class-level env: setUpClass cannot build fixtures.
        super().setUp()
        self.company = self.env.company
        self.journal = self.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', self.company.id)], limit=1)
        if not self.journal:
            self.journal = self.env['account.journal'].create({
                'name': 'Report Test Journal', 'code': 'RPT',
                'type': 'general', 'company_id': self.company.id})

        # Create our own accounts rather than assuming a chart of accounts is
        # loaded: a bare test database may have none.
        self.account_a = self._account('SLT100', 'SL Report Test A')
        self.account_b = self._account('SLT200', 'SL Report Test B')

        self.partner_a = self.env['res.partner'].create({'name': 'Ledger Partner A'})
        self.partner_b = self.env['res.partner'].create({'name': 'Ledger Partner B'})

        # One entry before the window, two inside it.
        self._move(date(2025, 12, 31), 100.0, self.partner_a)
        self._move(date(2026, 2, 10), 250.0, self.partner_a)
        self._move(date(2026, 3, 15), 75.0, self.partner_b)

    def _account(self, code, name):
        Account = self.env['account.account']
        values = {'code': code, 'name': name}
        # 17.0 replaced user_type_id with the account_type selection.
        if 'account_type' in Account._fields:
            values['account_type'] = 'asset_current'
        else:
            values['user_type_id'] = self.env.ref(
                'account.data_account_type_current_assets').id
        # 19.0 made the company link many2many.
        if 'company_ids' in Account._fields:
            values['company_ids'] = [(6, 0, self.company.ids)]
        else:
            values['company_id'] = self.company.id
        return Account.create(values)

    def _move(self, when, amount, partner):
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': when,
            'journal_id': self.journal.id,
            'company_id': self.company.id,
            'line_ids': [
                (0, 0, {'account_id': self.account_a.id, 'partner_id': partner.id,
                        'debit': amount, 'credit': 0.0, 'name': 'test debit'}),
                (0, 0, {'account_id': self.account_b.id, 'partner_id': partner.id,
                        'debit': 0.0, 'credit': amount, 'name': 'test credit'}),
            ],
        })
        move.action_post()
        return move

    def _wizard(self, **values):
        return self.env['sl.account.report.wizard'].create(dict({
            'date_from': date(2026, 1, 1),
            'date_to': date(2026, 12, 31),
            'company_id': self.company.id,
            'display_account': 'movement',
        }, **values))

    def _row_for(self, rows, account):
        return next((r for r in rows if r['account_code'] == account.code), None)

    # -- filters -----------------------------------------------------------

    def test_dates_must_be_in_order(self):
        with self.assertRaises(ValidationError):
            self._wizard(date_from=date(2026, 6, 1), date_to=date(2026, 1, 1))

    def test_opening_balance_excludes_the_period(self):
        """The December entry is opening, not movement."""
        rows = self._wizard()._collect()
        row = self._row_for(rows, self.account_a)
        self.assertIsNotNone(row)
        self.assertAlmostEqual(row['opening'], 100.0, places=2)
        self.assertAlmostEqual(row['debit'], 325.0, places=2)
        self.assertAlmostEqual(row['balance'], 425.0, places=2)

    def test_period_window_is_respected(self):
        rows = self._wizard(date_from=date(2026, 3, 1), date_to=date(2026, 3, 31))._collect()
        row = self._row_for(rows, self.account_a)
        self.assertAlmostEqual(row['debit'], 75.0, places=2,
                               msg="only the March entry is in this window")
        self.assertAlmostEqual(row['opening'], 350.0, places=2,
                               msg="December and February are both carried in")

    def test_journal_filter(self):
        other = self.env['account.journal'].create({
            'name': 'Unused', 'code': 'UNU', 'type': 'general',
            'company_id': self.company.id})
        rows = self._wizard(journal_ids=[(6, 0, other.ids)])._collect()
        self.assertEqual(rows, [], "no entries in that journal")

    def test_account_filter(self):
        rows = self._wizard(account_ids=[(6, 0, self.account_a.ids)])._collect()
        self.assertEqual({r['account_code'] for r in rows}, {self.account_a.code})

    def test_partner_filter(self):
        rows = self._wizard(partner_ids=[(6, 0, self.partner_b.ids)])._collect()
        row = self._row_for(rows, self.account_a)
        self.assertAlmostEqual(row['debit'], 75.0, places=2)
        self.assertAlmostEqual(row['opening'], 0.0, places=2,
                               msg="partner B has nothing before the period")

    # -- report shapes -----------------------------------------------------

    def test_trial_balance_has_no_detail_lines(self):
        rows = self._wizard(report_type='trial_balance')._collect()
        self.assertTrue(rows)
        self.assertTrue(all(not r['lines'] for r in rows),
                        "a trial balance summarises, it does not list entries")

    def test_general_ledger_lists_entries(self):
        rows = self._wizard(report_type='general_ledger')._collect()
        row = self._row_for(rows, self.account_a)
        self.assertEqual(len(row['lines']), 2)
        self.assertTrue(all(line['move'] for line in row['lines']))

    def test_partner_ledger_splits_by_partner(self):
        rows = self._wizard(report_type='partner_ledger')._collect()
        for_a = [r for r in rows if r['account_code'] == self.account_a.code]
        names = {r['partner_name'] for r in for_a}
        self.assertIn(self.partner_a.display_name, names)
        self.assertIn(self.partner_b.display_name, names)

    def test_totals_balance_out(self):
        rows = self._wizard(report_type='trial_balance')._collect()
        totals = self._wizard()._totals(rows)
        self.assertAlmostEqual(totals['debit'], totals['credit'], places=2,
                               msg="a trial balance must balance")

    def test_draft_entries_only_when_asked(self):
        draft = self.env['account.move'].create({
            'move_type': 'entry', 'date': date(2026, 5, 1),
            'journal_id': self.journal.id, 'company_id': self.company.id,
            'line_ids': [
                (0, 0, {'account_id': self.account_a.id, 'debit': 999.0, 'credit': 0.0}),
                (0, 0, {'account_id': self.account_b.id, 'debit': 0.0, 'credit': 999.0}),
            ],
        })
        self.assertEqual(draft.state, 'draft')

        posted_only = self._row_for(self._wizard()._collect(), self.account_a)
        self.assertAlmostEqual(posted_only['debit'], 325.0, places=2)

        with_draft = self._row_for(self._wizard(target_move='all')._collect(), self.account_a)
        self.assertAlmostEqual(with_draft['debit'], 1324.0, places=2)

    # -- output ------------------------------------------------------------

    def test_xlsx_export(self):
        wizard = self._wizard()
        wizard.action_export_xlsx()
        self.assertTrue(wizard.file_name.endswith('.xlsx'))
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(wizard.file_data))) as book:
            self.assertIn('xl/workbook.xml', book.namelist())

    def test_empty_report_explains_itself(self):
        wizard = self._wizard(date_from=date(2000, 1, 1), date_to=date(2000, 12, 31),
                              display_account='movement')
        with self.assertRaises(UserError):
            wizard.action_export_xlsx()

    def test_pdf_renders(self):
        wizard = self._wizard()
        report = self.env.ref('sl_account_standard_report.action_report_account_standard')
        # 16.0 added a leading report_ref argument to _render_qweb_html.
        if 'report_ref' in inspect.signature(report._render_qweb_html).parameters:
            content, content_type = report._render_qweb_html(report.report_name, wizard.ids)
        else:
            content, content_type = report._render_qweb_html(wizard.ids)
        self.assertEqual(content_type, 'html')
        self.assertIn(self.account_a.code.encode(), content)
