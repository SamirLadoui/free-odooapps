# -*- coding: utf-8 -*-
from odoo import api, models


class LabelSheetReport(models.AbstractModel):
    _name = 'report.sl_mass_label.report_label_sheet'
    _description = 'Label Sheet Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env['sl.label.wizard'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'sl.label.wizard',
            'docs': wizards,
            'pages_by_wizard': {w.id: w._label_pages() for w in wizards},
        }
