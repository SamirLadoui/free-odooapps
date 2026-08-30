# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Returns are recorded as ordinary orders holding negative quantities, which is
# how the point of sale already represents a refund. Nothing new is invented:
# the only addition is the link back to the order being returned.


class PosOrder(models.Model):
    _inherit = 'pos.order'

    sl_return_of_order_id = fields.Many2one(
        'pos.order', string='Return Of', readonly=True, copy=False, index=True,
        help='The order these lines are being returned from.')
    sl_return_ids = fields.One2many(
        'pos.order', 'sl_return_of_order_id', string='Returns')
    sl_has_returns = fields.Boolean(compute='_compute_sl_has_returns')

    @api.depends('sl_return_ids')
    def _compute_sl_has_returns(self):
        for order in self:
            order.sl_has_returns = bool(order.sl_return_ids)

    @api.constrains('sl_return_of_order_id')
    def _check_return_target(self):
        for order in self:
            original = order.sl_return_of_order_id
            if not original:
                continue
            if original == order:
                raise ValidationError(_('An order cannot be a return of itself.'))
            if original.sl_return_of_order_id:
                raise ValidationError(_(
                    'A return cannot itself be returned. Return the original '
                    'order instead.'))

    # -- getting the link back from the till ------------------------------

    @api.model
    def _load_pos_data_fields(self, *args):
        """Ship the link to the client so a return can carry it back.

        Takes *args because the argument changed shape between versions: 18.0
        passes a config id, 19.0 passes the config record.
        """
        return super()._load_pos_data_fields(*args) + ['sl_return_of_order_id']

    @api.model
    def _order_fields(self, ui_order):
        """The pre-18 route for the same value."""
        values = super()._order_fields(ui_order)
        if ui_order.get('sl_return_of_order_id'):
            values['sl_return_of_order_id'] = ui_order['sl_return_of_order_id']
        return values

    # -- finding the order to return --------------------------------------

    @api.model
    def sl_find_returnable(self, reference):
        """The order a cashier is looking for, with what is left to return.

        Matched on the receipt reference or the order name, because the
        receipt in a customer's hand shows one or the other depending on how
        the shop is set up.
        """
        reference = (reference or '').strip()
        if not reference:
            raise UserError(_('Type a receipt number to look for.'))

        order = self.search([
            '|', ('pos_reference', '=', reference), ('name', '=', reference),
            ('state', 'in', ('paid', 'done', 'invoiced')),
            ('sl_return_of_order_id', '=', False),
        ], limit=1)
        if not order:
            raise UserError(_('No paid order found for "%s".', reference))
        return order._sl_return_payload()

    def _sl_return_payload(self):
        """What the point of sale needs to show the return screen."""
        self.ensure_one()
        lines = []
        for line in self.lines:
            remaining = line._sl_returnable_qty()
            if remaining <= 0:
                continue
            lines.append({
                'line_id': line.id,
                'product_id': line.product_id.id,
                'product_name': line.product_id.display_name,
                'price_unit': line.price_unit,
                'discount': line.discount,
                'qty_sold': line.qty,
                'qty_returned': line.qty - remaining,
                'qty_returnable': remaining,
            })
        return {
            'order_id': self.id,
            'name': self.name,
            'reference': self.pos_reference,
            'date_order': fields.Datetime.to_string(self.date_order),
            'partner_id': self.partner_id.id,
            'lines': lines,
        }


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    sl_returned_qty = fields.Float(
        string='Returned', compute='_compute_sl_returned_qty',
        help='How much of this line has already been given back.')

    def _compute_sl_returned_qty(self):
        for line in self:
            line.sl_returned_qty = line._sl_returned_qty()

    def _sl_returned_qty(self):
        """How much of this line has already come back, as a positive number.

        Counted across every return of the order, so a customer bringing items
        back twice cannot be refunded the same unit twice.
        """
        self.ensure_one()
        returns = self.order_id.sl_return_ids
        if not returns:
            return 0.0
        matching = returns.mapped('lines').filtered(
            lambda l: l.product_id == self.product_id)
        # Return lines carry negative quantities; report the total as positive.
        return -sum(matching.mapped('qty'))

    def _sl_returnable_qty(self):
        """What is still available to give back on this line."""
        self.ensure_one()
        if self.qty <= 0:
            return 0.0  # already a refund line; nothing to return from it
        return max(0.0, self.qty - self._sl_returned_qty())
