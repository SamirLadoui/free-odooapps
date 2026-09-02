# -*- coding: utf-8 -*-
"""What is refused, what is allowed, and who is never asked."""
from datetime import timedelta

from odoo import fields, release
from odoo.exceptions import AccessDenied, UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPasswordPolicy(TransactionCase):

    def setUp(self):
        super().setUp()
        self.params = self.env['ir.config_parameter'].sudo()
        self.user = self.env['res.users'].create({
            'name': 'Policy Subject',
            'login': 'sl_policy_subject',
            'password': 'Correct-Horse-9',
        })

    def _policy(self, **values):
        for key, value in values.items():
            self.params.set_param('sl_password_policy.%s' % key, value)

    def _set(self, password, user=None):
        (user or self.user).write({'password': password})

    def _login(self, password, user=None):
        """What Odoo's own login does, minus the session.

        with_user matters: Odoo checks the password of the user the
        environment belongs to, not of the recordset it is called on.
        """
        user = user or self.user
        checker = user.with_user(user).sudo()
        environment = {'interactive': False}
        # The signature changed in 18.0.
        if release.version_info[0] >= 18:
            return checker._check_credentials(
                {'login': user.login, 'password': password, 'type': 'password'},
                environment)
        return checker._check_credentials(password, environment)

    # -- complexity --------------------------------------------------------

    def test_nothing_is_required_by_default(self):
        """An installed module that changes behaviour on its own is a trap."""
        self._set('anything at all really')
        self.assertTrue(self.user.sl_password_date)

    def test_a_capital_can_be_required(self):
        self._policy(uppercase=True)
        with self.assertRaises(UserError):
            self._set('no capitals here 9')
        self._set('One Capital Here 9')

    def test_a_small_letter_can_be_required(self):
        self._policy(lowercase=True)
        with self.assertRaises(UserError):
            self._set('SHOUTING ONLY 9')
        self._set('Some small letters 9')

    def test_a_digit_can_be_required(self):
        self._policy(digit=True)
        with self.assertRaises(UserError):
            self._set('letters only please')
        self._set('letters and 1 digit')

    def test_a_symbol_can_be_required(self):
        self._policy(special=True)
        with self.assertRaises(UserError):
            self._set('letters and 9 digits')
        with self.assertRaises(UserError):
            # A space is not a symbol: a rule met by pressing the space bar
            # is not a rule.
            self._set('spaces are not symbols')
        self._set('letters and a comma,')

    def test_the_message_says_what_is_missing(self):
        self._policy(uppercase=True, digit=True)
        with self.assertRaises(UserError) as caught:
            self._set('nothing much here')
        message = str(caught.exception)
        self.assertIn('capital', message)
        self.assertIn('digit', message)

    def test_all_the_rules_together(self):
        self._policy(uppercase=True, lowercase=True, digit=True, special=True)
        with self.assertRaises(UserError):
            self._set('Missing A Symbol 9')
        self._set('Has-Everything-9')

    # -- not the same one again -------------------------------------------

    def test_a_recent_password_cannot_come_back(self):
        self._policy(history=3)
        self._set('First-Password-1')
        with self.assertRaises(UserError):
            self._set('First-Password-1')

    def test_an_old_enough_password_can_come_back(self):
        """Remembering three means the fourth change frees the first."""
        self._policy(history=2)
        self._set('Alpha-Password-1')
        self._set('Bravo-Password-2')
        self._set('Charlie-Password-3')
        self._set('Alpha-Password-1')

    def test_remembering_nothing_allows_anything(self):
        self._policy(history=0)
        self._set('Repeated-Password-1')
        self._set('Repeated-Password-1')

    def test_one_account_does_not_constrain_another(self):
        self._policy(history=3)
        other = self.env['res.users'].create({
            'name': 'Someone Else', 'login': 'sl_policy_other',
            'password': 'Shared-Password-1'})
        self._set('Shared-Password-1')
        self.assertTrue(other.sl_password_date)

    def test_the_password_itself_is_never_stored(self):
        self._policy(history=2)
        self._set('Plain-Text-Check-1')
        history = self.env['sl.password.history'].sudo().search(
            [('user_id', '=', self.user.id)])
        self.assertTrue(history)
        for entry in history:
            self.assertNotIn('Plain-Text-Check-1', entry.password_hash)

    def test_only_the_last_few_are_kept(self):
        self._policy(history=2)
        for password in ('One-Password-1', 'Two-Password-2', 'Three-Password-3'):
            self._set(password)
        history = self.env['sl.password.history'].sudo().search_count(
            [('user_id', '=', self.user.id)])
        self.assertEqual(history, 2)

    # -- expiry ------------------------------------------------------------

    def _age(self, days):
        self.user.sudo().write({
            'sl_password_date': fields.Datetime.now() - timedelta(days=days)})

    def test_a_password_expires(self):
        self._policy(expiry_days=30)
        self._age(31)
        with self.assertRaises(AccessDenied):
            self._login('Correct-Horse-9')

    def test_a_fresh_password_does_not(self):
        self._policy(expiry_days=30)
        self._age(29)
        self._login('Correct-Horse-9')

    def test_expiry_can_be_turned_off(self):
        self._policy(expiry_days=0)
        self._age(3650)
        self._login('Correct-Horse-9')

    def test_a_password_with_no_recorded_date_is_treated_as_fresh(self):
        """Otherwise saving the setting locks out every existing user."""
        self._policy(expiry_days=30)
        self.user.sudo().write({'sl_password_date': False})
        self._login('Correct-Horse-9')

    def test_the_exempt_group_is_never_asked(self):
        self._policy(expiry_days=30)
        self._age(3650)
        group = self.env.ref('sl_password_policy.group_password_never_expires')
        field = ('group_ids' if 'group_ids' in self.user._fields
                 else 'groups_id')
        self.user.sudo().write({field: [(4, group.id)]})
        self._login('Correct-Horse-9')

    def test_changing_the_password_starts_the_clock_again(self):
        self._policy(expiry_days=30)
        self._age(31)
        self._set('Brand-New-Password-1')
        self._login('Brand-New-Password-1')

    def test_the_wrong_password_is_still_refused(self):
        """The expiry check must not turn into a way in."""
        self._policy(expiry_days=0)
        with self.assertRaises(AccessDenied):
            self._login('not-the-password')
