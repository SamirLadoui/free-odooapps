# -*- coding: utf-8 -*-
"""Holding a record still until its approvals are in.

Every model inherits `base`, so the check lives here and applies to whatever
an administrator names - no code per model, which is the thing that stops most
approval add-ons from being usable.

The cost of sitting in the path of every write is paid on every write in the
database, so the guard comes first: the set of models with tiers is cached,
and a model that is not among them does no extra work at all.
"""
from odoo import _, api, models, tools
from odoo.exceptions import UserError


class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model
    @tools.ormcache()
    def _sl_tier_models(self):
        """{model_name: (field, ...)} for the models an approval stands on."""
        try:
            definitions = self.env['sl.tier.definition'].sudo().search([])
        except Exception:
            # Installing, or the table is not there yet.
            return {}
        found = {}
        for definition in definitions:
            if definition.model_name:
                found.setdefault(definition.model_name, set()).add(
                    definition.trigger_field)
        return {name: tuple(fields) for name, fields in found.items()}

    def _sl_pending_reviews(self):
        self.ensure_one()
        return self.env['sl.tier.review'].sudo().search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('status', '=', 'pending'),
        ])

    def _sl_rejected_reviews(self):
        self.ensure_one()
        return self.env['sl.tier.review'].sudo().search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('status', '=', 'rejected'),
        ])

    def write(self, vals):
        watched = self.env['base']._sl_tier_models().get(self._name)
        if watched and not self.env.context.get('sl_tier_bypass'):
            for field_name in watched:
                if field_name in vals:
                    self._sl_check_allowed(field_name, vals[field_name])
        return super().write(vals)

    def _sl_check_allowed(self, field_name, value):
        """Refuse the change while somebody still has to agree to it."""
        definitions = self.env['sl.tier.definition'].sudo()
        for record in self:
            needed = definitions._for(record, field_name, value)
            if not needed:
                continue
            rejected = record._sl_rejected_reviews()
            if rejected:
                raise UserError(_(
                    '%(record)s was rejected by %(who)s: %(why)s',
                    record=record.display_name,
                    who=rejected[0].done_by_id.display_name,
                    why=rejected[0].comment or _('no reason given')))
            pending = record._sl_pending_reviews()
            if pending:
                raise UserError(_(
                    '%(record)s is waiting for %(names)s to approve it.',
                    record=record.display_name,
                    names=', '.join(sorted(set(pending.mapped('name'))))))
            approved = self.env['sl.tier.review'].sudo().search_count([
                ('res_model', '=', record._name),
                ('res_id', '=', record.id),
                ('status', '=', 'approved'),
            ])
            if not approved:
                raise UserError(_(
                    '%(record)s needs approving first. Ask for it from the '
                    'record.', record=record.display_name))

    # -- asking ------------------------------------------------------------

    def sl_request_validation(self, field_name='state', value=None):
        """Create the reviews this record needs, in tier order."""
        self.ensure_one()
        definitions = self.env['sl.tier.definition'].sudo()._for(
            self, field_name, value)
        if not definitions:
            raise UserError(_('Nothing needs approving for that change.'))
        reviews = self.env['sl.tier.review'].sudo()
        existing = reviews.search([('res_model', '=', self._name),
                                   ('res_id', '=', self.id)])
        if existing.filtered(lambda one: one.status == 'pending'):
            raise UserError(_('This has already been sent for approval.'))
        this_round = max(existing.mapped('round') or [0]) + 1
        for definition in definitions:
            reviews |= reviews.create({
                'definition_id': definition.id,
                'res_model': self._name,
                'res_id': self.id,
                'requested_by_id': self.env.user.id,
                'round': this_round,
            })
        return reviews

    def sl_reviews(self):
        self.ensure_one()
        return self.env['sl.tier.review'].sudo().search([
            ('res_model', '=', self._name), ('res_id', '=', self.id)])
