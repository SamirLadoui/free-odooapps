# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

# Browsers render these inline; anything else gets the "download instead" card.
KIND_BY_PREFIX = (
    ('image/', 'image'),
    ('video/', 'video'),
    ('audio/', 'audio'),
    ('text/', 'text'),
)
KIND_BY_MIMETYPE = {
    'application/pdf': 'pdf',
    'application/json': 'text',
    'application/xml': 'text',
    'application/javascript': 'text',
    'application/x-javascript': 'text',
    'application/x-sh': 'text',
    'application/sql': 'text',
    'application/x-yaml': 'text',
}
# Text previews are streamed into a <pre>; past this the page stops being useful
# and starts being a memory problem.
TEXT_PREVIEW_LIMIT = 200 * 1024


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    preview_kind = fields.Selection(
        [('image', 'Image'), ('pdf', 'PDF'), ('text', 'Text'),
         ('video', 'Video'), ('audio', 'Audio'), ('none', 'Not previewable')],
        compute='_compute_preview_kind',
        help="How this attachment is rendered on the preview page.")

    @api.depends('mimetype')
    def _compute_preview_kind(self):
        for attachment in self:
            attachment.preview_kind = self._preview_kind_for(attachment.mimetype)

    @api.model
    def _preview_kind_for(self, mimetype):
        mimetype = (mimetype or '').split(';')[0].strip().lower()
        if mimetype in KIND_BY_MIMETYPE:
            return KIND_BY_MIMETYPE[mimetype]
        for prefix, kind in KIND_BY_PREFIX:
            if mimetype.startswith(prefix):
                return kind
        return 'none'

    def action_preview(self):
        """Open the attachment on the preview page, in a new browser tab."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/sl_attachment_preview/%d' % self.id,
            'target': 'new',
        }

    # -- used by the preview page ------------------------------------------

    def _preview_text(self):
        """Decoded text for a text/* attachment, truncated to a sane size."""
        self.ensure_one()
        data = self.raw or b''
        truncated = len(data) > TEXT_PREVIEW_LIMIT
        text = data[:TEXT_PREVIEW_LIMIT].decode('utf-8', errors='replace')
        if truncated:
            text += _("\n\n--- truncated, download the file to see the rest ---")
        return text

    def _preview_siblings(self):
        """The other attachments of the same record, for prev/next navigation.

        Returns (previous, next), either of which may be empty.
        """
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return self.browse(), self.browse()
        siblings = self.search([
            ('res_model', '=', self.res_model),
            ('res_id', '=', self.res_id),
        ], order='id')
        ids = siblings.ids
        if self.id not in ids:
            return self.browse(), self.browse()
        index = ids.index(self.id)
        return (self.browse(ids[index - 1]) if index else self.browse(),
                self.browse(ids[index + 1]) if index + 1 < len(ids) else self.browse())
