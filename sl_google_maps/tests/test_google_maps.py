# -*- coding: utf-8 -*-
import json
from urllib.parse import parse_qs, quote_plus, urlparse

from odoo.exceptions import UserError, ValidationError
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestGoogleMaps(HttpCase):

    def setUp(self):
        # 14.0 has no class-level env: setUpClass cannot build fixtures.
        super().setUp()
        self.company = self.env.company
        self.company.google_maps_api_key = False
        self.country = self.env.ref('base.dz')
        self.partner = self.env['res.partner'].create({
            'name': 'Map Test',
            'street': '12 Rue Didouche Mourad',
            'city': 'Algiers',
            'zip': '16000',
            'country_id': self.country.id,
        })
        self.blank = self.env['res.partner'].create({'name': 'No Address'})

    # -- what gets handed to Google ----------------------------------------

    def test_address_is_used_when_there_are_no_coordinates(self):
        query = self.partner._map_query()
        self.assertIn('12 Rue Didouche Mourad', query)
        self.assertIn('Algiers', query)
        self.assertIn(self.country.name, query)

    def test_coordinates_win_over_the_address(self):
        """Two towns share a street name far more often than a latitude."""
        self.partner.write({'partner_latitude': 36.7538, 'partner_longitude': 3.0588})
        self.assertEqual(self.partner._map_query(), '36.7538000,3.0588000')

    def test_coordinates_do_not_leak_float_repr(self):
        """3.0588 reads back as 3.0587999999999997 on some versions."""
        self.partner.write({'partner_latitude': 36.7538, 'partner_longitude': 3.0588})
        self.assertNotIn('999999', self.partner._map_query())

    def test_partner_without_address_is_not_mappable(self):
        self.assertFalse(self.blank._map_query())
        self.assertFalse(self.blank.has_mappable_address)
        self.assertFalse(self.blank._map_search_url())

    # -- URLs --------------------------------------------------------------

    def test_search_url_needs_no_api_key(self):
        """The module has to be useful before anyone configures a key."""
        self.assertFalse(self.company.google_maps_api_key)
        url = self.partner._map_search_url()
        self.assertTrue(url.startswith('https://www.google.com/maps/search/'))
        self.assertIn(quote_plus('Algiers'), url)

    def test_directions_url(self):
        url = self.partner._map_directions_url()
        self.assertIn('/maps/dir/', url)
        self.assertIn('destination=', url)

    def test_no_embed_without_a_key(self):
        self.assertFalse(self.partner._map_embed_url())

    def test_embed_url_with_a_key(self):
        self.company.google_maps_api_key = 'TEST_KEY'
        url = self.partner._map_embed_url()
        self.assertIn('/maps/embed/v1/place', url)
        params = parse_qs(urlparse(url).query)
        self.assertEqual(params['key'], ['TEST_KEY'])
        self.assertEqual(params['zoom'], ['14'])

    def test_zoom_is_validated(self):
        for bad in (22, -3, 100):
            with self.assertRaises(ValidationError, msg='accepted zoom %s' % bad):
                self.company.google_maps_zoom = bad

    def test_zero_zoom_falls_back_to_the_default(self):
        self.company.google_maps_api_key = 'TEST_KEY'
        self.company.google_maps_zoom = 0
        self.assertIn('zoom=14', self.partner._map_embed_url())

    def test_api_key_is_url_encoded(self):
        """The key is user input that ends up inside a URL."""
        self.company.google_maps_api_key = 'key with spaces&x=1'
        url = self.partner._map_embed_url()
        self.assertNotIn(' ', url)
        self.assertEqual(parse_qs(urlparse(url).query)['key'], ['key with spaces&x=1'])

    # -- resolving Google's ISO codes --------------------------------------

    def test_country_code_resolves(self):
        result = self.env['res.partner'].sl_resolve_place_location('DZ')
        self.assertEqual(result['country_id'], self.country.id)

    def test_country_code_is_case_insensitive(self):
        self.assertEqual(
            self.env['res.partner'].sl_resolve_place_location('dz')['country_id'],
            self.country.id)

    def test_state_resolves_within_its_country(self):
        state = self.env['res.country.state'].search(
            [('country_id', '=', self.env.ref('base.us').id), ('code', '=', 'CA')], limit=1)
        if not state:
            self.skipTest('US states not loaded')
        result = self.env['res.partner'].sl_resolve_place_location('US', 'CA')
        self.assertEqual(result['state_id'], state.id)

    def test_unknown_codes_resolve_to_nothing(self):
        self.assertEqual(self.env['res.partner'].sl_resolve_place_location('ZZ'), {})
        self.assertEqual(self.env['res.partner'].sl_resolve_place_location(''), {})
        result = self.env['res.partner'].sl_resolve_place_location('DZ', 'NOPE')
        self.assertNotIn('state_id', result, "a bad state must not be guessed at")

    # -- markers -----------------------------------------------------------

    def test_markers_need_coordinates(self):
        """The browser map cannot place an address it has not geocoded."""
        self.assertEqual(self.env['res.partner']._map_markers(self.partner), [])
        self.partner.write({'partner_latitude': 36.75, 'partner_longitude': 3.05})
        markers = self.env['res.partner']._map_markers(self.partner)
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]['id'], self.partner.id)
        self.assertEqual(markers[0]['lat'], 36.75)

    def test_markers_are_json_serialisable(self):
        self.partner.write({'partner_latitude': 36.75, 'partner_longitude': 3.05})
        json.dumps(self.env['res.partner']._map_markers(self.partner))

    # -- static fallback ---------------------------------------------------

    def test_static_map_needs_a_key(self):
        self.assertFalse(self.env['res.partner']._static_map_url(self.partner))

    def test_static_map_lists_every_mappable_partner(self):
        self.company.google_maps_api_key = 'TEST_KEY'
        second = self.env['res.partner'].create({'name': 'Second', 'city': 'Oran'})
        url = self.env['res.partner']._static_map_url(self.partner | second)
        self.assertEqual(url.count('markers='), 2)

    def test_static_map_skips_partners_without_an_address(self):
        self.company.google_maps_api_key = 'TEST_KEY'
        url = self.env['res.partner']._static_map_url(self.partner | self.blank)
        self.assertEqual(url.count('markers='), 1)

    def test_static_map_is_capped(self):
        """The Static Maps URL has a length limit."""
        from odoo.addons.sl_google_maps.models.res_partner import MAX_STATIC_MARKERS
        self.company.google_maps_api_key = 'TEST_KEY'
        many = self.env['res.partner'].create([
            {'name': 'Bulk %d' % i, 'city': 'Algiers'}
            for i in range(MAX_STATIC_MARKERS + 5)])
        url = self.env['res.partner']._static_map_url(many)
        self.assertEqual(url.count('markers='), MAX_STATIC_MARKERS)

    # -- actions -----------------------------------------------------------

    def test_show_on_map_opens_google_without_a_key(self):
        action = self.partner.action_show_on_map()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertIn('google.com/maps/search', action['url'])

    def test_show_on_map_opens_the_embedded_page_with_a_key(self):
        self.company.google_maps_api_key = 'TEST_KEY'
        action = self.partner.action_show_on_map()
        self.assertEqual(action['url'], '/sl_google_maps/partner/%d' % self.partner.id)

    def test_show_on_map_refuses_an_addressless_partner(self):
        with self.assertRaises(UserError):
            self.blank.action_show_on_map()

    def test_selection_action_skips_addressless_records(self):
        action = (self.partner | self.blank).action_show_selection_on_map()
        self.assertIn('ids=%d' % self.partner.id, action['url'])
        self.assertNotIn(str(self.blank.id), action['url'].split('ids=')[1])

    def test_selection_action_needs_at_least_one_address(self):
        with self.assertRaises(UserError):
            self.blank.action_show_selection_on_map()

    # -- the key reaching the browser --------------------------------------

    def test_internal_users_get_the_key(self):
        self.company.google_maps_api_key = 'TEST_KEY'
        self.assertEqual(self.env['ir.http']._sl_google_maps_key(), 'TEST_KEY')

    def test_key_is_empty_when_unset(self):
        self.assertEqual(self.env['ir.http']._sl_google_maps_key(), '')

    def test_portal_users_never_get_the_key(self):
        """The key is public by design, but there is no reason to hand it out."""
        self.company.google_maps_api_key = 'TEST_KEY'
        groups_field = ('group_ids' if 'group_ids' in self.env['res.users']._fields
                        else 'groups_id')
        portal = self.env['res.users'].create({
            'name': 'Portal Maps', 'login': 'portal_maps_test',
            groups_field: [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        self.assertEqual(
            self.env['ir.http'].with_user(portal)._sl_google_maps_key(), '')

    # -- pages -------------------------------------------------------------

    def test_partner_page_renders(self):
        self.authenticate('admin', 'admin')
        self.env['base'].flush()
        response = self.url_open('/sl_google_maps/partner/%d' % self.partner.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Open in Google Maps', response.text)

    def test_partner_page_explains_a_missing_key(self):
        self.authenticate('admin', 'admin')
        self.env['base'].flush()
        response = self.url_open('/sl_google_maps/partner/%d' % self.partner.id)
        self.assertIn('No API key configured', response.text)

    def test_partners_page_renders(self):
        self.authenticate('admin', 'admin')
        self.env['base'].flush()
        response = self.url_open('/sl_google_maps/partners?ids=%d' % self.partner.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Map Test', response.text)

    def test_partners_page_rejects_rubbish_ids(self):
        self.authenticate('admin', 'admin')
        self.assertEqual(self.url_open('/sl_google_maps/partners?ids=abc').status_code, 404)
        self.assertEqual(self.url_open('/sl_google_maps/partners?ids=').status_code, 404)

    def test_map_pages_require_login(self):
        response = self.url_open('/sl_google_maps/partner/%d' % self.partner.id,
                                 allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
