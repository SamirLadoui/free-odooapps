# -*- coding: utf-8 -*-
import logging
import os
import tempfile

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class Printer(models.Model):
    _name = 'sl.printer'
    _description = 'Printer'
    _order = 'name'

    name = fields.Char(required=True)
    system_name = fields.Char(
        string='Queue Name', required=True,
        help="The queue name on the print server, as CUPS knows it.")
    server_id = fields.Many2one(
        'sl.printing.server', string='Print Server', required=True, ondelete='cascade')
    active = fields.Boolean(default=True)

    model = fields.Char(string='Make and Model', readonly=True)
    location = fields.Char(readonly=True)
    uri = fields.Char(string='Device URI', readonly=True)
    status = fields.Selection(
        [('available', 'Available'), ('printing', 'Printing'),
         ('error', 'Stopped'), ('unknown', 'Unknown')],
        default='unknown', readonly=True)
    status_message = fields.Char(readonly=True)
    last_seen = fields.Datetime(readonly=True)

    is_default = fields.Boolean(
        string='Default Printer',
        help="Used when nothing more specific is set on the report or the user.")

    @api.constrains('is_default')
    def _check_single_default(self):
        """Two defaults would make 'the default printer' meaningless."""
        for printer in self.filtered('is_default'):
            clash = self.search([
                ('id', '!=', printer.id), ('is_default', '=', True),
            ], limit=1)
            if clash:
                raise ValidationError(_(
                    "%s is already the default printer. Unset it first.")
                    % clash.display_name)

    @api.depends('name', 'server_id')
    def _compute_display_name(self):
        for printer in self:
            printer.display_name = '%s (%s)' % (printer.name, printer.system_name)

    def action_set_default(self):
        self.ensure_one()
        self.search([('is_default', '=', True)]).write({'is_default': False})
        self.is_default = True
        return True

    def action_update_status(self):
        for printer in self:
            printer.server_id.action_update_printers()
        return True

    def action_print_test_page(self):
        self.ensure_one()
        self._print_bytes(
            b'%PDF-1.4\n% Odoo printer test page\n',
            'odoo_test_page.pdf', title=_("Odoo test page"))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Test page sent"),
                'message': _("Sent to %s.") % self.display_name,
                'type': 'success', 'sticky': False,
            },
        }

    def _print_bytes(self, content, filename, title=None, copies=1):
        """Hand a document to CUPS.

        Everything that decides *whether* and *where* to print lives in
        ir.actions.report; this is only the transport.
        """
        self.ensure_one()
        connection = self.server_id._connection()
        handle, path = tempfile.mkstemp(suffix='_%s' % filename)
        try:
            with os.fdopen(handle, 'wb') as stream:
                stream.write(content)
            options = {'copies': str(max(1, copies))}
            connection.printFile(self.system_name, path, title or filename, options)
            _logger.info("Sent %s to printer %s", filename, self.system_name)
        except Exception as err:
            raise UserError(_("Could not print to %(printer)s: %(err)s")
                            % {'printer': self.display_name, 'err': err})
        finally:
            if os.path.exists(path):
                os.remove(path)
        return True
