# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDeveloperMode(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.groups_field = ('group_ids' if 'group_ids' in cls.env['res.users']._fields
                            else 'groups_id')
        cls.admin = cls.env['res.users'].create({
            'name': 'Dev Admin', 'login': 'sl_dev_admin',
            cls.groups_field: [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('base.group_system').id,
            ])],
        })
        cls.plain = cls.env['res.users'].create({
            'name': 'Plain User', 'login': 'sl_dev_plain',
            cls.groups_field: [(6, 0, [cls.env.ref('base.group_user').id])],
        })

    def test_default_is_off(self):
        self.assertEqual(self.admin.auto_developer_mode, 'off')

    def test_an_administrator_can_enable_it(self):
        self.admin.auto_developer_mode = 'on'
        self.assertEqual(self.admin.auto_developer_mode, 'on')

    def test_assets_mode_is_allowed(self):
        self.admin.auto_developer_mode = 'assets'
        self.assertEqual(self.admin.auto_developer_mode, 'assets')

    def test_a_plain_user_cannot_be_put_into_developer_mode(self):
        """Developer mode exposes technical menus; only Settings admins qualify."""
        with self.assertRaises(ValidationError):
            self.plain.auto_developer_mode = 'on'

    def test_a_plain_user_may_still_be_off(self):
        self.plain.auto_developer_mode = 'off'
        self.assertEqual(self.plain.auto_developer_mode, 'off')

    def test_losing_admin_rights_is_caught_on_the_next_write(self):
        self.admin.auto_developer_mode = 'on'
        self.admin.write({self.groups_field: [
            (6, 0, [self.env.ref('base.group_user').id])]})
        with self.assertRaises(ValidationError):
            self.admin.auto_developer_mode = 'assets'

    def test_the_setting_is_self_writeable(self):
        """A developer should be able to turn it on for themselves."""
        self.assertIn('auto_developer_mode',
                      self.env['res.users'].SELF_WRITEABLE_FIELDS)
        self.assertIn('auto_developer_mode',
                      self.env['res.users'].SELF_READABLE_FIELDS)
