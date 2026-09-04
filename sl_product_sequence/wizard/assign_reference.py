# -*- coding: utf-8 -*-
"""Numbering the products that are already there.

Turning the numbering on does nothing for the eight hundred products already
in the database, which is the reason most people are looking for it in the
first place.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AssignReference(models.TransientModel):
    _name = 'sl.product.reference.wizard'
    _description = 'Assign Product References'

    product_count = fields.Integer(string='Selected', readonly=True)
    todo_count = fields.Integer(string='Will Be Numbered', readonly=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        templates = self._sl_templates()
        values['product_count'] = len(templates)
        values['todo_count'] = len(templates.filtered(
            lambda template: not template.default_code
            and template._sl_sequence()))
        return values

    def _sl_templates(self):
        context = self.env.context
        records = self.env[context.get('active_model') or 'product.template'] \
            .browse(context.get('active_ids') or [])
        if records._name == 'product.product':
            return records.product_tmpl_id
        return records

    def action_assign(self):
        self.ensure_one()
        templates = self._sl_templates().filtered(
            lambda template: not template.default_code)
        if not templates:
            raise UserError(_(
                'Every selected product already has a reference. Existing '
                'ones are never replaced.'))
        numbered = 0
        for template in templates:
            reference = template._sl_next_reference()
            if reference:
                template.default_code = reference
                numbered += 1
        if not numbered:
            raise UserError(_(
                'None of these products has numbering to draw on. Set it on '
                'their category, or on the company.'))
        return {'type': 'ir.actions.act_window_close'}
