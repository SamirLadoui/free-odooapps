# -*- coding: utf-8 -*-
"""Who can see the cost, and what still works for everybody who cannot."""
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestHideCost(TransactionCase):

    def setUp(self):
        super().setUp()
        self.group = self.env.ref('sl_hide_cost.group_show_cost')
        self.product = self.env['product.product'].create({
            'name': 'Watched Widget', 'standard_price': 42.0,
            'list_price': 100.0})
        self.groups_field = ('group_ids'
                             if 'group_ids' in self.env['res.users']._fields
                             else 'groups_id')
        self._allow_managing_products()
        self.clerk = self._user('sl_hide_cost_clerk')
        self.buyer = self._user('sl_hide_cost_buyer', extra=self.group)

    def _allow_managing_products(self):
        """Let an ordinary user create products, whatever this release asks.

        Which group may create a product moved about between 14.0 and 19.0,
        and none of that is what these tests are about; the access is granted
        outright so the only thing left in the way is the cost field itself.
        """
        for model in ('product.template', 'product.product'):
            self.env['ir.model.access'].create({
                'name': 'sl_hide_cost test access %s' % model,
                'model_id': self.env['ir.model']._get(model).id,
                'group_id': self.env.ref('base.group_user').id,
                'perm_read': True, 'perm_write': True,
                'perm_create': True, 'perm_unlink': True,
            })

    def _user(self, login, extra=None):
        groups = self.env.ref('base.group_user')
        if extra:
            groups |= extra
        return self.env['res.users'].create({
            'name': login, 'login': login,
            self.groups_field: [(6, 0, groups.ids)],
        })

    # -- who sees it -------------------------------------------------------

    def test_an_ordinary_user_cannot_read_the_cost(self):
        with self.assertRaises(AccessError):
            self.product.with_user(self.clerk).read(['standard_price'])

    def test_a_member_of_the_group_can(self):
        [values] = self.product.with_user(self.buyer).read(['standard_price'])
        self.assertEqual(values['standard_price'], 42.0)

    def test_the_settings_administrator_can_out_of_the_box(self):
        """Installing it must not leave nobody able to see the cost."""
        self.assertTrue(self.env.ref('base.user_admin').has_group(
            'sl_hide_cost.group_show_cost'))

    def test_an_ordinary_user_cannot_write_the_cost(self):
        with self.assertRaises(AccessError):
            self.product.with_user(self.clerk).write({'standard_price': 1.0})
        self.assertEqual(self.product.standard_price, 42.0)

    def test_the_template_is_covered_too(self):
        """Hiding it on the variant and leaving it on the template would be
        the same as not hiding it."""
        template = self.product.product_tmpl_id
        with self.assertRaises(AccessError):
            template.with_user(self.clerk).read(['standard_price'])

    def test_it_is_gone_from_the_form(self):
        """A restricted field is taken out of the view, so nothing is left
        pointing at a field the user may not read."""
        view = self.env['product.template'].with_user(self.clerk) \
            .get_view(view_type='form') if hasattr(
                self.env['product.template'], 'get_view') else \
            self.env['product.template'].with_user(self.clerk) \
                .fields_view_get(view_type='form')
        self.assertNotIn('name="standard_price"', view['arch'])

    def test_it_is_still_in_the_form_for_the_group(self):
        model = self.env['product.template'].with_user(self.buyer)
        view = model.get_view(view_type='form') if hasattr(model, 'get_view') \
            else model.fields_view_get(view_type='form')
        self.assertIn('name="standard_price"', view['arch'])

    # -- what still works --------------------------------------------------

    def test_everything_else_about_a_product_still_reads(self):
        product = self.product.with_user(self.clerk)
        [values] = product.read(['name', 'list_price', 'default_code'])
        self.assertEqual(values['list_price'], 100.0)

    def test_a_product_can_still_be_duplicated(self):
        """Duplicate reads every field the user can see; it must not trip
        over the one they cannot. The template is what the button copies."""
        copy = self.product.product_tmpl_id.with_user(self.clerk).copy()
        self.assertTrue(copy.exists())
        self.assertNotEqual(copy, self.product.product_tmpl_id)

    def test_a_product_can_still_be_created(self):
        """Creating one without naming a cost must not need to read one."""
        product = self.env['product.product'].with_user(self.clerk).create({
            'name': 'Another Widget', 'list_price': 5.0})
        self.assertTrue(product.exists())

    def test_the_sales_price_is_left_alone(self):
        """Hiding what people need to do their job is not the point."""
        [values] = self.product.with_user(self.clerk).read(['list_price'])
        self.assertEqual(values['list_price'], 100.0)

    def test_a_search_on_products_still_works(self):
        found = self.env['product.product'].with_user(self.clerk).search(
            [('name', '=', 'Watched Widget')])
        self.assertEqual(found, self.product)

