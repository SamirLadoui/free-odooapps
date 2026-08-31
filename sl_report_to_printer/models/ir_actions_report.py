# -*- coding: utf-8 -*-
import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    printing_action = fields.Selection(
        [('client', 'Download the PDF'), ('server', 'Send to a printer')],
        string='Print Behaviour',
        help="Leave empty to follow the user's own setting.")
    printing_printer_id = fields.Many2one(
        'sl.printer', string='Printer',
        help="Leave empty to use the user's printer, then the company default.")
    printing_copies = fields.Integer(string='Copies', default=1)

    # -- the decision ------------------------------------------------------

    def _printing_behaviour(self, user=None):
        """Decide how and where this report prints.

        Most specific wins: the report, then the user, then the company. Returns
        ``(behaviour, printer)`` where behaviour is 'client' or 'server'.
        A 'server' behaviour with no printer anywhere falls back to 'client',
        because silently printing nowhere is worse than downloading a PDF.
        """
        self.ensure_one()
        user = user or self.env.user
        company = user.company_id or self.env.company

        if self.printing_action:
            behaviour = self.printing_action
        elif user.printing_action and user.printing_action != 'company':
            behaviour = user.printing_action
        else:
            behaviour = company.printing_action or 'client'

        printer = (self.printing_printer_id
                   or user.printing_printer_id
                   or company.printing_printer_id
                   or self.env['sl.printer'].search([('is_default', '=', True)], limit=1))

        if behaviour == 'server' and not printer:
            _logger.info(
                "Report %s asked to print but no printer is configured; "
                "falling back to a download.", self.report_name)
            behaviour = 'client'
        return behaviour, printer

    # -- the hook ----------------------------------------------------------

    def report_action(self, docids, data=None, config=True):
        """Send to the printer instead of the browser when that is the policy."""
        action = super().report_action(docids, data=data, config=config)
        if not self or self.report_type not in ('qweb-pdf',):
            return action

        behaviour, printer = self._printing_behaviour()
        if behaviour != 'server' or not printer:
            return action

        res_ids = docids
        if hasattr(docids, 'ids'):
            res_ids = docids.ids
        elif isinstance(res_ids, int):
            res_ids = [res_ids]
        if not res_ids:
            return action

        content, _ext = self._render_qweb_pdf(self.report_name, res_ids, data=data)
        printer._print_bytes(
            content, '%s.pdf' % self.report_name.replace('.', '_'),
            title=self.name, copies=self.printing_copies or 1)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Sent to printer"),
                'message': _("%(report)s sent to %(printer)s.") % {
                    'report': self.name, 'printer': printer.display_name},
                'type': 'success', 'sticky': False,
            },
        }
