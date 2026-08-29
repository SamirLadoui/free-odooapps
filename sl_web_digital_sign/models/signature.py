# -*- coding: utf-8 -*-
import base64

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Signature(models.Model):
    _name = 'sl.signature'
    _description = 'Captured Signature'
    _order = 'signed_on desc, id desc'
    _rec_name = 'signer_name'

    signer_name = fields.Char(string='Signed By', required=True)
    signer_email = fields.Char(string='Email')
    signature = fields.Image(required=True, max_width=1024, max_height=512)
    signed_on = fields.Datetime(required=True, default=fields.Datetime.now, readonly=True)
    signed_ip = fields.Char(string='IP Address', readonly=True)
    note = fields.Text(string='Purpose')

    res_model = fields.Char(string='Model', required=True, readonly=True, index=True)
    res_id = fields.Integer(string='Record ID', required=True, readonly=True, index=True)
    record_name = fields.Char(compute='_compute_record_name', store=True)
    captured_by_id = fields.Many2one(
        'res.users', string='Captured By', readonly=True,
        default=lambda self: self.env.user)

    @api.depends('res_model', 'res_id')
    def _compute_record_name(self):
        for signature in self:
            record = signature._record()
            signature.record_name = record.display_name if record else _("(deleted)")

    def _record(self):
        """The signed record, or an empty recordset if it is gone or unreadable."""
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env:
            return self.env['sl.signature'].browse()
        try:
            return self.env[self.res_model].browse(self.res_id).exists()
        except Exception:
            return self.env['sl.signature'].browse()

    @api.constrains('res_model')
    def _check_res_model(self):
        for signature in self:
            if signature.res_model not in self.env:
                raise ValidationError(
                    _("'%s' is not a model on this database.") % signature.res_model)

    @api.constrains('signer_email')
    def _check_signer_email(self):
        for signature in self.filtered('signer_email'):
            if '@' not in signature.signer_email:
                raise ValidationError(
                    _("'%s' does not look like an email address.") % signature.signer_email)

    def action_open_record(self):
        self.ensure_one()
        record = self._record()
        if not record:
            raise ValidationError(_("The signed record no longer exists."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
        }

    def _attach_to_record(self):
        """Keep a copy on the record itself, so the signature travels with it."""
        self.ensure_one()
        return self.env['ir.attachment'].create({
            'name': 'signature-%s-%s.png' % (
                self.signer_name.replace('/', '-'),
                self.signed_on.strftime('%Y%m%d-%H%M%S')),
            'datas': self.signature,
            'mimetype': 'image/png',
            'res_model': self.res_model,
            'res_id': self.res_id,
        })

    def _post_to_chatter(self):
        self.ensure_one()
        record = self._record()
        if not record or not hasattr(record, 'message_post'):
            return
        record.message_post(body=_(
            "Signed by %(name)s on %(date)s.") % {
                'name': self.signer_name,
                'date': fields.Datetime.to_string(self.signed_on)})
