# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.http import request


class SignatureWizard(models.TransientModel):
    _name = 'sl.signature.wizard'
    _description = 'Sign Records'

    config_id = fields.Many2one('sl.signature.config', required=True, ondelete='cascade')
    model_name = fields.Char(related='config_id.model_name')
    record_count = fields.Integer(compute='_compute_record_count')

    signer_name = fields.Char(
        string='Signed By', required=True,
        default=lambda self: self.env.user.name)
    signer_email = fields.Char(
        string='Email', default=lambda self: self.env.user.email)
    signature = fields.Image(required=True, max_width=1024, max_height=512)
    note = fields.Text(string='Purpose')

    def _target_ids(self):
        return self.env.context.get('active_ids') or []

    def _compute_record_count(self):
        count = len(self._target_ids())
        for wizard in self:
            wizard.record_count = count

    def _client_ip(self):
        """Best-effort. Recorded for the audit trail, never trusted for access."""
        try:
            return request.httprequest.remote_addr if request else False
        except Exception:
            return False

    def action_sign(self):
        self.ensure_one()
        model_name = self.config_id.model_name
        records = self.env[model_name].browse(self._target_ids()).exists()
        if not records:
            raise UserError(_("Nothing selected. Pick the records to sign first."))

        # Signing changes what a record means, so require write access on it.
        try:
            records.check_access_rights('write')
            records.check_access_rule('write')
        except AccessError:
            raise UserError(_(
                "You do not have permission to sign these %s records.") % model_name)

        ip = self._client_ip()
        signatures = self.env['sl.signature'].create([{
            'signer_name': self.signer_name,
            'signer_email': self.signer_email,
            'signature': self.signature,
            'note': self.note,
            'signed_ip': ip,
            'res_model': model_name,
            'res_id': record.id,
        } for record in records])

        for signature in signatures:
            signature._attach_to_record()
            signature._post_to_chatter()

        return {'type': 'ir.actions.act_window_close'}
