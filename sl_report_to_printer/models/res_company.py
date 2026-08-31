# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    printing_action = fields.Selection(
        [('client', 'Download the PDF'), ('server', 'Send to a printer')],
        string='Default Print Behaviour', default='client', required=True,
        help="What happens when a report is printed and nothing more specific "
             "is set on the report or the user.")
    printing_printer_id = fields.Many2one(
        'sl.printer', string='Default Printer',
        help="Used when neither the report nor the user names one.")
