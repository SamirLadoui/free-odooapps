# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Touching these through a bulk edit corrupts records rather than updating them.
FORBIDDEN_FIELDS = {
    'id', 'create_uid', 'create_date', 'write_uid', 'write_date',
    '__last_update', 'display_name',
}


class MassEditing(models.Model):
    _name = 'sl.mass.editing'
    _description = 'Mass Editing Configuration'
    _order = 'model_id, name'

    name = fields.Char(required=True)
    model_id = fields.Many2one(
        'ir.model', string='Model', required=True, ondelete='cascade',
        help="The model this bulk edit applies to.")
    model_name = fields.Char(related='model_id.model', string='Model Name', store=True)
    field_ids = fields.Many2many(
        'ir.model.fields', string='Editable Fields', required=True,
        domain="[('model_id', '=', model_id), ('store', '=', True), ('readonly', '=', False)]",
        help="Only these fields can be changed through this bulk edit.")
    action_id = fields.Many2one(
        'ir.actions.server', string='Menu Entry', readonly=True, copy=False,
        ondelete='set null')
    active = fields.Boolean(default=True)

    @api.constrains('name', 'model_id')
    def _check_name_unique(self):
        """A python constraint rather than _sql_constraints: 19.0 dropped support
        for the latter, and this works identically on every version."""
        for record in self:
            clash = self.search([
                ('id', '!=', record.id),
                ('name', '=', record.name),
                ('model_id', '=', record.model_id.id),
            ], limit=1)
            if clash:
                raise ValidationError(_(
                    "A bulk edit named '%(name)s' already exists for %(model)s.")
                    % {'name': record.name, 'model': record.model_id.model})

    @api.onchange('model_id')
    def _onchange_model_id(self):
        self.field_ids = [(5, 0, 0)]

    @api.constrains('field_ids', 'model_id')
    def _check_fields(self):
        for record in self:
            wrong = record.field_ids.filtered(lambda f: f.model_id != record.model_id)
            if wrong:
                raise ValidationError(_(
                    "These fields do not belong to %(model)s: %(fields)s")
                    % {'model': record.model_id.model,
                       'fields': ', '.join(wrong.mapped('name'))})
            forbidden = record.field_ids.filtered(lambda f: f.name in FORBIDDEN_FIELDS)
            if forbidden:
                raise ValidationError(_(
                    "These fields are maintained by Odoo and cannot be bulk edited: %s")
                    % ', '.join(forbidden.mapped('name')))
            unstored = record.field_ids.filtered(lambda f: not f.store)
            if unstored:
                raise ValidationError(_(
                    "These fields are not stored, so writing to them has no effect: %s")
                    % ', '.join(unstored.mapped('name')))

    # -- the Action-menu entry ---------------------------------------------

    def _action_values(self):
        self.ensure_one()
        return {
            'name': self.name,
            'model_id': self.model_id.id,
            'binding_model_id': self.model_id.id,
            'binding_type': 'action',
            'state': 'code',
            'code': ("action = env['sl.mass.editing'].browse(%d)._open_wizard()"
                     % self.id),
        }

    def _sync_action(self):
        """Keep the Action-menu entry in step with the configuration."""
        for record in self:
            if not record.active:
                record.action_id.unlink()
                continue
            if record.action_id:
                record.action_id.write(record._action_values())
            else:
                record.action_id = self.env['ir.actions.server'].create(
                    record._action_values())

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_action()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {'name', 'model_id', 'active'} & set(vals):
            self._sync_action()
        return result

    def unlink(self):
        self.action_id.unlink()
        return super().unlink()

    def _open_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'sl.mass.editing.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': dict(self.env.context, default_mass_edit_id=self.id),
        }
