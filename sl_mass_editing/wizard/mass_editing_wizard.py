# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

X2MANY = ('many2many', 'one2many')
# Which operations make sense for which kind of field.
OPERATIONS_BY_TYPE = {
    'many2many': ('set', 'append', 'remove', 'clear'),
    'one2many': ('clear',),
    'many2one': ('set', 'clear'),
}
DEFAULT_OPERATIONS = ('set', 'clear')


class MassEditingWizard(models.TransientModel):
    _name = 'sl.mass.editing.wizard'
    _description = 'Mass Editing'

    mass_edit_id = fields.Many2one('sl.mass.editing', required=True, ondelete='cascade')
    model_name = fields.Char(related='mass_edit_id.model_name')
    record_count = fields.Integer(compute='_compute_record_count')
    line_ids = fields.One2many('sl.mass.editing.line', 'wizard_id', string='Changes')

    def _target_ids(self):
        return self.env.context.get('active_ids') or []

    @api.depends('mass_edit_id')
    def _compute_record_count(self):
        count = len(self._target_ids())
        for wizard in self:
            wizard.record_count = count

    def _target_records(self):
        self.ensure_one()
        model = self.env[self.mass_edit_id.model_name]
        return model.browse(self._target_ids()).exists()

    def action_apply(self):
        self.ensure_one()
        records = self._target_records()
        if not records:
            raise UserError(_("Nothing selected. Pick some records first."))
        if not self.line_ids:
            raise UserError(_("Add at least one change to apply."))

        values = {}
        for line in self.line_ids:
            name = line.field_id.name
            command = line._write_value()
            if name in values and isinstance(values[name], list) and isinstance(command, list):
                # Several lines on the same x2many field stack their commands.
                values[name] = values[name] + command
            else:
                values[name] = command

        # No sudo: the user's own write access decides what happens.
        records.write(values)
        return {'type': 'ir.actions.act_window_close'}


class MassEditingLine(models.TransientModel):
    _name = 'sl.mass.editing.line'
    _description = 'Mass Editing Change'

    wizard_id = fields.Many2one('sl.mass.editing.wizard', required=True, ondelete='cascade')
    # The configuration is the whitelist: a line may only touch a field the
    # administrator listed, whatever the client sends.
    allowed_field_ids = fields.Many2many(
        related='wizard_id.mass_edit_id.field_ids', string='Allowed Fields')
    field_id = fields.Many2one('ir.model.fields', string='Field', required=True)
    field_type = fields.Selection(related='field_id.ttype', string='Type')
    field_relation = fields.Char(related='field_id.relation')

    operation = fields.Selection(
        [('set', 'Set to'), ('append', 'Add'), ('remove', 'Remove'), ('clear', 'Clear')],
        default='set', required=True)

    value_char = fields.Char(string='Text Value')
    value_text = fields.Text(string='Long Text Value')
    value_integer = fields.Integer(string='Whole Number')
    value_float = fields.Float(string='Number')
    value_boolean = fields.Selection(
        [('true', 'Yes'), ('false', 'No')], string='Yes / No', default='true')
    value_date = fields.Date(string='Date Value')
    value_datetime = fields.Datetime(string='Date & Time Value')
    value_selection = fields.Char(
        string='Selection Value',
        help="The stored key of the option, not its label.")
    value_reference = fields.Reference(
        selection='_reference_models', string='Record',
        help="The record to point at, add, or remove.")

    @api.model
    def _reference_models(self):
        models_ = self.env['ir.model'].sudo().search([('transient', '=', False)], order='model')
        return [(m.model, m.name) for m in models_]

    @api.onchange('field_id')
    def _onchange_field_id(self):
        """Reset the operation when it no longer applies to the chosen field."""
        allowed = OPERATIONS_BY_TYPE.get(self.field_type, DEFAULT_OPERATIONS)
        if self.operation not in allowed:
            self.operation = allowed[0]

    @api.constrains('field_id', 'wizard_id')
    def _check_field_is_allowed(self):
        for line in self:
            if line.field_id not in line.allowed_field_ids:
                raise ValidationError(_(
                    "'%(field)s' is not one of the fields this bulk edit may change.")
                    % {'field': line.field_id.name})

    @api.constrains('field_id', 'operation')
    def _check_operation(self):
        for line in self:
            allowed = OPERATIONS_BY_TYPE.get(line.field_type, DEFAULT_OPERATIONS)
            if line.operation not in allowed:
                raise ValidationError(_(
                    "'%(operation)s' does not apply to a %(type)s field. "
                    "Allowed here: %(allowed)s.")
                    % {'operation': line.operation, 'type': line.field_type,
                       'allowed': ', '.join(allowed)})

    @api.constrains('field_id', 'value_selection', 'operation')
    def _check_selection_value(self):
        """A wrong selection key writes silently and breaks the record later."""
        for line in self.filtered(lambda l: l.field_type == 'selection' and l.operation == 'set'):
            model = self.env.get(line.field_id.model)
            if model is None:
                continue
            # `model and ...` would short-circuit here: an empty recordset is falsy.
            field = model._fields.get(line.field_id.name)
            if field is None:
                continue
            try:
                keys = [key for key, _label in field._description_selection(self.env)]
            except (KeyError, TypeError, ValueError):
                # A selection computed by a callable can need context we do not
                # have; skip the check rather than block a legitimate edit.
                continue
            if line.value_selection not in keys:
                raise ValidationError(_(
                    "'%(value)s' is not a valid option for %(field)s. Valid keys: %(keys)s")
                    % {'value': line.value_selection or '', 'field': line.field_id.name,
                       'keys': ', '.join(keys)})

    def _write_value(self):
        """The value (or x2many command list) to write for this line."""
        self.ensure_one()
        field_type = self.field_type

        if self.operation == 'clear':
            return [(5, 0, 0)] if field_type in X2MANY else False

        if field_type == 'many2many':
            record = self._referenced_record()
            if self.operation == 'append':
                return [(4, record.id, 0)]
            if self.operation == 'remove':
                return [(3, record.id, 0)]
            return [(6, 0, [record.id])]

        if field_type == 'many2one':
            return self._referenced_record().id

        if field_type == 'boolean':
            return self.value_boolean == 'true'
        if field_type == 'integer':
            return self.value_integer
        if field_type in ('float', 'monetary'):
            return self.value_float
        if field_type == 'date':
            return self.value_date
        if field_type == 'datetime':
            return self.value_datetime
        if field_type in ('text', 'html'):
            return self.value_text
        if field_type == 'selection':
            return self.value_selection
        return self.value_char

    def _referenced_record(self):
        self.ensure_one()
        if not self.value_reference:
            raise UserError(_("Choose a record for '%s'.") % self.field_id.field_description)
        if self.value_reference._name != self.field_relation:
            raise UserError(_(
                "%(field)s expects a %(expected)s record, but a %(given)s was chosen.")
                % {'field': self.field_id.field_description,
                   'expected': self.field_relation, 'given': self.value_reference._name})
        return self.value_reference
