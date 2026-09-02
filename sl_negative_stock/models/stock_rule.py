# -*- coding: utf-8 -*-
"""Where stock is not allowed to go below zero, and where it is.

Odoo lets stock go negative on purpose: a shop that receives goods after it
sells them would otherwise be unable to trade. The trouble is that it is
allowed everywhere, so a genuine mistake in a warehouse looks exactly like the
intended behaviour in a shop, and nobody finds it until a stock count.

A rule says where the line is drawn: which warehouse or location, which
products, and whether going under is refused outright or merely warned about.
Everywhere without a rule behaves exactly as Odoo always did.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class NegativeStockRule(models.Model):
    _name = 'sl.negative.stock.rule'
    _description = 'Negative Stock Rule'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(
        default=10, help='The first rule that fits a move is the one applied.')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)

    location_id = fields.Many2one(
        'stock.location', string='Location',
        domain="[('usage', '=', 'internal')]",
        help='The location stock is taken from. Empty means anywhere internal.')
    include_children = fields.Boolean(
        string='And Everything Under It', default=True,
        help='A rule on a warehouse usually means its shelves too.')

    product_ids = fields.Many2many(
        'product.product', string='Products',
        help='Leave empty for every product.')
    category_ids = fields.Many2many(
        'product.category', string='Categories',
        help='Leave empty for every category.')

    behaviour = fields.Selection(
        [('block', 'Refuse The Move'), ('warn', 'Allow It And Record It')],
        default='block', required=True,
        help='Refusing is right in a warehouse that counts. Recording is right '
             'where going under is normal but worth knowing about.')

    @api.constrains('location_id', 'company_id')
    def _check_location_company(self):
        for rule in self:
            owner = rule.location_id.company_id
            if owner and owner != rule.company_id:
                raise ValidationError(_(
                    'That location belongs to another company.'))

    def _covers(self, move, location):
        """Whether this rule speaks to this move leaving this location."""
        self.ensure_one()
        if self.location_id:
            if self.include_children:
                if not location.parent_path or not self.location_id.parent_path:
                    if location != self.location_id:
                        return False
                elif not location.parent_path.startswith(
                        self.location_id.parent_path):
                    return False
            elif location != self.location_id:
                return False
        product = move.product_id
        if self.product_ids and product not in self.product_ids:
            return False
        if self.category_ids and product.categ_id not in self.category_ids:
            return False
        return True

    @api.model
    def _for(self, move, location):
        """The first rule that fits, or nothing.

        First rather than all of them: two rules disagreeing about the same
        shelf is a question the sequence answers, and applying both would mean
        the stricter always won regardless of what anybody ordered.
        """
        company = move.company_id or self.env.company
        for rule in self.search([('company_id', '=', company.id)],
                                order='sequence, id'):
            if rule._covers(move, location):
                return rule
        return self.browse()
