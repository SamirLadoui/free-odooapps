# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

try:
    import cups
except ImportError:  # optional: only needed to actually reach a print server
    cups = None

CUPS_MISSING = _(
    "Printing needs the 'pycups' Python package on the Odoo server. "
    "Install it with: pip install pycups")


class PrintingServer(models.Model):
    _name = 'sl.printing.server'
    _description = 'Print Server (CUPS)'
    _order = 'name'

    name = fields.Char(required=True, default='Local CUPS')
    address = fields.Char(required=True, default='localhost')
    port = fields.Integer(required=True, default=631)
    active = fields.Boolean(default=True)
    printer_ids = fields.One2many('sl.printer', 'server_id', string='Printers')
    printer_count = fields.Integer(compute='_compute_printer_count')

    @api.depends('printer_ids')
    def _compute_printer_count(self):
        for server in self:
            server.printer_count = len(server.printer_ids)

    @api.constrains('port')
    def _check_port(self):
        for server in self:
            if not 1 <= server.port <= 65535:
                raise ValidationError(_("A port must be between 1 and 65535."))

    def _connection(self):
        """A live CUPS connection, or a clear error explaining what is missing."""
        self.ensure_one()
        if cups is None:
            raise UserError(CUPS_MISSING)
        try:
            cups.setServer(self.address)
            cups.setPort(self.port)
            return cups.Connection()
        except Exception as err:
            raise UserError(_("Cannot reach the print server at %(address)s:%(port)s - %(err)s")
                            % {'address': self.address, 'port': self.port, 'err': err})

    def action_test_connection(self):
        self.ensure_one()
        connection = self._connection()
        count = len(connection.getPrinters())
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Connected"),
                'message': _("%(count)s printer(s) available on %(name)s.")
                           % {'count': count, 'name': self.name},
                'type': 'success', 'sticky': False,
            },
        }

    def action_update_printers(self):
        """Create or refresh a printer record for every queue on the server."""
        for server in self:
            server._sync_printers(server._connection().getPrinters())
        return True

    def _sync_printers(self, queues):
        """Split from the CUPS call so the mapping can be tested offline."""
        self.ensure_one()
        Printer = self.env['sl.printer']
        for system_name, info in (queues or {}).items():
            printer = Printer.search([
                ('server_id', '=', self.id),
                ('system_name', '=', system_name),
            ], limit=1)
            values = {
                'name': info.get('printer-info') or system_name,
                'system_name': system_name,
                'server_id': self.id,
                'model': info.get('printer-make-and-model') or '',
                'location': info.get('printer-location') or '',
                'uri': info.get('device-uri') or '',
                'status': self._map_status(info.get('printer-state')),
                'status_message': info.get('printer-state-message') or '',
                'last_seen': fields.Datetime.now(),
            }
            if printer:
                printer.write(values)
            else:
                Printer.create(values)
        return True

    @api.model
    def _map_status(self, state):
        """CUPS printer-state: 3 idle, 4 printing, 5 stopped."""
        return {3: 'available', 4: 'printing', 5: 'error'}.get(state, 'unknown')
