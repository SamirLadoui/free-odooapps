# -*- coding: utf-8 -*-
"""One tier's answer about one record.

A review is kept after it is answered rather than deleted, because the useful
question afterwards is who agreed and when - and a record whose approvals were
tidied away is a record nobody can account for.

Asking again starts a fresh set. The old ones stay, marked as belonging to an
earlier request, so a document that went round twice shows that it did.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TierReview(models.Model):
    _name = 'sl.tier.review'
    _description = 'Approval'
    _order = 'res_model, res_id, sequence, id'

    definition_id = fields.Many2one(
        'sl.tier.definition', required=True, ondelete='cascade')
    name = fields.Char(related='definition_id.name', store=True)
    sequence = fields.Integer(related='definition_id.sequence', store=True)

    res_model = fields.Char(required=True, index=True, readonly=True)
    res_id = fields.Integer(required=True, index=True, readonly=True)
    record_label = fields.Char(compute='_compute_record_label', string='Record')

    status = fields.Selection(
        [('pending', 'Waiting'), ('approved', 'Approved'),
         ('rejected', 'Rejected')],
        default='pending', required=True, readonly=True)
    requested_by_id = fields.Many2one('res.users', readonly=True)
    requested_on = fields.Datetime(
        readonly=True, default=lambda self: fields.Datetime.now())
    done_by_id = fields.Many2one('res.users', string='Answered By', readonly=True)
    done_on = fields.Datetime(readonly=True)
    comment = fields.Char()
    round = fields.Integer(
        default=1, readonly=True,
        help='Which time of asking this belongs to. A document that went round '
             'twice shows that it did.')

    def _compute_record_label(self):
        for review in self:
            review.record_label = ''
            if review.res_model in self.env:
                record = self.env[review.res_model].browse(review.res_id).exists()
                review.record_label = record.display_name if record else ''

    def _may_answer(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        return user in self.definition_id._reviewers()

    def _answer(self, status, comment=None):
        for review in self:
            if review.status != 'pending':
                raise UserError(_(
                    'That approval has already been answered.'))
            if not review._may_answer():
                raise UserError(_(
                    'You are not one of the reviewers for %s.', review.name))
            review.write({
                'status': status,
                'done_by_id': self.env.user.id,
                'done_on': fields.Datetime.now(),
                'comment': comment or review.comment,
            })
        return True

    def action_approve(self):
        return self._answer('approved')

    def action_reject(self):
        for review in self:
            if not (review.comment or '').strip():
                raise UserError(_(
                    'Say why it was rejected. A refusal with no reason sends '
                    'the document back with nothing to act on.'))
        return self._answer('rejected')

    def action_open_record(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
        }
