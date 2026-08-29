# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request


class SlGoogleMaps(http.Controller):

    def _readable(self, partner_ids):
        """Partners the logged-in user may actually see. No sudo anywhere."""
        partners = request.env['res.partner'].browse(partner_ids).exists()
        try:
            partners.read(['display_name'])
        except AccessError:
            raise request.not_found()
        return partners

    @http.route('/sl_google_maps/partner/<int:partner_id>', type='http',
                auth='user', sitemap=False)
    def partner_map(self, partner_id, **kw):
        partner = self._readable([partner_id])
        if not partner:
            raise request.not_found()
        return request.render('sl_google_maps.partner_map_page', {
            'partner': partner,
            'embed_url': partner._map_embed_url(),
            'search_url': partner._map_search_url(),
            'directions_url': partner._map_directions_url(),
        })

    @http.route('/sl_google_maps/partners', type='http', auth='user', sitemap=False)
    def partners_map(self, ids='', **kw):
        try:
            partner_ids = [int(value) for value in ids.split(',') if value.strip()]
        except ValueError:
            raise request.not_found()
        if not partner_ids:
            raise request.not_found()

        partners = self._readable(partner_ids)
        mappable = partners.filtered('has_mappable_address')
        company = request.env.company
        return request.render('sl_google_maps.partners_map_page', {
            'partners': mappable,
            'markers': json.dumps(request.env['res.partner']._map_markers(mappable)),
            'api_key': company.google_maps_api_key or '',
            'static_url': request.env['res.partner']._static_map_url(mappable),
            'skipped': len(partners) - len(mappable),
            'base_url': request.env['ir.config_parameter'].sudo().get_param('web.base.url', ''),
        })
