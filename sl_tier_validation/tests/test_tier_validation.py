# -*- coding: utf-8 -*-
"""Held until everyone agrees, and only then.

Tested against res.partner rather than a model of the module's own, because
the whole claim is that it works on a model nobody wrote it for.
"""
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTierValidation(TransactionCase):

    def setUp(self):
        super().setUp()
        self.model = self.env['ir.model']._get('res.partner')
        groups_field = ('group_ids' if 'group_ids' in self.env['res.users']._fields
                        else 'groups_id')
        self.manager = self.env['res.users'].create({
            'name': 'Approving Manager', 'login': 'sl_tier_manager',
            groups_field: [(6, 0, [self.env.ref('base.group_user').id])],
        })
        self.director = self.env['res.users'].create({
            'name': 'Approving Director', 'login': 'sl_tier_director',
            groups_field: [(6, 0, [self.env.ref('base.group_user').id])],
        })
        self.outsider = self.env['res.users'].create({
            'name': 'Somebody Else', 'login': 'sl_tier_outsider',
            groups_field: [(6, 0, [self.env.ref('base.group_user').id])],
        })
        self.partner = self.env['res.partner'].create(
            {'name': 'Held Company', 'ref': 'HOLD'})

    def _tier(self, **values):
        return self.env['sl.tier.definition'].create(dict({
            'name': 'Manager agrees',
            'model_id': self.model.id,
            'trigger_field': 'ref',
            'trigger_value': 'APPROVED',
            'reviewer_ids': [(6, 0, self.manager.ids)],
        }, **values))

    # -- the hold ----------------------------------------------------------

    def test_the_change_is_refused_until_it_is_asked_for(self):
        self._tier()
        with self.assertRaises(UserError):
            self.partner.ref = 'APPROVED'

    def test_a_change_to_anything_else_is_left_alone(self):
        """Only the value named on the tier is held. Everything else about the
        record carries on working, or the module is unusable."""
        self._tier()
        self.partner.ref = 'SOMETHING ELSE'
        self.assertEqual(self.partner.ref, 'SOMETHING ELSE')
        self.partner.name = 'Renamed Freely'
        self.assertEqual(self.partner.name, 'Renamed Freely')

    def test_a_model_with_no_tier_is_untouched(self):
        self._tier()
        user = self.env['res.users'].create({
            'name': 'Unaffected', 'login': 'sl_tier_unaffected'})
        user.name = 'Renamed'
        self.assertEqual(user.name, 'Renamed')

    def test_waiting_names_who_it_waits_on(self):
        self._tier()
        self.partner.sl_request_validation('ref', 'APPROVED')
        with self.assertRaises(UserError) as caught:
            self.partner.ref = 'APPROVED'
        self.assertIn('Manager agrees', str(caught.exception))

    def test_once_approved_the_change_goes_through(self):
        self._tier()
        reviews = self.partner.sl_request_validation('ref', 'APPROVED')
        reviews.with_user(self.manager).action_approve()
        self.partner.ref = 'APPROVED'
        self.assertEqual(self.partner.ref, 'APPROVED')

    # -- tiers in order ----------------------------------------------------

    def test_every_tier_has_to_agree(self):
        """One approval out of two is not approval."""
        first = self._tier(name='Manager agrees', sequence=10)
        second = self._tier(name='Director agrees', sequence=20,
                            reviewer_ids=[(6, 0, self.director.ids)])
        reviews = self.partner.sl_request_validation('ref', 'APPROVED')
        self.assertEqual(len(reviews), 2)
        reviews.filtered(lambda r: r.definition_id == first).with_user(
            self.manager).action_approve()
        with self.assertRaises(UserError):
            self.partner.ref = 'APPROVED'
        reviews.filtered(lambda r: r.definition_id == second).with_user(
            self.director).action_approve()
        self.partner.ref = 'APPROVED'
        self.assertEqual(self.partner.ref, 'APPROVED')

    def test_the_tiers_come_back_in_their_order(self):
        self._tier(name='Second', sequence=20)
        self._tier(name='First', sequence=10)
        reviews = self.partner.sl_request_validation('ref', 'APPROVED')
        self.assertEqual(reviews.sorted('sequence').mapped('name'),
                         ['First', 'Second'])

    # -- only when it matters ---------------------------------------------

    def test_a_condition_keeps_it_off_the_records_it_does_not_apply_to(self):
        """The usual reason anybody wants this: the large orders, not all."""
        self._tier(domain="[('name', 'like', 'Large')]")
        self.partner.ref = 'APPROVED'
        self.assertEqual(self.partner.ref, 'APPROVED')

    def test_a_condition_still_holds_the_records_it_does_apply_to(self):
        self._tier(domain="[('name', 'like', 'Held')]")
        with self.assertRaises(UserError):
            self.partner.ref = 'APPROVED'

    # -- rejection ---------------------------------------------------------

    def test_a_rejection_needs_a_reason(self):
        """A refusal with no reason sends the document back with nothing to
        act on."""
        self._tier()
        reviews = self.partner.sl_request_validation('ref', 'APPROVED')
        with self.assertRaises(UserError):
            reviews.with_user(self.manager).action_reject()

    def test_a_rejection_blocks_and_says_why(self):
        self._tier()
        reviews = self.partner.sl_request_validation('ref', 'APPROVED')
        reviews.comment = 'The reference belongs to another company.'
        reviews.with_user(self.manager).action_reject()
        with self.assertRaises(UserError) as caught:
            self.partner.ref = 'APPROVED'
        self.assertIn('another company', str(caught.exception))

    # -- who may answer ----------------------------------------------------

    def test_somebody_who_is_not_a_reviewer_cannot_approve(self):
        self._tier()
        reviews = self.partner.sl_request_validation('ref', 'APPROVED')
        with self.assertRaises(UserError):
            reviews.with_user(self.outsider).action_approve()

    def test_anybody_in_the_reviewing_group_may_approve(self):
        group = self.env['res.groups'].create({'name': 'Approvers'})
        field = 'user_ids' if 'user_ids' in group._fields else 'users'
        group.write({field: [(4, self.director.id)]})
        self._tier(reviewer_ids=[(6, 0, [])], reviewer_group_id=group.id)
        reviews = self.partner.sl_request_validation('ref', 'APPROVED')
        reviews.with_user(self.director).action_approve()
        self.partner.ref = 'APPROVED'
        self.assertEqual(self.partner.ref, 'APPROVED')

    def test_answering_twice_is_refused(self):
        self._tier()
        reviews = self.partner.sl_request_validation('ref', 'APPROVED')
        reviews.with_user(self.manager).action_approve()
        with self.assertRaises(UserError):
            reviews.with_user(self.manager).action_approve()

    # -- asking again ------------------------------------------------------

    def test_asking_twice_at_once_is_refused(self):
        self._tier()
        self.partner.sl_request_validation('ref', 'APPROVED')
        with self.assertRaises(UserError):
            self.partner.sl_request_validation('ref', 'APPROVED')

    def test_the_earlier_round_is_kept(self):
        """A document that went round twice should show that it did."""
        self._tier()
        first = self.partner.sl_request_validation('ref', 'APPROVED')
        first.comment = 'Not yet.'
        first.with_user(self.manager).action_reject()
        second = self.partner.sl_request_validation('ref', 'APPROVED')
        self.assertEqual(second.round, 2)
        self.assertEqual(len(self.partner.sl_reviews()), 2)
        self.assertTrue(first.exists())

    def test_asking_for_something_nobody_reviews_is_refused(self):
        self._tier()
        with self.assertRaises(UserError):
            self.partner.sl_request_validation('ref', 'NOT A WATCHED VALUE')

    # -- the definitions refuse nonsense ----------------------------------

    def test_a_tier_with_nobody_to_review_it_is_refused(self):
        """It could never be approved, so it would stop the record for good."""
        with self.assertRaises(ValidationError):
            self.env['sl.tier.definition'].create({
                'name': 'Nobody', 'model_id': self.model.id,
                'trigger_field': 'ref', 'trigger_value': 'X'})

    def test_a_field_that_does_not_exist_is_refused(self):
        with self.assertRaises(ValidationError):
            self._tier(trigger_field='not_a_field')

    def test_a_broken_condition_is_refused(self):
        with self.assertRaises(ValidationError):
            self._tier(domain="[('nope_not_a_field', '=', 1)]")
