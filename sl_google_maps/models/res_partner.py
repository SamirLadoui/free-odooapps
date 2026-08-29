# -*- coding: utf-8 -*-
from urllib.parse import quote_plus

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Public Google endpoints. The search URL needs no API key, which is what makes
# the module useful before anyone has set one up.
MAPS_SEARCH = 'https://www.google.com/maps/search/?api=1&query=%s'
MAPS_DIRECTIONS = 'https://www.google.com/maps/dir/?api=1&destination=%s'
MAPS_EMBED = 'https://www.google.com/maps/embed/v1/place?key=%s&q=%s&zoom=%d'
STATIC_MAP = 'https://maps.googleapis.com/maps/api/staticmap'

MAX_STATIC_MARKERS = 40


class ResPartner(models.Model):
    _inherit = 'res.partner'

    has_mappable_address = fields.Boolean(compute='_compute_has_mappable_address')

    @api.depends('street', 'street2', 'city', 'zip', 'state_id', 'country_id',
                 'partner_latitude', 'partner_longitude')
    def _compute_has_mappable_address(self):
        for partner in self:
            partner.has_mappable_address = bool(partner._map_query())

    def _map_query(self):
        """What to hand Google: coordinates when we have them, else the address.

        Coordinates win because they are unambiguous - two towns share a street
        name far more often than they share a latitude.
        """
        self.ensure_one()
        if self.partner_latitude and self.partner_longitude:
            # Fixed precision, not the raw float repr: the stored digits are
            # (10, 7) and 3.0588 reads back as 3.0587999999999997 on some
            # versions, which would end up verbatim in the URL.
            return '%.7f,%.7f' % (self.partner_latitude, self.partner_longitude)
        parts = [self.street, self.street2, self.city, self.zip,
                 self.state_id.name, self.country_id.name]
        return ', '.join(part for part in parts if part)

    def _map_search_url(self):
        self.ensure_one()
        query = self._map_query()
        return MAPS_SEARCH % quote_plus(query) if query else False

    def _map_directions_url(self):
        self.ensure_one()
        query = self._map_query()
        return MAPS_DIRECTIONS % quote_plus(query) if query else False

    def _map_embed_url(self):
        """The in-Odoo embedded map, or False when no API key is configured."""
        self.ensure_one()
        company = self.company_id or self.env.company
        key = company.google_maps_api_key
        query = self._map_query()
        if not key or not query:
            return False
        zoom = min(max(company.google_maps_zoom or 14, 1), 21)
        return MAPS_EMBED % (quote_plus(key), quote_plus(query), zoom)

    @api.model
    def _static_map_url(self, partners):
        """One image showing every partner that has an address.

        The Static Maps API takes markers in the URL, so a multi-partner map
        needs no javascript at all - but the URL has a length limit, hence the
        marker cap.
        """
        company = self.env.company
        key = company.google_maps_api_key
        if not key:
            return False
        markers = []
        for index, partner in enumerate(partners, start=1):
            query = partner._map_query()
            if not query:
                continue
            label = str(index) if index < 10 else ''
            markers.append('markers=%s' % quote_plus(
                'color:red|label:%s|%s' % (label, query)))
            if len(markers) >= MAX_STATIC_MARKERS:
                break
        if not markers:
            return False
        return '%s?size=800x500&scale=2&key=%s&%s' % (
            STATIC_MAP, quote_plus(key), '&'.join(markers))

    @api.model
    def sl_resolve_place_location(self, country_code, state_code=None):
        """Turn the ISO codes Google returns into Odoo records.

        Called from the autocomplete widget, which only ever sees codes.
        """
        result = {}
        if not country_code:
            return result
        country = self.env['res.country'].search(
            [('code', '=ilike', country_code)], limit=1)
        if not country:
            return result
        result['country_id'] = country.id
        if state_code:
            state = self.env['res.country.state'].search([
                ('country_id', '=', country.id),
                ('code', '=ilike', state_code),
            ], limit=1)
            if state:
                result['state_id'] = state.id
        return result

    @api.model
    def _map_markers(self, partners):
        """Marker data for the interactive map page.

        Only partners with real coordinates get a marker: the browser map
        cannot place an address it has not geocoded, and geocoding every row
        server-side would be a request per partner.
        """
        markers = []
        for partner in partners:
            if not (partner.partner_latitude and partner.partner_longitude):
                continue
            markers.append({
                'id': partner.id,
                'name': partner.display_name,
                'lat': partner.partner_latitude,
                'lng': partner.partner_longitude,
                'address': partner._map_query(),
            })
        return markers

    # -- actions -----------------------------------------------------------

    def action_show_on_map(self):
        """One partner: the embedded page when a key is set, Google otherwise."""
        self.ensure_one()
        if not self._map_query():
            raise UserError(_(
                "%s has no address and no coordinates, so there is nothing to "
                "show on a map.") % self.display_name)
        if self._map_embed_url():
            return {
                'type': 'ir.actions.act_url',
                'url': '/sl_google_maps/partner/%d' % self.id,
                'target': 'new',
            }
        return {
            'type': 'ir.actions.act_url',
            'url': self._map_search_url(),
            'target': 'new',
        }

    def action_show_selection_on_map(self):
        """Several partners at once, from the list view's Action menu."""
        mappable = self.filtered('has_mappable_address')
        if not mappable:
            raise UserError(_("None of the selected records has an address."))
        return {
            'type': 'ir.actions.act_url',
            'url': '/sl_google_maps/partners?ids=%s' % ','.join(
                str(pid) for pid in mappable.ids),
            'target': 'new',
        }

