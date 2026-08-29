# -*- coding: utf-8 -*-
from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request


class SlAttachmentPreview(http.Controller):

    @http.route('/sl_attachment_preview/<int:attachment_id>', type='http',
                auth='user', sitemap=False)
    def preview(self, attachment_id, **kw):
        """Render one attachment on a page that can display it.

        No sudo anywhere. The record is read as the logged-in user, and read()
        applies the ir.attachment access rules on every supported version, so a
        user who may not see the attachment gets a 404 rather than its contents.
        """
        # exists() first: read() on a missing id returns [] rather than raising on
        # some versions, and the MissingError then escapes from further down.
        # not_found() *returns* the exception, so it has to be raised explicitly -
        # returning it yields a 400 instead of a 404.
        attachment = request.env['ir.attachment'].browse(attachment_id).exists()
        if not attachment:
            raise request.not_found()
        try:
            attachment.read(['name'])
        except AccessError:
            # 404 rather than 403: do not confirm that the attachment exists.
            raise request.not_found()

        previous, following = attachment._preview_siblings()
        return request.render('sl_attachment_preview.preview_page', {
            'attachment': attachment,
            'kind': attachment.preview_kind,
            'text': attachment._preview_text() if attachment.preview_kind == 'text' else '',
            'previous': previous,
            'next': following,
        })
