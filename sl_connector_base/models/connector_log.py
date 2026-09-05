# -*- coding: utf-8 -*-
"""What the integration did, and what it could not do.

An integration that fails silently is worse than one that does not run: the
orders stop arriving and nobody notices until a customer asks where their
parcel is. Every run writes a line here, whether it worked or not, and the
failures carry the message the other side actually sent rather than a
paraphrase of it.

The log is written, never rewritten. A record of what happened that somebody
can edit afterwards is not a record of what happened.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

STATES = [
    ('done', 'Done'),
    ('skipped', 'Nothing To Do'),
    ('error', 'Failed'),
]


class ConnectorLog(models.Model):
    _name = 'sl.connector.log'
    _description = 'Synchronisation Log'
    _order = 'create_date desc, id desc'
    _rec_name = 'operation'

    backend_model = fields.Char(required=True, index=True)
    backend_id = fields.Integer(required=True, index=True)
    backend_name = fields.Char()

    operation = fields.Char(
        required=True, index=True,
        help='What was being done, in the words of the connector that did it.')
    state = fields.Selection(STATES, required=True, default='done', index=True)
    message = fields.Text(
        help='What the other side said, kept as it said it.')

    model_name = fields.Char(string='Odoo Model')
    res_id = fields.Integer(string='Odoo Record')
    external_id = fields.Char(index=True)
    duration = fields.Float(string='Seconds')

    @api.model
    def _record_run(self, backend, operation, state='done', message=None,
                    record=None, external_id=None, duration=0.0):
        return self.sudo().create({
            'backend_model': backend._name,
            'backend_id': backend.id,
            'backend_name': backend.display_name,
            'operation': operation,
            'state': state,
            'message': message and str(message)[:8000] or False,
            'model_name': record._name if record else False,
            'res_id': record.id if record else False,
            'external_id': external_id and str(external_id) or False,
            'duration': duration,
        })

    def write(self, values):
        raise UserError(_(
            'The synchronisation log is a record of what happened. It cannot '
            'be edited afterwards.'))

    @api.model
    def _prune(self, days=90):
        """Housekeeping: a busy store writes a great many of these."""
        limit = fields.Datetime.subtract(fields.Datetime.now(), days=days)
        old = self.sudo().search([('create_date', '<', limit)])
        count = len(old)
        old.unlink()
        return count
