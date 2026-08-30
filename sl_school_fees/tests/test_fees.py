# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSchoolFees(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.year = cls.env['sl.academic.year'].create({
            'name': '2026 / 2027', 'code': 'AY-FEE',
            'date_start': date(2026, 9, 1), 'date_end': date(2027, 6, 30)})
        cls.standard = cls.env['sl.school.standard'].create({
            'name': 'Grade 5', 'academic_year_id': cls.year.id, 'capacity': 0})
        cls.other_standard = cls.env['sl.school.standard'].create({
            'name': 'Grade 9', 'academic_year_id': cls.year.id, 'capacity': 0})
        cls.student = cls.env['sl.student'].create({
            'name': 'Fee Payer', 'standard_id': cls.standard.id})
        cls.student.action_enrol()

        cls.structure = cls.env['sl.fee.structure'].create({
            'name': 'Grade 5 Annual', 'academic_year_id': cls.year.id,
            'standard_ids': [(6, 0, cls.standard.ids)],
            'line_ids': [
                (0, 0, {'name': 'Tuition', 'amount': 1000.0}),
                (0, 0, {'name': 'Books', 'amount': 150.0}),
            ],
        })
        cls.year_wide = cls.env['sl.fee.structure'].create({
            'name': 'Whole Year Levy', 'academic_year_id': cls.year.id,
            'line_ids': [(0, 0, {'name': 'Levy', 'amount': 50.0})],
        })

    def _fee(self, **values):
        return self.env['sl.fee'].create(dict({
            'student_id': self.student.id,
            'structure_id': self.structure.id,
            'amount': 1150.0,
            'date_due': date(2026, 10, 1)}, **values))

    # -- structures --------------------------------------------------------

    def test_structure_total(self):
        self.assertEqual(self.structure.amount_total, 1150.0)

    def test_structure_names_are_unique_per_year(self):
        with self.assertRaises(ValidationError):
            self.env['sl.fee.structure'].create({
                'name': 'grade 5 annual', 'academic_year_id': self.year.id})

    def test_the_same_name_is_fine_in_another_year(self):
        other_year = self.env['sl.academic.year'].create({
            'name': '2027 / 2028', 'code': 'AY-FEE2',
            'date_start': date(2027, 9, 1), 'date_end': date(2028, 6, 30)})
        self.assertTrue(self.env['sl.fee.structure'].create({
            'name': 'Grade 5 Annual', 'academic_year_id': other_year.id}))

    def test_an_empty_class_list_means_the_whole_year(self):
        """Empty is "everyone", not "nobody"."""
        self.assertTrue(self.year_wide._covers(self.standard))
        self.assertTrue(self.year_wide._covers(self.other_standard))

    def test_a_named_class_list_is_a_restriction(self):
        self.assertTrue(self.structure._covers(self.standard))
        self.assertFalse(self.structure._covers(self.other_standard))

    def test_negative_fee_items_are_refused(self):
        with self.assertRaises(ValidationError):
            self.structure.line_ids[0].amount = -10

    # -- charging ----------------------------------------------------------

    def test_amount_fills_in_from_the_structure(self):
        fee = self.env['sl.fee'].new({
            'student_id': self.student.id, 'structure_id': self.structure.id})
        fee._onchange_structure_id()
        self.assertEqual(fee.amount, 1150.0)

    def test_reference_is_generated(self):
        self.assertTrue(self._fee().code.startswith('FEE/'))

    def test_a_structure_for_another_class_is_refused(self):
        """Charging the wrong class's fees is always a mistake."""
        outsider = self.env['sl.student'].create({
            'name': 'Other Class', 'standard_id': self.other_standard.id})
        outsider.action_enrol()
        with self.assertRaises(ValidationError):
            self._fee(student_id=outsider.id)

    def test_a_year_wide_structure_applies_to_any_class(self):
        outsider = self.env['sl.student'].create({
            'name': 'Any Class', 'standard_id': self.other_standard.id})
        outsider.action_enrol()
        self.assertTrue(self._fee(student_id=outsider.id,
                                  structure_id=self.year_wide.id, amount=50.0))

    def test_a_zero_fee_is_refused(self):
        with self.assertRaises(ValidationError):
            self._fee(amount=0)

    # -- overdue -----------------------------------------------------------

    def test_a_past_due_date_is_overdue(self):
        fee = self._fee(date_due=date.today() - timedelta(days=1))
        self.assertTrue(fee.is_overdue)

    def test_a_future_due_date_is_not_overdue(self):
        fee = self._fee(date_due=date.today() + timedelta(days=30))
        self.assertFalse(fee.is_overdue)

    def test_a_paid_fee_is_never_overdue(self):
        """Paying late is still paying."""
        fee = self._fee(date_due=date.today() - timedelta(days=10))
        self.assertTrue(fee.is_overdue)
        fee.action_mark_paid()
        self.assertFalse(fee.is_overdue)

    def test_a_cancelled_fee_is_not_overdue(self):
        fee = self._fee(date_due=date.today() - timedelta(days=10))
        fee.action_cancel()
        self.assertFalse(fee.is_overdue)

    # -- invoicing ---------------------------------------------------------

    def test_invoicing_creates_an_invoice_against_the_contact(self):
        fee = self._fee()
        invoice = fee.action_create_invoice()
        self.assertEqual(fee.state, 'invoiced')
        self.assertEqual(invoice.partner_id, self.student.partner_id)
        self.assertEqual(len(invoice.invoice_line_ids), 1)
        self.assertEqual(invoice.invoice_line_ids.price_unit, 1150.0)

    def test_the_invoice_is_linked_back(self):
        fee = self._fee()
        invoice = fee.action_create_invoice()
        self.assertEqual(fee.invoice_id, invoice)

    def test_invoicing_twice_is_refused(self):
        fee = self._fee()
        fee.action_create_invoice()
        with self.assertRaises(UserError):
            fee.action_create_invoice()

    def test_a_student_without_a_contact_is_told(self):
        applicant = self.env['sl.student'].create({
            'name': 'Not Enrolled', 'standard_id': self.standard.id})
        fee = self._fee(student_id=applicant.id)
        with self.assertRaises(UserError) as caught:
            fee.action_create_invoice()
        self.assertIn('contact', str(caught.exception).lower())

    # -- student totals ----------------------------------------------------

    def test_student_totals(self):
        first = self._fee()
        second = self._fee(structure_id=self.year_wide.id, amount=50.0)
        self.student.invalidate_recordset(['fee_total', 'fee_outstanding'])
        self.assertEqual(self.student.fee_total, 1200.0)
        self.assertEqual(self.student.fee_outstanding, 1200.0)

        first.action_mark_paid()
        self.student.invalidate_recordset(['fee_total', 'fee_outstanding'])
        self.assertEqual(self.student.fee_outstanding, 50.0)

    def test_cancelled_fees_leave_the_totals(self):
        fee = self._fee()
        self.student.invalidate_recordset(['fee_total'])
        self.assertEqual(self.student.fee_total, 1150.0)
        fee.action_cancel()
        self.student.invalidate_recordset(['fee_total', 'fee_outstanding'])
        self.assertEqual(self.student.fee_total, 0.0)
        self.assertEqual(self.student.fee_outstanding, 0.0)
