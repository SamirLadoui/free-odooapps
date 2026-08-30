# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

DAYS_IN_WEEK = 7
DAYS_IN_MONTH = 30


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    sl_rentable = fields.Boolean(
        string='Can Be Rented',
        help="Offer this product for hire as well as, or instead of, sale.")
    sl_rental_price_day = fields.Float(string='Price Per Day')
    sl_rental_price_week = fields.Float(string='Price Per Week')
    sl_rental_price_month = fields.Float(string='Price Per Month')
    sl_rental_units = fields.Integer(
        string='Units Available', default=1,
        help="How many of this item you own. Bookings are refused once they are "
             "all out.")

    @api.constrains('sl_rentable', 'sl_rental_price_day', 'sl_rental_price_week',
                    'sl_rental_price_month')
    def _check_rental_prices(self):
        for product in self:
            prices = (product.sl_rental_price_day, product.sl_rental_price_week,
                      product.sl_rental_price_month)
            if any(price < 0 for price in prices):
                raise ValidationError(_("A rental price cannot be negative."))
            if product.sl_rentable and not any(prices):
                raise ValidationError(_(
                    "%s is marked rentable but has no rental price. Set at least "
                    "a daily rate.") % product.name)

    @api.constrains('sl_rental_units')
    def _check_units(self):
        for product in self:
            if product.sl_rentable and product.sl_rental_units < 1:
                raise ValidationError(_(
                    "%s must have at least one unit to rent out.") % product.name)

    def _rental_rates(self):
        """The rates that are actually set, as (days_covered, price)."""
        self.ensure_one()
        rates = []
        if self.sl_rental_price_day:
            rates.append((1, self.sl_rental_price_day))
        if self.sl_rental_price_week:
            rates.append((DAYS_IN_WEEK, self.sl_rental_price_week))
        if self.sl_rental_price_month:
            rates.append((DAYS_IN_MONTH, self.sl_rental_price_month))
        return rates

    def _rental_price_for(self, days):
        """Cheapest way to cover `days` with the rates that are set.

        Taking the largest rate first looks right and is not: with a 10/day,
        60/week, 200/month card, 29 days greedily costs 4 weeks plus a day =
        250, while 30 days costs 200. A longer hire coming out cheaper is a
        pricing bug customers do notice.

        So this is a smallest-cost cover instead. A block may overshoot the
        days needed - buying a month for 29 days is allowed and is what makes
        the price non-decreasing as the hire gets longer.
        """
        self.ensure_one()
        if days <= 0:
            return 0.0
        rates = self._rental_rates()
        if not rates:
            return 0.0

        # best[d] = cheapest cover for d days; overshoot clamps to best[0] = 0.
        best = [0.0] * (days + 1)
        for day in range(1, days + 1):
            best[day] = min(
                price + best[max(0, day - covered)] for covered, price in rates)
        return best[days]


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _rental_price_for(self, days):
        self.ensure_one()
        return self.product_tmpl_id._rental_price_for(days)

    def _rented_quantity_between(self, start, stop, exclude_line=None):
        """How many units are already out on confirmed orders in that window."""
        self.ensure_one()
        domain = [
            ('product_id', '=', self.id),
            ('sl_is_rental', '=', True),
            ('order_id.state', 'in', ('sale', 'done')),
            ('sl_rental_start', '<', stop),
            ('sl_rental_return', '>', start),
        ]
        if exclude_line:
            domain.append(('id', '!=', exclude_line.id))
        lines = self.env['sale.order.line'].search(domain)
        return sum(lines.mapped('product_uom_qty'))
