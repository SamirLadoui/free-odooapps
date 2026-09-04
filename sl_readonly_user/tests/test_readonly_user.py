# -*- coding: utf-8 -*-
"""What a read-only account cannot do, and what it still must be able to do."""
from odoo import release
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestReadOnlyUser(TransactionCase):

    def setUp(self):
        super().setUp()
        self.groups_field = ('group_ids'
                             if 'group_ids' in self.env['res.users']._fields
                             else 'groups_id')
        self.read_only_group = self.env.ref(
            'sl_readonly_user.group_read_only')
        self.partner = self.env['res.partner'].create({'name': 'Existing'})
        self.looker = self._user('sl_readonly_looker', self.read_only_group)
        self.doer = self._user('sl_readonly_doer')

    def _user(self, login, extra=None):
        groups = self.env.ref('base.group_user')
        groups |= self.env.ref('base.group_partner_manager')
        if extra:
            groups |= extra
        return self.env['res.users'].create({
            'name': login, 'login': login,
            self.groups_field: [(6, 0, groups.ids)],
        })

    # -- refused -----------------------------------------------------------

    def test_it_cannot_create(self):
        with self.assertRaises(AccessError):
            self.env['res.partner'].with_user(self.looker).create(
                {'name': 'New Partner'})

    def test_it_cannot_write(self):
        with self.assertRaises(AccessError):
            self.partner.with_user(self.looker).write({'name': 'Renamed'})
        self.assertEqual(self.partner.name, 'Existing')

    def test_it_cannot_delete(self):
        with self.assertRaises(AccessError):
            self.partner.with_user(self.looker).unlink()
        self.assertTrue(self.partner.exists())

    def test_the_refusal_names_what_was_being_changed(self):
        with self.assertRaises(AccessError) as caught:
            self.partner.with_user(self.looker).write({'name': 'Renamed'})
        self.assertIn('read-only', str(caught.exception))

    def test_it_is_refused_on_every_model_not_just_partners(self):
        """The point of a group rather than a table of tick boxes."""
        with self.assertRaises(AccessError):
            self.env['res.partner.category'].with_user(self.looker).create(
                {'name': 'A Tag'})

    def test_it_cannot_give_itself_another_group(self):
        """Otherwise a read-only account can quietly stop being one."""
        system = self.env.ref('base.group_system')
        with self.assertRaises(AccessError):
            self.looker.with_user(self.looker).write(
                {self.groups_field: [(4, system.id)]})
        self.assertFalse(self.looker.has_group('base.group_system'))

    def test_it_cannot_take_the_group_off_itself(self):
        with self.assertRaises(AccessError):
            self.looker.with_user(self.looker).write(
                {self.groups_field: [(3, self.read_only_group.id)]})
        self.assertTrue(self.looker._sl_is_read_only())

    # -- still allowed -----------------------------------------------------

    def test_it_can_still_read(self):
        found = self.env['res.partner'].with_user(self.looker).search(
            [('id', '=', self.partner.id)])
        self.assertEqual(found, self.partner)
        self.assertEqual(found.name, 'Existing')

    def test_it_can_still_set_its_own_preferences(self):
        """Odoo handles these itself, and an account that cannot set its own
        timezone is not usable."""
        self.looker.with_user(self.looker).write({'tz': 'Europe/Paris'})
        self.assertEqual(self.looker.tz, 'Europe/Paris')

    def test_an_ordinary_user_is_untouched(self):
        partner = self.env['res.partner'].with_user(self.doer).create(
            {'name': 'Made By Somebody Else'})
        self.assertTrue(partner.exists())
        partner.write({'name': 'And Renamed'})
        self.assertEqual(partner.name, 'And Renamed')

    def test_server_code_running_as_superuser_still_works(self):
        """Refusing that would break logging in rather than protect data."""
        partner = self.env['res.partner'].with_user(self.looker).sudo().create(
            {'name': 'Made By The Server'})
        self.assertTrue(partner.exists())

    def test_the_models_the_client_needs_are_left_alone(self):
        """The web client writes to a handful of models just to work.

        Asked of the rule rather than by writing one: Odoo's own access
        rights refuse most of them to an ordinary user anyway, so a create
        that failed would say nothing about this module.
        """
        allowed = self.env['res.users.log'].with_user(self.looker)
        blocked = self.env['res.partner'].with_user(self.looker)
        self.assertFalse(allowed._sl_read_only_denied('create'))
        self.assertTrue(blocked._sl_read_only_denied('create'))

    def test_reading_is_never_denied_by_this_module(self):
        looker = self.env['res.partner'].with_user(self.looker)
        self.assertFalse(looker._sl_read_only_denied('read'))

    # -- what the client is told -------------------------------------------

    def test_the_client_is_told_before_it_offers_the_button(self):
        if release.version_info[0] < 18:
            self.skipTest('has_access arrived in 18.0')
        partners = self.env['res.partner'].with_user(self.looker)
        self.assertTrue(partners.has_access('read'))
        self.assertFalse(partners.has_access('write'))
        self.assertFalse(partners.has_access('create'))
        self.assertFalse(partners.has_access('unlink'))
