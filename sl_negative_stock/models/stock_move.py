# -*- coding: utf-8 -*-
"""Checking, at the moment the stock actually leaves.

Not when the move is planned: a move created today for next week should not be
refused because the goods have not arrived yet. The question only means
anything when the move is being done, which is where the check sits.

What is counted is the quantity on hand at that location, not the forecast.
A forecast includes what is expected to arrive, and stock that has not arrived
cannot be picked off a shelf.
"""
import logging

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _sl_quantity_leaving(self):
        """How much this move takes out, whatever the release calls it."""
        self.ensure_one()
        for name in ('quantity', 'quantity_done'):
            if name in self._fields:
                value = self[name]
                if value:
                    return value
        return self.product_uom_qty

    def _sl_on_hand(self, location):
        """What is actually on the shelf now, not what is forecast."""
        self.ensure_one()
        product = self.product_id.with_context(
            location=location.id, compute_child=True)
        return product.qty_available

    def _sl_check_negative(self):
        """Refuse, or record, a move that would take stock below zero."""
        rules = self.env['sl.negative.stock.rule'].sudo()
        for move in self:
            if move.product_id.type not in ('product', 'consu'):
                continue
            if 'is_storable' in move.product_id._fields \
                    and not move.product_id.is_storable:
                # 18.0 split storability out of the type; a non-storable
                # product has no quantity to go under.
                continue
            source = move.location_id
            if not source or source.usage != 'internal':
                # Stock arriving from a supplier or a scrap location is not
                # coming off anybody's shelf.
                continue
            rule = rules._for(move, source)
            if not rule:
                continue
            leaving = move._sl_quantity_leaving()
            on_hand = move._sl_on_hand(source)
            if leaving <= on_hand:
                continue
            if rule.behaviour == 'block':
                raise UserError(_(
                    '%(product)s: %(leaving)s would leave %(location)s, which '
                    'holds %(on_hand)s. The rule "%(rule)s" does not allow it '
                    'to go below zero.',
                    product=move.product_id.display_name,
                    leaving=leaving, location=source.display_name,
                    on_hand=on_hand, rule=rule.name))
            move._sl_record_negative(rule, source, leaving, on_hand)
        return True

    def _sl_record_negative(self, rule, source, leaving, on_hand):
        """Say it happened, for a rule that allows it.

        On the transfer rather than on the move: a move has no chatter of its
        own, and the transfer is where somebody would go looking. When there is
        no transfer - an inventory adjustment, a scrap - the log is all there
        is, which is still better than the move passing silently.
        """
        self.ensure_one()
        message = _(
            '%(product)s went below zero at %(location)s: %(leaving)s left a '
            'location holding %(on_hand)s. Allowed by the rule "%(rule)s".',
            product=self.product_id.display_name,
            location=source.display_name,
            leaving=leaving, on_hand=on_hand, rule=rule.name)
        picking = self.picking_id
        if picking:
            picking.message_post(body=message)
        _logger.info('%s', message)
        return message

    def _action_done(self, *args, **kwargs):
        """The moment the stock actually leaves."""
        self._sl_check_negative()
        return super()._action_done(*args, **kwargs)
