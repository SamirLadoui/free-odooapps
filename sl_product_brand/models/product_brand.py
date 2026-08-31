# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductBrand(models.Model):
    _name = 'sl.product.brand'
    _description = 'Product Brand'
    _order = 'name'
    _inherit = ['mail.thread']

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(help="Short code, handy for exports and imports.")
    logo = fields.Image(max_width=512, max_height=512)
    partner_id = fields.Many2one(
        'res.partner', string='Brand Owner',
        help="The manufacturer or licence holder, if you track one.")
    website = fields.Char()
    description = fields.Text()
    active = fields.Boolean(default=True)

    product_ids = fields.One2many('product.template', 'sl_brand_id', string='Products')
    product_count = fields.Integer(compute='_compute_product_count')

    @api.depends('product_ids')
    def _compute_product_count(self):
        for brand in self:
            brand.product_count = len(brand.product_ids)

    @api.constrains('name')
    def _check_name_unique(self):
        for brand in self:
            if self.search_count([('id', '!=', brand.id), ('name', '=ilike', brand.name)]):
                raise ValidationError(
                    _("A brand called '%s' already exists.") % brand.name)

    @api.constrains('code')
    def _check_code_unique(self):
        for brand in self.filtered('code'):
            if self.search_count([('id', '!=', brand.id), ('code', '=ilike', brand.code)]):
                raise ValidationError(
                    _("Brand code '%s' is already used.") % brand.code)

    def action_view_products(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Products"),
            'res_model': 'product.template',
            'view_mode': 'kanban,list,form',
            'domain': [('sl_brand_id', '=', self.id)],
            'context': {'default_sl_brand_id': self.id},
        }


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    sl_brand_id = fields.Many2one(
        'sl.product.brand', string='Brand', ondelete='restrict', index=True)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    sl_brand_id = fields.Many2one(
        related='product_tmpl_id.sl_brand_id', store=True, index=True)
