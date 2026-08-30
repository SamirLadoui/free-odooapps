# -*- coding: utf-8 -*-
import json
from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestRestful(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        groups_field = ('group_ids' if 'group_ids' in cls.env['res.users']._fields
                        else 'groups_id')
        # group_partner_manager as well as group_user: a plain internal user
        # cannot create contacts on a bare database, and this fixture is about
        # exercising the API, not Odoo's partner ACL.
        cls.api_user = cls.env['res.users'].create({
            'name': 'API User', 'login': 'sl_restful_api_user',
            groups_field: [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('base.group_partner_manager').id,
            ])],
        })
        cls.key_record = cls.env['sl.api.key'].create({
            'name': 'Test Key', 'user_id': cls.api_user.id})
        cls.raw_key = cls._mint(cls, cls.key_record)
        cls.partner = cls.env['res.partner'].create({'name': 'Rest Partner'})

    def _mint(self, key_record):
        """Generate a key and capture the secret the UI would show once."""
        key_record.action_generate()
        return key_record.key_preview

    def _call(self, method, path, key=None, body=None, headers=None):
        url = self.base_url() + path
        head = {'Content-Type': 'application/json'}
        if key is not False:
            head['X-Api-Key'] = key or self.raw_key
        head.update(headers or {})
        return self.opener.request(
            method, url, headers=head,
            data=json.dumps(body) if body is not None else None)

    # -- the key itself ----------------------------------------------------

    def test_key_is_stored_hashed_not_in_the_clear(self):
        self.assertTrue(self.key_record.key_hash)
        self.assertNotIn(self.raw_key, self.key_record.key_hash)
        self.assertEqual(self.key_record.key_prefix, self.raw_key[:8])

    def test_key_resolves_from_its_secret(self):
        found = self.env['sl.api.key']._resolve(self.raw_key)
        self.assertEqual(found, self.key_record)

    def test_wrong_secret_resolves_to_nothing(self):
        self.assertFalse(self.env['sl.api.key']._resolve('not-a-real-key-at-all'))
        self.assertFalse(self.env['sl.api.key']._resolve(''))

    def test_a_shared_prefix_does_not_confuse_resolution(self):
        """Lookup is by prefix but the decision is the hash."""
        other = self.env['sl.api.key'].create({
            'name': 'Other', 'user_id': self.api_user.id})
        self._mint(other)
        other.write({'key_prefix': self.key_record.key_prefix})
        self.assertEqual(self.env['sl.api.key']._resolve(self.raw_key), self.key_record)

    def test_regenerating_invalidates_the_old_secret(self):
        old = self.raw_key
        new = self._mint(self.key_record)
        self.assertNotEqual(old, new)
        self.assertFalse(self.env['sl.api.key']._resolve(old))
        self.assertEqual(self.env['sl.api.key']._resolve(new), self.key_record)

    def test_expired_key_is_not_usable(self):
        """Set through SQL: the constraint rightly refuses a past date on entry,
        but a key created last year and left alone still has to expire."""
        self.env.cr.execute(
            "UPDATE sl_api_key SET expires_on = %s WHERE id = %s",
            (date.today() - timedelta(days=1), self.key_record.id))
        self.key_record.invalidate_recordset(['expires_on'])
        self.assertFalse(self.key_record._is_usable())

    def test_expired_key_is_rejected_over_http(self):
        self.env.cr.execute(
            "UPDATE sl_api_key SET expires_on = %s WHERE id = %s",
            (date.today() - timedelta(days=1), self.key_record.id))
        self.key_record.invalidate_recordset(['expires_on'])
        self.env.cr.flush()
        self.assertEqual(self._call('GET', '/api/v1/res.partner').status_code, 401)

    def test_expiry_in_the_past_is_refused_on_entry(self):
        with self.assertRaises(ValidationError):
            self.env['sl.api.key'].create({
                'name': 'Stale', 'user_id': self.api_user.id,
                'expires_on': date.today() - timedelta(days=1)})

    def test_revoked_key_is_not_usable(self):
        self.key_record.action_revoke()
        self.assertFalse(self.key_record._is_usable())

    # -- model restriction --------------------------------------------------

    def test_empty_model_list_allows_anything(self):
        self.assertTrue(self.key_record._may_touch('res.partner'))
        self.assertTrue(self.key_record._may_touch('res.users'))

    def test_naming_models_narrows_the_key(self):
        self.key_record.allowed_model_ids = [
            (6, 0, self.env['ir.model']._get('res.partner').ids)]
        self.assertTrue(self.key_record._may_touch('res.partner'))
        self.assertFalse(self.key_record._may_touch('res.users'))

    # -- authentication over HTTP ------------------------------------------

    def test_missing_key_is_rejected(self):
        response = self._call('GET', '/api/v1/res.partner', key=False)
        self.assertEqual(response.status_code, 401)

    def test_bad_key_is_rejected(self):
        response = self._call('GET', '/api/v1/res.partner', key='nonsense-key-value')
        self.assertEqual(response.status_code, 401)

    def test_revoked_key_is_rejected_over_http(self):
        self.key_record.action_revoke()
        self.env.cr.flush()
        self.assertEqual(self._call('GET', '/api/v1/res.partner').status_code, 401)

    def test_unknown_model_is_a_404(self):
        self.assertEqual(self._call('GET', '/api/v1/no.such.model').status_code, 404)

    def test_restricted_model_is_a_403(self):
        self.key_record.allowed_model_ids = [
            (6, 0, self.env['ir.model']._get('res.partner').ids)]
        self.env.cr.flush()
        self.assertEqual(self._call('GET', '/api/v1/res.country').status_code, 403)

    # -- reading -----------------------------------------------------------

    def test_list_returns_results_and_a_count(self):
        response = self._call('GET', '/api/v1/res.partner?limit=5&fields=name')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('count', payload)
        self.assertIn('results', payload)
        self.assertLessEqual(len(payload['results']), 5)

    def test_limit_is_capped(self):
        response = self._call('GET', '/api/v1/res.partner?limit=999999&fields=id')
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.json()['results']), 1000)

    def test_domain_is_applied(self):
        domain = json.dumps([['name', '=', 'Rest Partner']])
        response = self._call('GET', '/api/v1/res.partner?domain=%s&fields=name' % domain)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(payload['results'][0]['name'], 'Rest Partner')

    def test_malformed_domain_is_a_400(self):
        response = self._call('GET', '/api/v1/res.partner?domain=not-json')
        self.assertEqual(response.status_code, 400)

    def test_read_one_record(self):
        response = self._call('GET', '/api/v1/res.partner/%d?fields=name' % self.partner.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['name'], 'Rest Partner')

    def test_read_missing_record_is_a_404(self):
        self.assertEqual(
            self._call('GET', '/api/v1/res.partner/999999999').status_code, 404)

    # -- writing -----------------------------------------------------------

    def test_create_returns_the_new_id(self):
        response = self._call('POST', '/api/v1/res.partner',
                              body={'name': 'Created By API'})
        self.assertEqual(response.status_code, 201)
        new_id = response.json()['id']
        self.assertEqual(
            self.env['res.partner'].browse(new_id).name, 'Created By API')

    def test_create_with_a_bad_field_is_a_400(self):
        response = self._call('POST', '/api/v1/res.partner',
                              body={'no_such_field': 'x'})
        self.assertEqual(response.status_code, 400)

    def test_malformed_body_is_a_400(self):
        url = self.base_url() + '/api/v1/res.partner'
        response = self.opener.request(
            'POST', url, headers={'X-Api-Key': self.raw_key,
                                  'Content-Type': 'application/json'},
            data='{not json')
        self.assertEqual(response.status_code, 400)

    def test_update_a_record(self):
        response = self._call('PUT', '/api/v1/res.partner/%d' % self.partner.id,
                              body={'function': 'Buyer'})
        self.assertEqual(response.status_code, 200)
        self.partner.invalidate_recordset(['function'])
        self.assertEqual(self.partner.function, 'Buyer')

    def test_update_missing_record_is_a_404(self):
        response = self._call('PUT', '/api/v1/res.partner/999999999',
                              body={'function': 'x'})
        self.assertEqual(response.status_code, 404)

    def test_delete_a_record(self):
        victim = self.env['res.partner'].create({'name': 'Doomed By API'})
        self.env.cr.flush()
        response = self._call('DELETE', '/api/v1/res.partner/%d' % victim.id)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(victim.exists())

    def test_delete_missing_record_is_a_404(self):
        self.assertEqual(
            self._call('DELETE', '/api/v1/res.partner/999999999').status_code, 404)

    # -- the key's own limits are the user's -------------------------------

    def test_requests_cannot_exceed_the_user_rights(self):
        """A key never grants more than the user it acts as already has.

        The API user can manage contacts but is not an administrator, so
        creating a user has to be refused however valid the key is.
        """
        response = self._call('POST', '/api/v1/res.users',
                              body={'name': 'Sneaky', 'login': 'sneaky_api_user'})
        self.assertIn(response.status_code, (400, 403),
                      "a non-administrator must not be able to create users")

    def test_use_is_recorded(self):
        before = self.key_record.use_count
        self._call('GET', '/api/v1/res.partner?limit=1')
        self.key_record.invalidate_recordset(['use_count', 'last_used'])
        self.assertGreater(self.key_record.use_count, before)
        self.assertTrue(self.key_record.last_used)
