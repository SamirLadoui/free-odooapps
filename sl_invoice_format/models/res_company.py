# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Which columns appear. Description and subtotal are deliberately not
    # optional: an invoice line with neither says nothing.
    invoice_show_quantity = fields.Boolean(string='Show Quantity', default=True)
    invoice_show_price_unit = fields.Boolean(string='Show Unit Price', default=True)
    invoice_show_taxes = fields.Boolean(string='Show Taxes Column', default=True)
    invoice_show_product_code = fields.Boolean(
        string='Show Product Code', default=False,
        help="Prefixes each line with the product's internal reference.")
    invoice_show_product_image = fields.Boolean(
        string='Show Product Image', default=False)

    invoice_label_description = fields.Char(string='Description Heading')
    invoice_label_quantity = fields.Char(string='Quantity Heading')
    invoice_label_price_unit = fields.Char(string='Unit Price Heading')
    invoice_label_subtotal = fields.Char(string='Subtotal Heading')

    invoice_footer_note = fields.Text(
        string='Invoice Footer Note',
        help="Printed under every invoice, above the company footer.")

    @api.constrains('invoice_show_quantity', 'invoice_show_price_unit')
    def _check_columns(self):
        """Hiding both leaves a line nobody can check."""
        for company in self:
            if not company.invoice_show_quantity and not company.invoice_show_price_unit:
                raise ValidationError(_(
                    "Hide either the quantity or the unit price, but not both: "
                    "the customer would have no way to check the subtotal."))

    def _invoice_label(self, key):
        """The configured heading, or Odoo's default when none is set."""
        self.ensure_one()
        defaults = {
            'description': _("Description"),
            'quantity': _("Quantity"),
            'price_unit': _("Unit Price"),
            'subtotal': _("Amount"),
        }
        return getattr(self, 'invoice_label_%s' % key, False) or defaults.get(key, '')
