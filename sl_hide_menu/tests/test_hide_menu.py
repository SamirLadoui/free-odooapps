# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestHideMenu(TransactionCase):

    def setUp(self):
        # 14.0 has no class-level env: setUpClass cannot build fixtures.
        super().setUp()
        groups_field = ('group_ids' if 'group_ids' in self.env['res.users']._fields
                        else 'groups_id')
        self.user = self.env['res.users'].create({
            'name': 'Menu User', 'login': 'sl_hide_menu_user',
            groups_field: [(6, 0, [self.env.ref('base.group_user').id])],
        })
        # Odoo hides menus that have neither an action nor a visible child, so
        # the fixtures need a real action to be visible in the first place.
        action = self.env.ref('base.action_partner_form')
        self.action_ref = '%s,%d' % (action._name, action.id)
        self.parent = self.env['ir.ui.menu'].create({'name': 'SL Parent Menu'})
        self.child = self.env['ir.ui.menu'].create({
            'name': 'SL Child Menu', 'parent_id': self.parent.id})
        self.grandchild = self.env['ir.ui.menu'].create({
            'name': 'SL Grandchild Menu', 'parent_id': self.child.id,
            'action': self.action_ref})
        self.unrelated = self.env['ir.ui.menu'].create({
            'name': 'SL Unrelated Menu', 'action': self.action_ref})

    def _hidden_for(self, user):
        return set(self.env['ir.ui.menu'].with_user(user)._sl_hidden_menu_ids())

    def _visible_for(self, user):
        return set(self.env['ir.ui.menu'].with_user(user)._visible_menu_ids())

    # -- what counts as hidden ---------------------------------------------

    def test_nothing_hidden_by_default(self):
        self.assertEqual(self._hidden_for(self.user), set())

    def test_hiding_one_menu(self):
        self.user.hidden_menu_ids = [(6, 0, self.unrelated.ids)]
        self.assertIn(self.unrelated.id, self._hidden_for(self.user))

    def test_hiding_a_parent_takes_its_children(self):
        """Otherwise the children are stranded with no way back to them."""
        self.user.hidden_menu_ids = [(6, 0, self.parent.ids)]
        hidden = self._hidden_for(self.user)
        self.assertIn(self.parent.id, hidden)
        self.assertIn(self.child.id, hidden)
        self.assertIn(self.grandchild.id, hidden)

    def test_hiding_a_child_leaves_the_parent(self):
        self.user.hidden_menu_ids = [(6, 0, self.child.ids)]
        hidden = self._hidden_for(self.user)
        self.assertNotIn(self.parent.id, hidden)
        self.assertIn(self.child.id, hidden)
        self.assertIn(self.grandchild.id, hidden)

    def test_unrelated_menus_are_untouched(self):
        self.user.hidden_menu_ids = [(6, 0, self.parent.ids)]
        self.assertNotIn(self.unrelated.id, self._hidden_for(self.user))

    # -- what the user actually sees ---------------------------------------

    def test_hidden_menus_leave_the_visible_set(self):
        before = self._visible_for(self.user)
        self.assertIn(self.unrelated.id, before,
                      "the fixture menu should be visible before anything is hidden")

        self.user.hidden_menu_ids = [(6, 0, self.unrelated.ids)]
        self.env.registry.clear_caches()
        after = self._visible_for(self.user)
        self.assertNotIn(self.unrelated.id, after)
        self.assertIn(self.grandchild.id, after,
                      "an unrelated menu must stay visible")

    def test_hiding_is_per_user(self):
        """One person's tidy menu must not tidy anyone else's."""
        other = self.env['res.users'].create({
            'name': 'Other Menu User', 'login': 'sl_hide_menu_other'})
        self.user.hidden_menu_ids = [(6, 0, self.unrelated.ids)]
        self.assertEqual(self._hidden_for(other), set())

    def test_unhiding_restores_the_menu(self):
        self.user.hidden_menu_ids = [(6, 0, self.unrelated.ids)]
        self.assertIn(self.unrelated.id, self._hidden_for(self.user))
        self.user.hidden_menu_ids = [(5, 0, 0)]
        self.assertEqual(self._hidden_for(self.user), set())

    def test_hiding_does_not_change_access_rights(self):
        """It is a tidier menu, not a security control."""
        self.user.hidden_menu_ids = [(6, 0, self.unrelated.ids)]
        partners = self.env['res.partner'].with_user(self.user).search([], limit=1)
        self.assertTrue(partners, "the user can still reach records by other means")
