# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestEmployeeDocuments(TransactionCase):

    def setUp(self):
        # 14.0 has no class-level env: setUpClass cannot build fixtures.
        super().setUp()
        self.today = fields.Date.context_today(self.env['sl.employee.document'])
        self.employee = self.env['hr.employee'].create({'name': 'Doc Holder'})
        self.passport = self.env['sl.employee.document.type'].create({
            'name': 'Passport', 'expires': True, 'reminder_days': 30})
        self.diploma = self.env['sl.employee.document.type'].create({
            'name': 'Diploma', 'expires': False})

    def _document(self, days_from_now=None, type_id=None, **values):
        expiry = self.today + timedelta(days=days_from_now) if days_from_now is not None else False
        return self.env['sl.employee.document'].create(dict({
            'name': 'Test Document',
            'employee_id': self.employee.id,
            'type_id': (type_id or self.passport).id,
            'expiry_date': expiry,
        }, **values))

    # -- the state that matters --------------------------------------------

    def test_far_off_document_is_valid(self):
        document = self._document(days_from_now=200)
        self.assertEqual(document.state, 'valid')
        self.assertEqual(document.days_to_expiry, 200)

    def test_document_inside_the_window_is_expiring(self):
        self.assertEqual(self._document(days_from_now=10).state, 'expiring')

    def test_document_on_the_window_edge_is_expiring(self):
        """Exactly reminder_days away still counts as expiring."""
        self.assertEqual(self._document(days_from_now=30).state, 'expiring')

    def test_document_just_outside_the_window_is_valid(self):
        self.assertEqual(self._document(days_from_now=31).state, 'valid')

    def test_document_expiring_today_is_expiring_not_expired(self):
        document = self._document(days_from_now=0)
        self.assertEqual(document.state, 'expiring')
        self.assertEqual(document.days_to_expiry, 0)

    def test_yesterday_is_expired(self):
        document = self._document(days_from_now=-1)
        self.assertEqual(document.state, 'expired')
        self.assertEqual(document.days_to_expiry, -1)

    def test_type_without_expiry_never_expires(self):
        document = self._document(days_from_now=-100, type_id=self.diploma)
        self.assertEqual(document.state, 'no_expiry')

    def test_missing_expiry_date_is_no_expiry(self):
        self.assertEqual(self._document().state, 'no_expiry')

    def test_window_follows_the_type(self):
        self.passport.reminder_days = 5
        self.assertEqual(self._document(days_from_now=10).state, 'valid')
        self.passport.reminder_days = 60
        self.assertEqual(self._document(days_from_now=10).state, 'expiring')

    # -- validation --------------------------------------------------------

    def test_expiry_cannot_precede_issue(self):
        with self.assertRaises(ValidationError):
            self._document(days_from_now=10, issue_date=self.today + timedelta(days=20))

    def test_reminder_window_cannot_be_negative(self):
        with self.assertRaises(ValidationError):
            self.passport.reminder_days = -1

    def test_document_type_names_are_unique(self):
        with self.assertRaises(ValidationError):
            self.env['sl.employee.document.type'].create({'name': 'passport'})

    # -- reminders ---------------------------------------------------------

    def test_only_expiring_and_expired_are_chased(self):
        valid = self._document(days_from_now=200)
        expiring = self._document(days_from_now=5)
        expired = self._document(days_from_now=-5)
        due = self.env['sl.employee.document']._documents_needing_reminder()
        self.assertIn(expiring, due)
        self.assertIn(expired, due)
        self.assertNotIn(valid, due)

    def test_a_document_is_not_chased_twice_in_a_day(self):
        document = self._document(days_from_now=5)
        document._notify_expiry()
        self.assertEqual(document.last_reminder_on, self.today)
        self.assertNotIn(
            document, self.env['sl.employee.document']._documents_needing_reminder())

    def test_yesterdays_reminder_does_not_block_todays(self):
        document = self._document(days_from_now=5)
        document.last_reminder_on = self.today - timedelta(days=1)
        self.assertIn(
            document, self.env['sl.employee.document']._documents_needing_reminder())

    def test_notify_posts_and_schedules_an_activity(self):
        responsible = self.env['res.users'].create({
            'name': 'Doc Owner', 'login': 'doc_owner_test'})
        document = self._document(days_from_now=5, responsible_id=responsible.id)
        before = len(document.message_ids)
        document._notify_expiry()
        self.assertGreater(len(document.message_ids), before)
        self.assertTrue(document.activity_ids)
        self.assertEqual(document.activity_ids[0].user_id, responsible)

    def test_notify_says_expired_for_expired_documents(self):
        document = self._document(days_from_now=-3)
        document._notify_expiry()
        self.assertIn('expired', document.message_ids[0].body)

    def test_cron_runs_over_everything_due(self):
        self._document(days_from_now=5)
        self._document(days_from_now=-5)
        self.env['sl.employee.document']._cron_notify_expiring()
        self.assertFalse(
            self.env['sl.employee.document']._documents_needing_reminder(),
            "every due document should have been chased")

    # -- employee rollup ---------------------------------------------------

    def test_employee_counts(self):
        self._document(days_from_now=200)
        self._document(days_from_now=5)
        self._document(days_from_now=-5)
        self.assertEqual(self.employee.document_count, 3)
        self.assertEqual(self.employee.expiring_document_count, 2)

    def test_display_name_names_the_employee(self):
        document = self._document(days_from_now=10)
        self.assertIn('Doc Holder', document.display_name)
