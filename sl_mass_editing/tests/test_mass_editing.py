# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMassEditing(TransactionCase):

    def field(self, name, model='res.partner'):
        """An ir.model.fields record, by name.

        A plain method rather than a closure stashed on the class: assigning a
        function to a class attribute binds it as a method on access, and
        wrapping it in staticmethod() only became callable in python 3.10 -
        which 14.0, on 3.8, is not.
        """
        return self.env['ir.model.fields']._get(model, name)

    def setUp(self):
        # Instance level so the field helper is an ordinary method, which
        # works the same on every version.
        super().setUp()
        self.partner_model = self.env['ir.model']._get('res.partner')


        self.config = self.env['sl.mass.editing'].create({
            'name': 'Partner bulk edit',
            'model_id': self.partner_model.id,
            'field_ids': [(6, 0, [
                self.field('comment').id, self.field('function').id, self.field('city').id,
                self.field('category_id').id, self.field('user_id').id,
                self.field('active').id, self.field('type').id,
            ])],
        })
        self.partners = self.env['res.partner'].create([
            {'name': 'Bulk One', 'city': 'Algiers'},
            {'name': 'Bulk Two', 'city': 'Oran'},
        ])
        self.tag_a = self.env['res.partner.category'].create({'name': 'Tag A'})
        self.tag_b = self.env['res.partner.category'].create({'name': 'Tag B'})

    def _wizard(self, lines):
        return self.env['sl.mass.editing.wizard'].with_context(
            active_ids=self.partners.ids, active_model='res.partner',
        ).create({
            'mass_edit_id': self.config.id,
            'line_ids': [(0, 0, values) for values in lines],
        })

    # -- the Action-menu entry ---------------------------------------------

    def test_action_is_created_and_bound(self):
        self.assertTrue(self.config.action_id)
        self.assertEqual(self.config.action_id.binding_model_id, self.partner_model)
        self.assertEqual(self.config.action_id.name, 'Partner bulk edit')

    def test_action_follows_a_rename(self):
        self.config.name = 'Renamed'
        self.assertEqual(self.config.action_id.name, 'Renamed')

    def test_archiving_removes_the_action(self):
        action = self.config.action_id
        self.config.active = False
        self.assertFalse(action.exists(), "an archived bulk edit must leave the Action menu")

    def test_unlink_removes_the_action(self):
        config = self.env['sl.mass.editing'].create({
            'name': 'Temporary', 'model_id': self.partner_model.id,
            'field_ids': [(6, 0, [self.field('city').id])],
        })
        action = config.action_id
        config.unlink()
        self.assertFalse(action.exists())

    # -- configuration guards ----------------------------------------------

    def test_fields_must_belong_to_the_model(self):
        with self.assertRaises(ValidationError):
            self.env['sl.mass.editing'].create({
                'name': 'Wrong model', 'model_id': self.partner_model.id,
                'field_ids': [(6, 0, [self.field('login', 'res.users').id])],
            })

    def test_odoo_maintained_fields_are_refused(self):
        with self.assertRaises(ValidationError):
            self.env['sl.mass.editing'].create({
                'name': 'Audit fields', 'model_id': self.partner_model.id,
                'field_ids': [(6, 0, [self.field('create_date').id])],
            })

    # -- writing values ----------------------------------------------------

    def test_set_char_and_text(self):
        self._wizard([
            {'field_id': self.field('function').id, 'operation': 'set',
             'value_char': 'Buyer'},
            {'field_id': self.field('comment').id, 'operation': 'set',
             'value_text': 'Reviewed in bulk'},
        ]).action_apply()
        self.assertEqual(set(self.partners.mapped('function')), {'Buyer'})
        for partner in self.partners:
            self.assertIn('Reviewed in bulk', partner.comment or '')

    def test_clear_sets_false(self):
        self.partners.write({'city': 'Somewhere'})
        self._wizard([
            {'field_id': self.field('city').id, 'operation': 'clear'},
        ]).action_apply()
        self.assertEqual(self.partners.mapped('city'), [False, False])

    def test_set_boolean(self):
        self._wizard([
            {'field_id': self.field('active').id, 'operation': 'set',
             'value_boolean': 'false'},
        ]).action_apply()
        self.assertFalse(any(self.partners.mapped('active')))

    def test_set_selection_value(self):
        self._wizard([
            {'field_id': self.field('type').id, 'operation': 'set',
             'value_selection': 'invoice'},
        ]).action_apply()
        self.assertEqual(set(self.partners.mapped('type')), {'invoice'})

    def test_invalid_selection_key_is_refused(self):
        with self.assertRaises(ValidationError):
            self._wizard([
                {'field_id': self.field('type').id, 'operation': 'set',
                 'value_selection': 'not_a_real_option'},
            ])

    def test_set_many2one_by_reference(self):
        user = self.env.ref('base.user_admin')
        self._wizard([
            {'field_id': self.field('user_id').id, 'operation': 'set',
             'value_reference': 'res.users,%d' % user.id},
        ]).action_apply()
        self.assertEqual(set(self.partners.mapped('user_id')), {user})

    def test_wrong_model_reference_is_refused(self):
        wizard = self._wizard([
            {'field_id': self.field('user_id').id, 'operation': 'set',
             'value_reference': 'res.partner.category,%d' % self.tag_a.id},
        ])
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_append_and_remove_tags(self):
        self.partners.write({'category_id': [(6, 0, self.tag_a.ids)]})
        self._wizard([
            {'field_id': self.field('category_id').id, 'operation': 'append',
             'value_reference': 'res.partner.category,%d' % self.tag_b.id},
        ]).action_apply()
        for partner in self.partners:
            self.assertEqual(partner.category_id, self.tag_a | self.tag_b)

        self._wizard([
            {'field_id': self.field('category_id').id, 'operation': 'remove',
             'value_reference': 'res.partner.category,%d' % self.tag_a.id},
        ]).action_apply()
        for partner in self.partners:
            self.assertEqual(partner.category_id, self.tag_b)

    def test_several_lines_on_one_m2m_stack(self):
        """Two Add lines on the same field must both land, not overwrite."""
        self._wizard([
            {'field_id': self.field('category_id').id, 'operation': 'append',
             'value_reference': 'res.partner.category,%d' % self.tag_a.id},
            {'field_id': self.field('category_id').id, 'operation': 'append',
             'value_reference': 'res.partner.category,%d' % self.tag_b.id},
        ]).action_apply()
        for partner in self.partners:
            self.assertEqual(partner.category_id, self.tag_a | self.tag_b)

    def test_operation_must_suit_the_field(self):
        with self.assertRaises(ValidationError):
            self._wizard([
                {'field_id': self.field('city').id, 'operation': 'append',
                 'value_char': 'nope'},
            ])

    def test_field_outside_the_whitelist_is_refused(self):
        """The configuration is the boundary, whatever the client sends."""
        with self.assertRaises(ValidationError):
            self._wizard([
                {'field_id': self.field('vat').id, 'operation': 'set',
                 'value_char': 'X'},
            ])

    def test_apply_needs_a_selection(self):
        wizard = self.env['sl.mass.editing.wizard'].with_context(
            active_ids=[], active_model='res.partner',
        ).create({
            'mass_edit_id': self.config.id,
            'line_ids': [(0, 0, {'field_id': self.field('city').id,
                                 'operation': 'set', 'value_char': 'X'})],
        })
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_apply_needs_at_least_one_change(self):
        with self.assertRaises(UserError):
            self._wizard([]).action_apply()

    def test_record_count_reflects_the_selection(self):
        self.assertEqual(self._wizard([]).record_count, 2)
