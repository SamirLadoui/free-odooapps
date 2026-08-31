# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SignatureConfig(models.Model):
    _name = 'sl.signature.config'
    _description = 'Signable Model'
    _order = 'model_id'

    model_id = fields.Many2one(
        'ir.model', string='Model', required=True, ondelete='cascade',
        domain="[('transient', '=', False)]")
    model_name = fields.Char(related='model_id.model', store=True)
    label = fields.Char(
        string='Menu Label', default='Sign this record', required=True,
        help="What the entry is called in the model's Action menu.")
    note = fields.Char(
        string='Default Purpose',
        help="Pre-filled on the signing form, e.g. 'Delivery accepted'.")
    action_id = fields.Many2one(
        'ir.actions.server', readonly=True, copy=False, ondelete='set null')
    active = fields.Boolean(default=True)

    @api.constrains('model_id')
    def _check_model_unique(self):
        for config in self:
            clash = self.search([
                ('id', '!=', config.id), ('model_id', '=', config.model_id.id),
            ], limit=1)
            if clash:
                raise ValidationError(
                    _("%s is already signable.") % config.model_id.model)

    def _action_values(self):
        self.ensure_one()
        return {
            'name': self.label,
            'model_id': self.model_id.id,
            'binding_model_id': self.model_id.id,
            'binding_type': 'action',
            'state': 'code',
            'code': ("action = env['sl.signature.config'].browse(%d)._open_wizard()"
                     % self.id),
        }

    def _sync_action(self):
        for config in self:
            if not config.active:
                config.action_id.unlink()
                continue
            if config.action_id:
                config.action_id.write(config._action_values())
            else:
                config.action_id = self.env['ir.actions.server'].create(
                    config._action_values())

    @api.model_create_multi
    def create(self, vals_list):
        configs = super().create(vals_list)
        configs._sync_action()
        return configs

    def write(self, vals):
        result = super().write(vals)
        if {'label', 'model_id', 'active'} & set(vals):
            self._sync_action()
        return result

    def unlink(self):
        self.action_id.unlink()
        return super().unlink()

    def _open_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.label,
            'res_model': 'sl.signature.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': dict(self.env.context, default_config_id=self.id,
                            default_note=self.note or False),
        }
