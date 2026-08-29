# -*- coding: utf-8 -*-
import base64

from odoo.tests import HttpCase, tagged

PIXEL = base64.b64encode(base64.b64decode(
    b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='))


@tagged('post_install', '-at_install')
class TestAttachmentPreview(HttpCase):

    def _attachment(self, name, mimetype, raw=b'hello'):
        return self.env['ir.attachment'].create({
            'name': name,
            'mimetype': mimetype,
            'datas': base64.b64encode(raw),
        })

    def test_kind_detection(self):
        cases = {
            'image/png': 'image', 'image/jpeg': 'image', 'image/svg+xml': 'image',
            'application/pdf': 'pdf',
            'text/plain': 'text', 'text/csv': 'text',
            'application/json': 'text', 'application/xml': 'text',
            'video/mp4': 'video', 'audio/mpeg': 'audio',
            'application/octet-stream': 'none', 'application/zip': 'none',
            '': 'none', False: 'none',
        }
        model = self.env['ir.attachment']
        for mimetype, expected in cases.items():
            self.assertEqual(model._preview_kind_for(mimetype), expected,
                             'wrong kind for %r' % mimetype)

    def test_kind_ignores_charset_and_case(self):
        model = self.env['ir.attachment']
        self.assertEqual(model._preview_kind_for('TEXT/PLAIN; charset=utf-8'), 'text')
        self.assertEqual(model._preview_kind_for('Application/PDF'), 'pdf')

    def test_text_preview_is_truncated(self):
        from odoo.addons.sl_attachment_preview.models.ir_attachment import TEXT_PREVIEW_LIMIT
        attachment = self._attachment('big.txt', 'text/plain', b'x' * (TEXT_PREVIEW_LIMIT + 5000))
        text = attachment._preview_text()
        self.assertIn('truncated', text)
        self.assertLess(len(text), TEXT_PREVIEW_LIMIT + 200)

    def test_text_preview_survives_bad_bytes(self):
        """A .log full of latin-1 must render, not raise."""
        attachment = self._attachment('weird.txt', 'text/plain', b'caf\xe9 \xff\xfe')
        self.assertIn('caf', attachment._preview_text())

    def test_siblings_walk_the_same_record(self):
        partner = self.env['res.partner'].create({'name': 'Preview Test'})
        made = [self.env['ir.attachment'].create({
            'name': 'file%d.txt' % i, 'mimetype': 'text/plain',
            'datas': base64.b64encode(b'x'),
            'res_model': 'res.partner', 'res_id': partner.id,
        }) for i in range(3)]

        previous, following = made[1]._preview_siblings()
        self.assertEqual(previous, made[0])
        self.assertEqual(following, made[2])

        previous, following = made[0]._preview_siblings()
        self.assertFalse(previous, "the first attachment has no previous")
        self.assertEqual(following, made[1])

        previous, following = made[2]._preview_siblings()
        self.assertEqual(previous, made[1])
        self.assertFalse(following, "the last attachment has no next")

    def test_siblings_empty_when_unattached(self):
        loose = self._attachment('loose.txt', 'text/plain')
        self.assertEqual(loose._preview_siblings(), (loose.browse(), loose.browse()))

    def test_action_preview_opens_the_page(self):
        attachment = self._attachment('doc.pdf', 'application/pdf')
        action = attachment.action_preview()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertEqual(action['url'], '/sl_attachment_preview/%d' % attachment.id)

    def test_page_renders_each_kind(self):
        self.authenticate('admin', 'admin')
        for name, mimetype, marker in (
            ('shot.png', 'image/png', 'sl_preview_image'),
            ('doc.pdf', 'application/pdf', 'sl_preview_frame'),
            ('notes.txt', 'text/plain', 'sl_preview_text'),
            ('clip.mp4', 'video/mp4', '<video'),
            ('tune.mp3', 'audio/mpeg', '<audio'),
            ('archive.zip', 'application/zip', 'No preview for this file type'),
        ):
            attachment = self._attachment(name, mimetype)
            self.env.cr.flush()
            response = self.url_open('/sl_attachment_preview/%d' % attachment.id)
            self.assertEqual(response.status_code, 200, name)
            self.assertIn(marker, response.text, name)

    def test_text_content_reaches_the_page(self):
        self.authenticate('admin', 'admin')
        attachment = self._attachment('notes.txt', 'text/plain', b'the quick brown fox')
        self.env.cr.flush()
        response = self.url_open('/sl_attachment_preview/%d' % attachment.id)
        self.assertIn('the quick brown fox', response.text)

    def test_missing_attachment_is_not_found(self):
        self.authenticate('admin', 'admin')
        self.assertEqual(self.url_open('/sl_attachment_preview/999999999').status_code, 404)

    def test_route_requires_login(self):
        """Anonymous users must never reach an attachment."""
        attachment = self._attachment('private.txt', 'text/plain', b'secret')
        self.env.cr.flush()
        response = self.url_open('/sl_attachment_preview/%d' % attachment.id,
                                 allow_redirects=False)
        self.assertIn(response.status_code, (302, 303),
                      "an anonymous request should be bounced to the login page")
        self.assertNotIn('secret', response.text)
