# -*- coding: utf-8 -*-
import json
from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, tagged

import odoo.release

# Odoo 14 and 15 route any request with Content-Type: application/json to the
# JSON-RPC dispatcher before it reaches a type='http' route, which answers 400.
# The body is still JSON either way - the controller parses it itself - so on
# those versions the header is the only thing that changes.
JSON_CONTENT_TYPE = ('application/json'
                     if odoo.release.version_info[0] >= 16 else 'text/plain')


@tagged('post_install', '-at_install')
class TestRestful(HttpCase):

    def setUp(self):
        # Instance level rather than setUpClass: 14.0 has no class-level env.
        super().setUp()
        groups_field = ('group_ids' if 'group_ids' in self.env['res.users']._fields
                        else 'groups_id')
        # group_partner_manager as well as group_user: a plain internal user
        # cannot create contacts on a bare database, and this fixture is about
        # exercising the API, not Odoo's partner ACL.
        self.api_user = self.env['res.users'].create({
            'name': 'API User', 'login': 'sl_restful_api_user',
            groups_field: [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('base.group_partner_manager').id,
            ])],
        })
        self.key_record = self.env['sl.api.key'].create({
            'name': 'Test Key', 'user_id': self.api_user.id})
        self.raw_key = self._mint(self.key_record)
        self.partner = self.env['res.partner'].create({'name': 'Rest Partner'})

    def _mint(self, key_record):
        """Generate a key and capture the secret the UI would show once.

        key_preview is a non-stored field with no compute, and 14.0 drops the
        assigned value rather than keeping it in cache, so fall back to the
        notification the action returns - it carries the same key.
        """
        action = key_record.action_generate()
        if key_record.key_preview:
            return key_record.key_preview
        return action['params']['message'].rsplit(': ', 1)[-1]

    def _base_url(self):
        """HttpCase grew base_url() in 15.0; on 14 it is built by hand."""
        if hasattr(self, 'base_url'):
            return self.base_url()
        import odoo
        from odoo.tests.common import HOST
        return 'http://%s:%s' % (HOST, odoo.tools.config['http_port'])

    def _flush(self):
        """Odoo moved flushing three times: Model.flush() on 14,
        cr.flush() on 15-16, env.flush_all() on 17+."""
        if hasattr(self.env, 'flush_all'):
            self.env.flush_all()
        elif hasattr(self.env.cr, 'flush'):
            self.env.cr.flush()
        else:
            self.env['base'].flush()

    def _invalidate(self, records, fields):
        """invalidate_recordset arrived in 17.0; before that it was
        invalidate_cache on the recordset."""
        if hasattr(records, 'invalidate_recordset'):
            records.invalidate_recordset(fields)
        else:
            records.invalidate_cache(fields)

    def _call(self, method, path, key=None, body=None, headers=None):
        # Going through the session directly (PUT and DELETE need it) bypasses
        # url_open, which is where Odoo flushes before a request. Without this
        # the worker reads the database while the fixture is still in cache.
        self._flush()
        url = self._base_url() + path
        head = {'Content-Type': JSON_CONTENT_TYPE}
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
        self._invalidate(self.key_record, ['expires_on'])
        self.assertFalse(self.key_record._is_usable())

    def test_expired_key_is_rejected_over_http(self):
        self.env.cr.execute(
            "UPDATE sl_api_key SET expires_on = %s WHERE id = %s",
            (date.today() - timedelta(days=1), self.key_record.id))
        self._invalidate(self.key_record, ['expires_on'])
        self._flush()
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
        self._flush()
        self.assertEqual(self._call('GET', '/api/v1/res.partner').status_code, 401)

    def test_unknown_model_is_a_404(self):
        self.assertEqual(self._call('GET', '/api/v1/no.such.model').status_code, 404)

    def test_restricted_model_is_a_403(self):
        self.key_record.allowed_model_ids = [
            (6, 0, self.env['ir.model']._get('res.partner').ids)]
        self._flush()
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
        self._flush()  # this one bypasses _call, so it flushes for itself
        url = self._base_url() + '/api/v1/res.partner'
        response = self.opener.request(
            'POST', url, headers={'X-Api-Key': self.raw_key,
                                  'Content-Type': JSON_CONTENT_TYPE},
            data='{not json')
        self.assertEqual(response.status_code, 400)

    def test_update_a_record(self):
        response = self._call('PUT', '/api/v1/res.partner/%d' % self.partner.id,
                              body={'function': 'Buyer'})
        self.assertEqual(response.status_code, 200)
        self._invalidate(self.partner, ['function'])
        self.assertEqual(self.partner.function, 'Buyer')

    def test_update_missing_record_is_a_404(self):
        response = self._call('PUT', '/api/v1/res.partner/999999999',
                              body={'function': 'x'})
        self.assertEqual(response.status_code, 404)

    def test_delete_a_record(self):
        victim = self.env['res.partner'].create({'name': 'Doomed By API'})
        self._flush()
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
        self._invalidate(self.key_record, ['use_count', 'last_used'])
        self.assertGreater(self.key_record.use_count, before)
        self.assertTrue(self.key_record.last_used)
