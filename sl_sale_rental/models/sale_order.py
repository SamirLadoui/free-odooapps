# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    sl_is_rental = fields.Boolean(string='Rental')
    sl_rental_start = fields.Date(string='Hire From')
    sl_rental_return = fields.Date(string='Return By')
    sl_rental_days = fields.Integer(
        string='Days', compute='_compute_rental_days', store=True)

    @api.depends('sl_rental_start', 'sl_rental_return', 'sl_is_rental')
    def _compute_rental_days(self):
        """Both ends inclusive: picking up and returning on the same day is one
        day's hire, not zero."""
        for line in self:
            if (line.sl_is_rental and line.sl_rental_start
                    and line.sl_rental_return):
                line.sl_rental_days = (
                    line.sl_rental_return - line.sl_rental_start).days + 1
            else:
                line.sl_rental_days = 0

    @api.constrains('sl_is_rental', 'sl_rental_start', 'sl_rental_return')
    def _check_rental_dates(self):
        for line in self.filtered('sl_is_rental'):
            if not line.sl_rental_start or not line.sl_rental_return:
                raise ValidationError(_(
                    "A rental line needs both a hire date and a return date."))
            if line.sl_rental_return < line.sl_rental_start:
                raise ValidationError(_(
                    "'%s' is due back before it goes out.") % line.product_id.display_name)

    @api.constrains('sl_is_rental', 'product_id')
    def _check_product_is_rentable(self):
        for line in self.filtered('sl_is_rental'):
            if not line.product_id.sl_rentable:
                raise ValidationError(_(
                    "%s is not marked as rentable.") % line.product_id.display_name)

    @api.constrains('sl_is_rental', 'product_id', 'product_uom_qty',
                    'sl_rental_start', 'sl_rental_return')
    def _check_availability(self):
        """Refuse a booking once every unit is already out.

        Only confirmed orders hold stock: a quotation should not stop somebody
        else booking, or one abandoned draft blocks the item forever.
        """
        for line in self.filtered(
                lambda l: l.sl_is_rental and l.order_id.state in ('sale', 'done')):
            if not (line.sl_rental_start and line.sl_rental_return):
                continue
            already_out = line.product_id._rented_quantity_between(
                line.sl_rental_start, line.sl_rental_return, exclude_line=line)
            owned = line.product_id.sl_rental_units or 0
            if already_out + line.product_uom_qty > owned:
                raise ValidationError(_(
                    "Only %(free)s of %(product)s free between %(start)s and "
                    "%(end)s: %(out)s of %(owned)s are already out.") % {
                        'free': max(0, owned - already_out),
                        'product': line.product_id.display_name,
                        'start': line.sl_rental_start,
                        'end': line.sl_rental_return,
                        'out': already_out, 'owned': owned})

    @api.onchange('sl_is_rental', 'sl_rental_start', 'sl_rental_return', 'product_id')
    def _onchange_rental(self):
        """Price the hire from the product's own rates."""
        if not self.sl_is_rental or not self.product_id:
            return
        if self.sl_rental_start and self.sl_rental_return:
            days = (self.sl_rental_return - self.sl_rental_start).days + 1
            if days > 0:
                self.price_unit = self.product_id._rental_price_for(days)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    sl_rental_line_count = fields.Integer(compute='_compute_rental_line_count')

    def action_confirm(self):
        """Check availability here as well as on the line.

        Confirming changes the order's state, not the line's fields, so the
        line constraint does not re-run: without this, a booking that was fine
        as a quotation sails through even when the units are gone.
        """
        result = super().action_confirm()
        self.mapped('order_line').filtered('sl_is_rental')._check_availability()
        return result

    @api.depends('order_line.sl_is_rental')
    def _compute_rental_line_count(self):
        for order in self:
            order.sl_rental_line_count = len(
                order.order_line.filtered('sl_is_rental'))
