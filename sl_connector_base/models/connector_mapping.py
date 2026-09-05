# -*- coding: utf-8 -*-
"""Which Odoo record is which record over there.

Every integration needs this table and every integration writes it again.
Without it the second sync creates a second copy of everything, which is the
failure people actually hit: the orders imported fine on Monday and there were
two of each on Tuesday.

The link is stored rather than guessed at from a name or a reference, because
names change and references get edited, and an integration that re-identifies
records by matching text will eventually match the wrong ones.

A backend is referred to by model name and id rather than by a Many2one, so
this table can serve a Shopify backend, a Salla backend and something written
in-house next year without knowing anything about any of them.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ConnectorMapping(models.Model):
    _name = 'sl.connector.mapping'
    _description = 'External Record Mapping'
    _order = 'id desc'
    _rec_name = 'external_id'

    backend_model = fields.Char(required=True, index=True)
    backend_id = fields.Integer(required=True, index=True)

    model_name = fields.Char(
        string='Odoo Model', required=True, index=True)
    res_id = fields.Integer(string='Odoo Record', required=True, index=True)
    external_id = fields.Char(required=True, index=True)

    external_written = fields.Datetime(
        help='When the record was last changed on the other side, as that '
             'side reported it. Used to skip work that is already done.')
    synced_on = fields.Datetime(default=fields.Datetime.now)

    _sql_constraints = [
        ('external_uniq',
         'unique(backend_model, backend_id, model_name, external_id)',
         'That external record is already linked to something here.'),
        ('odoo_uniq',
         'unique(backend_model, backend_id, model_name, res_id)',
         'That Odoo record is already linked to something over there.'),
    ]

    # -- reading -----------------------------------------------------------

    @api.model
    def _find(self, backend, model_name, external_id=None, res_id=None):
        domain = [('backend_model', '=', backend._name),
                  ('backend_id', '=', backend.id),
                  ('model_name', '=', model_name)]
        if external_id is not None:
            domain.append(('external_id', '=', str(external_id)))
        if res_id is not None:
            domain.append(('res_id', '=', res_id))
        return self.sudo().search(domain, limit=1)

    @api.model
    def _record(self, backend, model_name, external_id):
        """The Odoo record this external id stands for, or an empty one.

        Checked for existence: a mapping outlives the record it points at if
        somebody deletes the record, and handing back a stale id would only
        move the error somewhere less obvious.
        """
        mapping = self._find(backend, model_name, external_id=external_id)
        if not mapping:
            return self.env[model_name].browse()
        record = self.env[model_name].browse(mapping.res_id).exists()
        if not record:
            mapping.sudo().unlink()
        return record

    @api.model
    def _external_id(self, backend, record):
        record.ensure_one()
        mapping = self._find(backend, record._name, res_id=record.id)
        return mapping.external_id or False

    # -- writing -----------------------------------------------------------

    @api.model
    def _bind(self, backend, record, external_id, external_written=None):
        """Record that these two are the same thing.

        Binding again is not an error: a re-import of the same order should
        refresh what is known about it rather than fail or duplicate it.
        """
        record.ensure_one()
        if not external_id:
            raise UserError(_('An external record with no id cannot be bound.'))
        values = {
            'backend_model': backend._name,
            'backend_id': backend.id,
            'model_name': record._name,
            'res_id': record.id,
            'external_id': str(external_id),
            'synced_on': fields.Datetime.now(),
        }
        if external_written:
            values['external_written'] = external_written
        existing = self._find(backend, record._name, external_id=external_id) \
            or self._find(backend, record._name, res_id=record.id)
        if existing:
            existing.sudo().write(values)
            return existing
        return self.sudo().create(values)

    @api.model
    def _is_newer(self, backend, model_name, external_id, external_written):
        """Whether the other side has changed since we last looked.

        The cheapest work is the work not done: a store with forty thousand
        products cannot be walked field by field on every run.
        """
        if not external_written:
            return True
        mapping = self._find(backend, model_name, external_id=external_id)
        if not mapping or not mapping.external_written:
            return True
        return external_written > mapping.external_written
