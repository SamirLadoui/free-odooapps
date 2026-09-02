# -*- coding: utf-8 -*-
"""A number in front of every line on an invoice.

"The second line is wrong" is how people talk about an invoice on the phone,
and Odoo gives them nothing to count with. Lines get numbered on the screen
and on the printed document alike, so both sides of the call are looking at
the same numbers.

Sections and notes are not numbered. They are headings, and numbering them
would mean the fifth line on paper is not line five.
"""
from odoo import api, fields, models

# What a heading looks like, across the releases that spell it differently.
HEADINGS = ('line_section', 'line_note', 'line_subsection')


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    sl_line_number = fields.Integer(
        string='#', compute='_compute_sl_line_number',
        help='The position of this line among the invoice lines, headings '
             'aside. Worked out as it is shown rather than stored, so moving '
             'a line renumbers the rest at once.')

    @api.depends('move_id', 'sequence', 'display_type')
    def _compute_sl_line_number(self):
        for line in self:
            line.sl_line_number = 0
        for move in self.move_id:
            number = 0
            for line in move._sl_numbered_lines():
                number += 1
                if line in self:
                    line.sl_line_number = number


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _sl_numbered_lines(self):
        """The lines that get a number, in the order they are shown."""
        self.ensure_one()
        lines = self.invoice_line_ids.filtered(
            lambda line: line.display_type not in HEADINGS)
        return lines.sorted(lambda line: (line.sequence, line.id))
