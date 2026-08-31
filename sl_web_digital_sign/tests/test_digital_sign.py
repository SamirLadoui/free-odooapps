# -*- coding: utf-8 -*-
import base64

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

PIXEL = base64.b64encode(base64.b64decode(
    b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='))


@tagged('post_install', '-at_install')
class TestDigitalSign(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.config = cls.env['sl.signature.config'].create({
            'model_id': cls.partner_model.id,
            'note': 'Delivery accepted',
        })
        cls.partners = cls.env['res.partner'].create([
            {'name': 'Signer One'}, {'name': 'Signer Two'}])

    def _wizard(self, records=None, **values):
        records = self.partners if records is None else records
        return self.env['sl.signature.wizard'].with_context(
            active_ids=records.ids, active_model='res.partner',
        ).create(dict({
            'config_id': self.config.id,
            'signer_name': 'Jane Doe',
            'signer_email': 'jane@example.com',
            'signature': PIXEL,
        }, **values))

    # -- configuration -----------------------------------------------------

    def test_action_is_created_and_bound(self):
        self.assertTrue(self.config.action_id)
        self.assertEqual(self.config.action_id.binding_model_id, self.partner_model)
        self.assertEqual(self.config.action_id.name, 'Sign this record')

    def test_label_change_renames_the_action(self):
        self.config.label = 'Accept delivery'
        self.assertEqual(self.config.action_id.name, 'Accept delivery')

    def test_archiving_removes_the_action(self):
        action = self.config.action_id
        self.config.active = False
        self.assertFalse(action.exists())

    def test_a_model_can_only_be_configured_once(self):
        with self.assertRaises(ValidationError):
            self.env['sl.signature.config'].create({'model_id': self.partner_model.id})

    def test_unlink_removes_the_action(self):
        config = self.env['sl.signature.config'].create({
            'model_id': self.env['ir.model']._get('res.users').id})
        action = config.action_id
        config.unlink()
        self.assertFalse(action.exists())

    # -- signing -----------------------------------------------------------

    def test_signing_creates_one_signature_per_record(self):
        self._wizard().action_sign()
        signatures = self.env['sl.signature'].search([
            ('res_model', '=', 'res.partner'),
            ('res_id', 'in', self.partners.ids)])
        self.assertEqual(len(signatures), 2)
        self.assertEqual(set(signatures.mapped('signer_name')), {'Jane Doe'})
        self.assertTrue(all(signatures.mapped('signature')))

    def test_signature_records_who_and_when(self):
        self._wizard(records=self.partners[0]).action_sign()
        signature = self.env['sl.signature'].search([
            ('res_id', '=', self.partners[0].id),
            ('res_model', '=', 'res.partner')], limit=1)
        self.assertTrue(signature.signed_on)
        self.assertEqual(signature.captured_by_id, self.env.user)
        self.assertEqual(signature.signer_email, 'jane@example.com')

    def test_record_name_is_resolved(self):
        self._wizard(records=self.partners[0]).action_sign()
        signature = self.env['sl.signature'].search([
            ('res_id', '=', self.partners[0].id),
            ('res_model', '=', 'res.partner')], limit=1)
        self.assertEqual(signature.record_name, self.partners[0].display_name)

    def test_deleted_record_does_not_break_the_log(self):
        """The audit trail must outlive the record it refers to."""
        victim = self.env['res.partner'].create({'name': 'Temporary'})
        self._wizard(records=victim).action_sign()
        signature = self.env['sl.signature'].search([
            ('res_id', '=', victim.id), ('res_model', '=', 'res.partner')], limit=1)
        victim.unlink()
        signature.invalidate_cache(['record_name'])
        signature._compute_record_name()
        self.assertEqual(signature.record_name, '(deleted)')
        with self.assertRaises(ValidationError):
            signature.action_open_record()

    def test_a_copy_is_attached_to_the_record(self):
        self._wizard(records=self.partners[0]).action_sign()
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'res.partner'), ('res_id', '=', self.partners[0].id)])
        self.assertTrue(any(a.name.startswith('signature-') for a in attachments))

    def test_chatter_records_the_signature(self):
        partner = self.partners[0]
        before = len(partner.message_ids)
        self._wizard(records=partner).action_sign()
        self.assertGreater(len(partner.message_ids), before)
        self.assertIn('Jane Doe', partner.message_ids[0].body)

    def test_signing_needs_a_selection(self):
        wizard = self.env['sl.signature.wizard'].with_context(
            active_ids=[], active_model='res.partner',
        ).create({
            'config_id': self.config.id,
            'signer_name': 'Nobody',
            'signature': PIXEL,
        })
        with self.assertRaises(UserError):
            wizard.action_sign()

    def test_bad_email_is_refused(self):
        with self.assertRaises(ValidationError):
            self.env['sl.signature'].create({
                'signer_name': 'Bad', 'signature': PIXEL,
                'signer_email': 'not-an-email',
                'res_model': 'res.partner', 'res_id': self.partners[0].id,
            })

    def test_unknown_model_is_refused(self):
        with self.assertRaises(ValidationError):
            self.env['sl.signature'].create({
                'signer_name': 'Bad', 'signature': PIXEL,
                'res_model': 'no.such.model', 'res_id': 1,
            })

    def test_signing_requires_write_access(self):
        """A user who can read but not edit the record must not be able to sign it.

        res.company is readable by every internal user and writable only by
        administrators, which is exactly the shape this guard exists for.
        """
        groups_field = ('group_ids' if 'group_ids' in self.env['res.users']._fields
                        else 'groups_id')
        member = self.env['res.users'].create({
            'name': 'Plain Employee', 'login': 'sign_employee_test',
            groups_field: [(6, 0, [self.env.ref('base.group_user').id])],
        })
        company_config = self.env['sl.signature.config'].create({
            'model_id': self.env['ir.model']._get('res.company').id})
        company = self.env.company

        self.assertTrue(company.with_user(member).read(['name']), "should be readable")

        wizard = self.env['sl.signature.wizard'].with_user(member).with_context(
            active_ids=company.ids, active_model='res.company',
        ).create({
            'config_id': company_config.id,
            'signer_name': 'Plain Employee',
            'signature': PIXEL,
        })
        with self.assertRaises(UserError):
            wizard.action_sign()

        self.assertFalse(
            self.env['sl.signature'].search([('res_model', '=', 'res.company'),
                                             ('res_id', '=', company.id)]),
            "a refused signing must not leave a signature behind")
