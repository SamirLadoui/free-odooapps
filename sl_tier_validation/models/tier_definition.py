# -*- coding: utf-8 -*-
"""Who has to agree before a record may move on.

A definition says: on this model, when somebody tries to set this field to
this value, these people have to approve first. That covers the shape almost
every approval actually has - a purchase order that may not be confirmed above
a certain amount until a manager says so - without asking anybody to write
code for it.

Several definitions on one model are tiers: they are asked in sequence, and
the record cannot move until every one of them has agreed. The sequence is
what makes it a hierarchy rather than a crowd.
"""
from ast import literal_eval

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class TierDefinition(models.Model):
    _name = 'sl.tier.definition'
    _description = 'Approval Tier'
    _order = 'model_id, sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(
        default=10,
        help='Tiers are asked in this order. The record moves when the last '
             'of them has agreed.')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    model_id = fields.Many2one(
        'ir.model', string='Model', required=True, ondelete='cascade',
        domain=[('transient', '=', False)])
    model_name = fields.Char(related='model_id.model', store=True,
                             string='Technical Model')

    trigger_field = fields.Char(
        string='Field', required=True, default='state',
        help='The field whose change needs approving. Usually the status.')
    trigger_value = fields.Char(
        string='Value', required=True,
        help='Approval is needed to set the field to this. Anything else is '
             'left alone.')
    domain = fields.Char(
        string='Only When', default='[]',
        help='Records this tier applies to. Leave as [] for all of them - the '
             'usual use is an amount above which somebody has to agree.')

    reviewer_ids = fields.Many2many('res.users', string='Reviewers')
    reviewer_group_id = fields.Many2one(
        'res.groups', string='Reviewer Group',
        help='Anybody in this group may answer for this tier.')

    @api.constrains('reviewer_ids', 'reviewer_group_id')
    def _check_somebody_reviews(self):
        for definition in self:
            if not definition.reviewer_ids and not definition.reviewer_group_id:
                raise ValidationError(_(
                    'A tier with nobody to review it can never be approved, so '
                    'it would stop the record for good. Name a reviewer or a '
                    'group.'))

    @api.constrains('trigger_field', 'model_id')
    def _check_field_exists(self):
        """Checked here rather than the first time somebody is blocked by a
        tier that can never fire."""
        for definition in self:
            model_name = definition.model_id.model
            if not model_name or model_name not in self.env:
                continue
            if definition.trigger_field not in self.env[model_name]._fields:
                raise ValidationError(_(
                    'There is no field called %(field)s on %(model)s.',
                    field=definition.trigger_field, model=model_name))

    @api.constrains('domain', 'model_id')
    def _check_domain(self):
        for definition in self.filtered('domain'):
            try:
                parsed = literal_eval(definition.domain or '[]')
                if not isinstance(parsed, (list, tuple)):
                    raise ValueError('a domain is a list')
            except Exception as error:
                raise ValidationError(_(
                    'That is not a valid domain: %s', error)) from None
            if parsed and definition.model_name in self.env:
                try:
                    self.env[definition.model_name].search(list(parsed), limit=1)
                except Exception as error:
                    raise ValidationError(_(
                        'The domain does not work on %(model)s: %(error)s',
                        model=definition.model_name, error=error)) from None

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            # Checked here as well as in the constraint: a constraint does not
            # run for a field that was never in the values, so a tier created
            # with no reviewer at all would save and then hold its records for
            # good with nobody able to release them.
            if not values.get('reviewer_ids') and not values.get('reviewer_group_id'):
                raise ValidationError(_(
                    'A tier with nobody to review it can never be approved, so '
                    'it would stop the record for good. Name a reviewer or a '
                    'group.'))
        definitions = super().create(vals_list)
        self._sl_reload()
        return definitions

    def write(self, vals):
        result = super().write(vals)
        self._sl_reload()
        return result

    def unlink(self):
        result = super().unlink()
        self._sl_reload()
        return result

    def _sl_reload(self):
        """The set of watched models is cached, so a new tier has to say so."""
        registry = self.env.registry
        if hasattr(registry, 'clear_cache'):
            registry.clear_caches()
        else:
            registry.clear_caches()

    def _as_domain(self):
        self.ensure_one()
        return list(literal_eval(self.domain or '[]'))

    def _reviewers(self):
        """Everybody entitled to answer this tier."""
        self.ensure_one()
        users = self.reviewer_ids
        if self.reviewer_group_id:
            field = ('user_ids' if 'user_ids' in self.reviewer_group_id._fields
                     else 'users')
            users |= self.reviewer_group_id[field]
        return users

    @api.model
    def _for(self, record, field_name, value):
        """The tiers that stand between this record and that value."""
        definitions = self.search([
            ('model_name', '=', record._name),
            ('trigger_field', '=', field_name),
            ('trigger_value', '=', str(value)),
        ])
        return definitions.filtered(
            lambda one: not one._as_domain()
            or record.filtered_domain(one._as_domain()))
