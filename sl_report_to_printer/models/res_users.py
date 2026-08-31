# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    printing_action = fields.Selection(
        [('company', 'Follow the company setting'),
         ('client', 'Download the PDF'),
         ('server', 'Send to my printer')],
        string='Print Behaviour', default='company', required=True)
    printing_printer_id = fields.Many2one('sl.printer', string='My Printer')

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['printing_action', 'printing_printer_id']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['printing_action', 'printing_printer_id']
