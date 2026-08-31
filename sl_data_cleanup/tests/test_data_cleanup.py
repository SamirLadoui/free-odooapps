# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDataCleanup(TransactionCase):

    def setUp(self):
        # 14.0 has no class-level env: cls.env in setUpClass arrived in 15.0.
        super().setUp()
        self.dbname = self.env.cr.dbname
        self.keep_me = self.env['res.partner'].create({'name': 'Plain Contact'})
        self.user = self.env['res.users'].create({
            'name': 'Cleanup User', 'login': 'cleanup_user',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })

    def _wizard(self, **values):
        return self.env['sl.data.cleanup'].create(values)

    # -- the confirmation --------------------------------------------------

    def test_the_database_name_is_required(self):
        wizard = self._wizard(remove_partners=True)
        with self.assertRaises(UserError):
            wizard.action_remove()
        self.assertTrue(self.keep_me.exists(), 'data went despite no confirmation')

    def test_a_wrong_name_removes_nothing(self):
        wizard = self._wizard(remove_partners=True, confirmation='not-the-db')
        with self.assertRaises(UserError):
            wizard.action_remove()
        self.assertTrue(self.keep_me.exists())

    def test_the_name_is_stripped_before_comparing(self):
        """Typing it with a trailing space is not a reason to refuse."""
        wizard = self._wizard(remove_leads=True,
                              confirmation=' %s ' % self.dbname)
        wizard.action_remove()  # must not raise

    def test_nothing_selected_is_refused(self):
        wizard = self._wizard(confirmation=self.dbname)
        with self.assertRaises(UserError):
            wizard.action_remove()

    def test_the_database_name_is_shown_to_type(self):
        self.assertEqual(self._wizard().database_name, self.dbname)

    # -- who may run it ----------------------------------------------------

    def test_a_plain_user_cannot_remove(self):
        wizard = self._wizard(remove_partners=True, confirmation=self.dbname)
        with self.assertRaises(AccessError):
            wizard.with_user(self.user).action_remove()
        self.assertTrue(self.keep_me.exists())

    def test_a_plain_user_cannot_even_count(self):
        wizard = self._wizard(remove_partners=True)
        with self.assertRaises(AccessError):
            wizard.with_user(self.user).action_preview()

    # -- counting ----------------------------------------------------------

    def test_counting_removes_nothing(self):
        wizard = self._wizard(remove_partners=True)
        wizard.action_preview()
        self.assertTrue(self.keep_me.exists(), 'counting deleted data')
        self.assertIn('Contacts', wizard.preview)

    def test_counting_says_when_a_model_is_missing(self):
        wizard = self._wizard(remove_pos=True)
        wizard.action_preview()
        if 'pos.order' not in self.env:
            self.assertIn('not installed', wizard.preview)

    def test_counting_nothing_says_so(self):
        wizard = self._wizard()
        wizard.action_preview()
        self.assertIn('Nothing selected', wizard.preview)

    # -- what survives -----------------------------------------------------

    def test_company_contacts_are_kept(self):
        company_partner = self.env.company.partner_id
        wizard = self._wizard(remove_partners=True, confirmation=self.dbname)
        wizard.action_remove()
        self.assertTrue(company_partner.exists(),
                        'removing the company contact breaks the database')

    def test_user_contacts_are_kept(self):
        user_partner = self.user.partner_id
        wizard = self._wizard(remove_partners=True, confirmation=self.dbname)
        wizard.action_remove()
        self.assertTrue(user_partner.exists(),
                        'a user cannot log in without their contact')

    def test_a_plain_contact_is_removed(self):
        wizard = self._wizard(remove_partners=True, confirmation=self.dbname)
        wizard.action_remove()
        self.assertFalse(self.keep_me.exists())

    def test_an_uninstalled_model_is_skipped_quietly(self):
        wizard = self._wizard(remove_manufacturing=True, remove_pos=True,
                              confirmation=self.dbname)
        wizard.action_remove()  # must not raise on a small database

    def test_the_result_reports_what_went(self):
        wizard = self._wizard(remove_partners=True, confirmation=self.dbname)
        wizard.action_remove()
        self.assertIn('removed', wizard.preview)

    def test_only_the_ticked_categories_are_touched(self):
        # The module only depends on base, so product may not be installed.
        product = self.env['product.template'].create({'name': 'Kept Product'}) \
            if 'product.template' in self.env else None
        wizard = self._wizard(remove_leads=True, confirmation=self.dbname)
        wizard.action_remove()
        self.assertTrue(self.keep_me.exists(), 'unticked category was removed')
        if product is not None:
            self.assertTrue(product.exists(), 'unticked category was removed')
