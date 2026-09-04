# -*- coding: utf-8 -*-
"""A word across the page, so a draft is never mistaken for the real thing.

A quotation printed for discussion and a quotation that has been accepted look
identical on paper. So do a paid invoice and an unpaid one. People find out
which they were holding after they have acted on it.

A rule says: for this kind of document, in this state, print this word behind
the text. It is drawn as an image tiled behind the page rather than a line of
text dropped into the layout, so it cannot push anything down the page or
break a table across a page boundary.
"""
import base64
from html import escape

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval

# One tile of the repeating background. Big enough to read, small enough that
# a short page still gets a whole one.
TILE = (420, 300)


class WatermarkRule(models.Model):
    _name = 'sl.watermark.rule'
    _description = 'Watermark Rule'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(
        default=10, help='The first rule that fits a document is the one used.')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    model_id = fields.Many2one(
        'ir.model', string='Applies To', required=True, ondelete='cascade')
    model_name = fields.Char(related='model_id.model', store=True, readonly=True)
    domain = fields.Char(
        default='[]', required=True,
        help='Which documents of that kind. Leave it as [] for all of them.')

    text = fields.Char(
        required=True, default='DRAFT',
        help='What to print across the page.')
    color = fields.Char(
        default='#d0021b', required=True,
        help='A CSS colour: a name, or #rrggbb.')
    opacity = fields.Float(
        default=0.12, required=True,
        help='How faint. Low enough to read the document through it.')
    angle = fields.Integer(
        default=-30, required=True, help='Degrees. Negative slopes upwards.')
    font_size = fields.Integer(default=48, required=True)

    @api.constrains('opacity')
    def _check_opacity(self):
        for rule in self:
            if not 0 < rule.opacity <= 1:
                raise ValidationError(_(
                    'Opacity is between 0 and 1. A watermark at 0 is invisible '
                    'and one at 1 hides the document.'))

    @api.constrains('domain')
    def _check_domain(self):
        for rule in self:
            try:
                model = self.env[rule.model_name]
                model.search_count(safe_eval(rule.domain))
            except Exception as error:
                raise ValidationError(_(
                    'That domain does not work against %(model)s: %(error)s',
                    model=rule.model_id.display_name, error=error))

    # -- which rule, if any ------------------------------------------------

    @api.model
    def _rule_for(self, record):
        """The first rule that fits this document, or nothing."""
        if not record or len(record) != 1:
            return self.browse()
        company = record.company_id if 'company_id' in record._fields else None
        domain = [('model_name', '=', record._name)]
        if company:
            domain += ['|', ('company_id', '=', company.id),
                       ('company_id', '=', False)]
        for rule in self.sudo().search(domain):
            try:
                if record.filtered_domain(safe_eval(rule.domain)):
                    return rule
            except Exception:
                # A rule nobody can evaluate must not stop the document
                # printing; printing without a watermark is the safe failure.
                continue
        return self.browse()

    # -- what it looks like ------------------------------------------------

    def _tile(self):
        """One tile of the watermark, as an SVG data URI."""
        self.ensure_one()
        width, height = TILE
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="%(width)d" height="%(height)d">'
            '<text x="%(cx)d" y="%(cy)d" text-anchor="middle" '
            'dominant-baseline="middle" '
            'transform="rotate(%(angle)d %(cx)d %(cy)d)" '
            'font-family="Helvetica, Arial, sans-serif" '
            'font-size="%(size)d" font-weight="bold" '
            'fill="%(color)s" fill-opacity="%(opacity)s">%(text)s</text>'
            '</svg>'
        ) % {
            'width': width, 'height': height,
            'cx': width // 2, 'cy': height // 2,
            'angle': self.angle, 'size': self.font_size,
            'color': escape(self.color or '#d0021b', quote=True),
            'opacity': round(self.opacity, 3),
            'text': escape(self.text or ''),
        }
        encoded = base64.b64encode(svg.encode()).decode()
        return 'data:image/svg+xml;base64,%s' % encoded

    @api.model
    def _css_for(self, record):
        """The stylesheet that puts the watermark behind this document.

        Empty when no rule fits, so a report with no watermark carries no
        trace of this module at all.
        """
        rule = self._rule_for(record)
        if not rule:
            return ''
        return (
            '.article, .page { '
            'background-image: url(%s); '
            'background-repeat: repeat; '
            'background-position: center top; }'
        ) % rule._tile()
