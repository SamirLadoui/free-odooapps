# -*- coding: utf-8 -*-
"""Who may take whose account, and what is written down when they do.

The feature is useful and also the most abusable thing an administrator can
do, so the tests are mostly about what it refuses.
"""
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestLoginAs(TransactionCase):

    def setUp(self):
        super().setUp()
        self.groups_field = ('group_ids' if 'group_ids' in self.env['res.users']._fields
                             else 'groups_id')
        self.erp_manager = self.env.ref('base.group_erp_manager')
        self.settings = self.env.ref('base.group_system')
        self.internal = self.env.ref('base.group_user')

        self.support = self._user('sl_support', [self.internal, self.erp_manager])
        self.plain = self._user('sl_plain', [self.internal])
        self.admin_like = self._user(
            'sl_admin_like', [self.internal, self.erp_manager, self.settings])

    def _user(self, login, groups):
        return self.env['res.users'].create({
            'name': login, 'login': login,
            self.groups_field: [(6, 0, [group.id for group in groups])],
        })

    # -- who may ------------------------------------------------------------

    def test_a_manager_may_take_a_plainer_account(self):
        self.assertTrue(self.support._sl_may_log_in_as(self.plain))

    def test_nobody_may_take_an_account_with_rights_they_lack(self):
        """The rule is containment, not seniority: taking a stronger account
        would be granting yourself its rights."""
        self.assertFalse(self.support._sl_may_log_in_as(self.admin_like))

    def test_somebody_without_the_manager_right_may_take_nobody(self):
        self.assertFalse(self.plain._sl_may_log_in_as(self.plain))
        other = self._user('sl_other', [self.internal])
        self.assertFalse(self.plain._sl_may_log_in_as(other))

    def test_nobody_takes_their_own_account(self):
        self.assertFalse(self.support._sl_may_log_in_as(self.support))

    def test_taking_a_stronger_account_raises(self):
        with self.assertRaises(AccessError):
            self.admin_like.with_user(self.support).sl_login_as('trying it on')

    # -- the reason ---------------------------------------------------------

    def test_a_reason_is_required(self):
        with self.assertRaises(UserError):
            self.plain.with_user(self.support).sl_login_as('')

    def test_whitespace_is_not_a_reason(self):
        with self.assertRaises(UserError):
            self.plain.with_user(self.support).sl_login_as('   ')

    def test_the_reason_is_kept_with_the_entry(self):
        self.plain.with_user(self.support).sl_login_as('ticket 4182, missing button')
        entry = self.env['sl.login.as.log'].search([], order='id desc', limit=1)
        self.assertEqual(entry.actor_user_id, self.support)
        self.assertEqual(entry.target_user_id, self.plain)
        self.assertIn('4182', entry.reason)
        self.assertTrue(entry.happened_on)

    # -- the record cannot be tidied away ----------------------------------

    def test_an_entry_cannot_be_edited(self):
        self.plain.with_user(self.support).sl_login_as('looking at a report')
        entry = self.env['sl.login.as.log'].search([], order='id desc', limit=1)
        with self.assertRaises(UserError):
            entry.reason = 'something else entirely'

    def test_an_entry_cannot_be_deleted_even_by_whoever_made_it(self):
        """A log an administrator can clean up is not a log."""
        self.plain.with_user(self.support).sl_login_as('looking at a report')
        entry = self.env['sl.login.as.log'].search([], order='id desc', limit=1)
        with self.assertRaises(UserError):
            entry.with_user(self.support).unlink()
        with self.assertRaises(UserError):
            entry.sudo().unlink()

    # -- the wizard ---------------------------------------------------------

    def test_the_wizard_says_why_it_will_not(self):
        wizard = self.env['sl.login.as.wizard'].with_user(self.support).create({
            'target_user_id': self.admin_like.id, 'reason': 'trying'})
        self.assertFalse(wizard.may_do_it)
        self.assertIn('rights yours does not', wizard.refusal)
        with self.assertRaises(AccessError):
            wizard.action_go()

    def test_the_wizard_writes_the_entry_and_sends_you_on(self):
        wizard = self.env['sl.login.as.wizard'].with_user(self.support).create({
            'target_user_id': self.plain.id, 'reason': 'ticket 51'})
        self.assertTrue(wizard.may_do_it)
        action = wizard.action_go()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertIn(str(self.plain.id), action['url'])
        entry = self.env['sl.login.as.log'].search([], order='id desc', limit=1)
        self.assertEqual(entry.target_user_id, self.plain)
        self.assertEqual(entry.reason, 'ticket 51')
