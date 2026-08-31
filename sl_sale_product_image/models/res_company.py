# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

MIN_SIZE, MAX_SIZE = 16, 200


class ResCompany(models.Model):
    _inherit = 'res.company'

    sale_report_show_image = fields.Boolean(
        string='Product Images On Quotations', default=False)
    sale_report_image_size = fields.Integer(
        string='Image Size (px)', default=48,
        help="Height of each product image on the printed quotation.")

    @api.constrains('sale_report_image_size')
    def _check_image_size(self):
        """A huge image pushes one line per page; a tiny one is a smudge."""
        for company in self:
            size = company.sale_report_image_size
            if size and not MIN_SIZE <= size <= MAX_SIZE:
                raise ValidationError(_(
                    "The image size must be between %(min)s and %(max)s pixels.")
                    % {'min': MIN_SIZE, 'max': MAX_SIZE})

    def _sale_report_image_size(self):
        self.ensure_one()
        size = self.sale_report_image_size or 48
        return min(max(size, MIN_SIZE), MAX_SIZE)
