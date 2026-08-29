# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    google_maps_api_key = fields.Char(
        string='Google Maps API Key',
        help="Optional. Without a key the module still works: map buttons open "
             "google.com/maps in a new tab. With a key, maps are embedded "
             "directly in Odoo.")
    google_maps_zoom = fields.Integer(string='Default Zoom', default=14)

    @api.constrains('google_maps_zoom')
    def _check_google_maps_zoom(self):
        """Zero means "use the default"; anything else must be a real zoom level."""
        for company in self:
            zoom = company.google_maps_zoom
            if zoom and not 1 <= zoom <= 21:
                raise ValidationError(_(
                    "Google Maps zoom must be between 1 and 21, or 0 to use the default."))
            if zoom < 0:
                raise ValidationError(_("Google Maps zoom cannot be negative."))
