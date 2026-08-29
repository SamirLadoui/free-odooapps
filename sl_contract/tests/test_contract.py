# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestContract(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': 'Contract Customer'})
        cls.journal = cls.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', cls.company.id)], limit=1)
        if not cls.journal:
            cls.journal = cls.env['account.journal'].create({
                'name': 'Contract Sales', 'code': 'CSAL',
                'type': 'sale', 'company_id': cls.company.id})
        cls.product = cls.env['product.product'].create({
            'name': 'Support Retainer', 'list_price': 100.0, 'type': 'service'})

    def _contract(self, lines=True, **values):
        contract = self.env['sl.contract'].create(dict({
            'name': 'Test Contract',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'journal_id': self.journal.id,
            'date_start': date(2026, 1, 1),
            'recurring_interval': 1,
            'recurring_rule_type': 'monthly',
            'recurring_invoicing_type': 'pre-paid',
        }, **values))
        if lines:
            self.env['sl.contract.line'].create({
                'contract_id': contract.id,
                'name': 'Monthly support',
                'product_id': self.product.id,
                'quantity': 2.0,
                'price_unit': 100.0,
            })
        return contract

    # -- the schedule ------------------------------------------------------

    def test_next_invoice_defaults_to_the_start(self):
        contract = self._contract()
        self.assertEqual(contract.next_invoice_date, date(2026, 1, 1))

    def test_monthly_period_in_advance(self):
        contract = self._contract()
        start, end = contract._period_for(date(2026, 1, 1))
        self.assertEqual(start, date(2026, 1, 1))
        self.assertEqual(end, date(2026, 1, 31), "the period ends the day before the next")

    def test_monthly_period_in_arrears(self):
        contract = self._contract(recurring_invoicing_type='post-paid')
        start, end = contract._period_for(date(2026, 2, 1))
        self.assertEqual(start, date(2026, 1, 1))
        self.assertEqual(end, date(2026, 1, 31))

    def test_yearly_period(self):
        contract = self._contract(recurring_rule_type='yearly')
        start, end = contract._period_for(date(2026, 1, 1))
        self.assertEqual(end, date(2026, 12, 31))

    def test_multi_month_interval(self):
        contract = self._contract(recurring_interval=3)
        start, end = contract._period_for(date(2026, 1, 1))
        self.assertEqual(end, date(2026, 3, 31))
        self.assertEqual(contract._next_date_after(date(2026, 1, 1)), date(2026, 4, 1))

    def test_weekly_and_daily(self):
        weekly = self._contract(recurring_rule_type='weekly')
        self.assertEqual(weekly._next_date_after(date(2026, 1, 1)), date(2026, 1, 8))
        daily = self._contract(lines=False, recurring_rule_type='daily')
        self.assertEqual(daily._next_date_after(date(2026, 1, 1)), date(2026, 1, 2))

    def test_interval_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self._contract(lines=False, recurring_interval=0)

    def test_end_cannot_precede_start(self):
        with self.assertRaises(ValidationError):
            self._contract(lines=False, date_end=date(2025, 1, 1))

    # -- what is due -------------------------------------------------------

    def test_draft_contracts_are_never_due(self):
        contract = self._contract()
        self.assertFalse(contract._is_due(date(2026, 6, 1)))

    def test_running_contract_is_due_once_the_date_arrives(self):
        contract = self._contract()
        contract.action_start()
        self.assertFalse(contract._is_due(date(2025, 12, 31)))
        self.assertTrue(contract._is_due(date(2026, 1, 1)))
        self.assertTrue(contract._is_due(date(2026, 3, 1)))

    def test_contract_without_lines_is_not_due(self):
        contract = self._contract(lines=False)
        contract.state = 'open'
        contract.next_invoice_date = date(2026, 1, 1)
        self.assertFalse(contract._is_due(date(2026, 6, 1)))

    def test_contract_past_its_end_date_is_not_due(self):
        contract = self._contract(date_end=date(2026, 2, 15))
        contract.action_start()
        contract.next_invoice_date = date(2026, 3, 1)
        self.assertFalse(contract._is_due(date(2026, 6, 1)))

    # -- invoicing ---------------------------------------------------------

    def test_invoice_carries_the_lines_and_amount(self):
        contract = self._contract()
        contract.action_start()
        invoice = contract._create_invoice()
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.partner_id, self.partner)
        self.assertEqual(len(invoice.invoice_line_ids), 1)
        line = invoice.invoice_line_ids
        self.assertEqual(line.quantity, 2.0)
        self.assertEqual(line.price_unit, 100.0)

    def test_invoice_description_names_the_period(self):
        contract = self._contract()
        contract.action_start()
        invoice = contract._create_invoice()
        self.assertIn('2026-01-01', invoice.invoice_line_ids.name)
        self.assertIn('2026-01-31', invoice.invoice_line_ids.name)

    def test_invoicing_advances_the_schedule(self):
        contract = self._contract()
        contract.action_start()
        contract._create_invoice()
        self.assertEqual(contract.next_invoice_date, date(2026, 2, 1))
        contract._create_invoice()
        self.assertEqual(contract.next_invoice_date, date(2026, 3, 1))

    def test_invoice_is_linked_back_to_the_contract(self):
        contract = self._contract()
        contract.action_start()
        invoice = contract._create_invoice()
        self.assertEqual(invoice.sl_contract_id, contract)
        self.assertEqual(contract.invoice_count, 1)

    def test_discount_reaches_the_invoice(self):
        contract = self._contract()
        contract.line_ids.discount = 10.0
        contract.action_start()
        invoice = contract._create_invoice()
        self.assertEqual(invoice.invoice_line_ids.discount, 10.0)

    def test_contract_closes_itself_at_the_end_date(self):
        """The last period is invoiced, then the contract stops."""
        contract = self._contract(date_end=date(2026, 1, 31))
        contract.action_start()
        contract._create_invoice()
        self.assertEqual(contract.next_invoice_date, date(2026, 2, 1))
        self.assertEqual(contract.state, 'closed')

    def test_a_draft_contract_cannot_be_invoiced(self):
        contract = self._contract()
        with self.assertRaises(UserError):
            contract.action_create_invoice()

    # -- line date windows -------------------------------------------------

    def test_line_starting_later_is_not_billed_yet(self):
        contract = self._contract()
        contract.line_ids.date_start = date(2026, 6, 1)
        contract.action_start()
        with self.assertRaises(UserError):
            contract._create_invoice()

    def test_line_starting_later_is_billed_once_it_begins(self):
        contract = self._contract()
        contract.line_ids.date_start = date(2026, 6, 1)
        contract.action_start()
        invoice = contract._create_invoice(invoice_date=date(2026, 6, 1))
        self.assertEqual(len(invoice.invoice_line_ids), 1)

    def test_line_that_has_ended_is_dropped(self):
        contract = self._contract()
        contract.line_ids.date_end = date(2026, 1, 31)
        contract.action_start()
        contract._create_invoice(invoice_date=date(2026, 1, 1))
        with self.assertRaises(UserError):
            contract._create_invoice(invoice_date=date(2026, 2, 1))

    def test_covers_is_inclusive_at_both_edges(self):
        contract = self._contract()
        line = contract.line_ids
        line.write({'date_start': date(2026, 1, 15), 'date_end': date(2026, 1, 20)})
        self.assertTrue(line._covers(date(2026, 1, 1), date(2026, 1, 31)))
        self.assertTrue(line._covers(date(2026, 1, 20), date(2026, 1, 25)))
        self.assertFalse(line._covers(date(2026, 2, 1), date(2026, 2, 28)))
        self.assertFalse(line._covers(date(2025, 12, 1), date(2025, 12, 31)))

    # -- amounts and guards -------------------------------------------------

    def test_subtotal_applies_the_discount(self):
        contract = self._contract()
        line = contract.line_ids
        self.assertEqual(line.price_subtotal, 200.0)
        line.discount = 25.0
        self.assertEqual(line.price_subtotal, 150.0)
        self.assertEqual(contract.amount_total, 150.0)

    def test_line_amounts_are_validated(self):
        contract = self._contract()
        with self.assertRaises(ValidationError):
            contract.line_ids.quantity = 0
        with self.assertRaises(ValidationError):
            contract.line_ids.discount = 150

    def test_starting_needs_lines(self):
        contract = self._contract(lines=False)
        with self.assertRaises(UserError):
            contract.action_start()

    def test_reference_is_generated(self):
        self.assertTrue(self._contract(lines=False).code.startswith('CON/'))

    # -- the cron ----------------------------------------------------------

    def test_cron_invoices_only_what_is_due(self):
        due = self._contract()
        due.action_start()
        due.next_invoice_date = date(2020, 1, 1)

        later = self._contract(name='Not Yet')
        later.action_start()
        later.next_invoice_date = date(2099, 1, 1)

        self.env['sl.contract']._cron_recurring_invoices()
        self.assertEqual(due.invoice_count, 1)
        self.assertEqual(later.invoice_count, 0)
