# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

# A trimmed copy of what CUPS getPrinters() returns.
CUPS_QUEUES = {
    'Front_Desk': {
        'printer-info': 'Front Desk Laser',
        'printer-make-and-model': 'HP LaserJet',
        'printer-location': 'Reception',
        'device-uri': 'ipp://10.0.0.5/ipp/print',
        'printer-state': 3,
        'printer-state-message': '',
    },
    'Warehouse': {
        'printer-info': 'Warehouse Label',
        'printer-make-and-model': 'Zebra ZD420',
        'printer-location': 'Bay 2',
        'device-uri': 'usb://Zebra/ZD420',
        'printer-state': 5,
        'printer-state-message': 'Out of paper',
    },
}


@tagged('post_install', '-at_install')
class TestReportToPrinter(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.server = cls.env['sl.printing.server'].create({
            'name': 'Test CUPS', 'address': 'localhost', 'port': 631})
        cls.printer = cls.env['sl.printer'].create({
            'name': 'Office', 'system_name': 'office', 'server_id': cls.server.id})
        cls.other_printer = cls.env['sl.printer'].create({
            'name': 'Warehouse', 'system_name': 'warehouse', 'server_id': cls.server.id})
        cls.report = cls.env['ir.actions.report'].create({
            'name': 'Printer Test Report',
            'model': 'res.partner',
            'report_type': 'qweb-pdf',
            'report_name': 'sl_report_to_printer.nonexistent_template',
        })
        cls.user = cls.env['res.users'].create({
            'name': 'Printing User', 'login': 'printing_user_test',
            'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)],
        })

    def _reset(self):
        self.company.write({'printing_action': 'client', 'printing_printer_id': False})
        self.user.write({'printing_action': 'company', 'printing_printer_id': False})
        self.report.write({'printing_action': False, 'printing_printer_id': False})
        self.env['sl.printer'].search([]).write({'is_default': False})

    # -- syncing printers from CUPS ----------------------------------------

    def test_sync_creates_printers(self):
        self.server._sync_printers(CUPS_QUEUES)
        printers = self.env['sl.printer'].search([
            ('server_id', '=', self.server.id),
            ('system_name', 'in', list(CUPS_QUEUES)),
        ])
        self.assertEqual(len(printers), 2)
        front = printers.filtered(lambda p: p.system_name == 'Front_Desk')
        self.assertEqual(front.name, 'Front Desk Laser')
        self.assertEqual(front.model, 'HP LaserJet')
        self.assertEqual(front.status, 'available')

    def test_sync_maps_stopped_state(self):
        self.server._sync_printers(CUPS_QUEUES)
        warehouse = self.env['sl.printer'].search([
            ('server_id', '=', self.server.id), ('system_name', '=', 'Warehouse')])
        self.assertEqual(warehouse.status, 'error')
        self.assertEqual(warehouse.status_message, 'Out of paper')

    def test_sync_updates_rather_than_duplicates(self):
        self.server._sync_printers(CUPS_QUEUES)
        changed = dict(CUPS_QUEUES)
        changed['Front_Desk'] = dict(CUPS_QUEUES['Front_Desk'], **{'printer-state': 5})
        self.server._sync_printers(changed)
        printers = self.env['sl.printer'].search([
            ('server_id', '=', self.server.id), ('system_name', '=', 'Front_Desk')])
        self.assertEqual(len(printers), 1, "a second sync must not duplicate the queue")
        self.assertEqual(printers.status, 'error')

    def test_status_mapping(self):
        Server = self.env['sl.printing.server']
        self.assertEqual(Server._map_status(3), 'available')
        self.assertEqual(Server._map_status(4), 'printing')
        self.assertEqual(Server._map_status(5), 'error')
        self.assertEqual(Server._map_status(None), 'unknown')
        self.assertEqual(Server._map_status(99), 'unknown')

    def test_port_is_validated(self):
        for bad in (0, -1, 70000):
            with self.assertRaises(ValidationError, msg='accepted port %s' % bad):
                self.server.port = bad

    # -- which printer, and whether to print at all -------------------------

    def test_default_is_a_download(self):
        self._reset()
        behaviour, _printer = self.report._printing_behaviour(self.user)
        self.assertEqual(behaviour, 'client')

    def test_company_setting_applies(self):
        self._reset()
        self.company.write({'printing_action': 'server',
                            'printing_printer_id': self.printer.id})
        behaviour, printer = self.report._printing_behaviour(self.user)
        self.assertEqual(behaviour, 'server')
        self.assertEqual(printer, self.printer)

    def test_user_setting_beats_the_company(self):
        self._reset()
        self.company.write({'printing_action': 'server',
                            'printing_printer_id': self.printer.id})
        self.user.write({'printing_action': 'client'})
        behaviour, _printer = self.report._printing_behaviour(self.user)
        self.assertEqual(behaviour, 'client')

    def test_report_setting_beats_the_user(self):
        self._reset()
        self.user.write({'printing_action': 'client'})
        self.report.write({'printing_action': 'server',
                           'printing_printer_id': self.printer.id})
        behaviour, printer = self.report._printing_behaviour(self.user)
        self.assertEqual(behaviour, 'server')
        self.assertEqual(printer, self.printer)

    def test_user_printer_beats_the_company_printer(self):
        self._reset()
        self.company.write({'printing_action': 'server',
                            'printing_printer_id': self.printer.id})
        self.user.write({'printing_action': 'server',
                         'printing_printer_id': self.other_printer.id})
        _behaviour, printer = self.report._printing_behaviour(self.user)
        self.assertEqual(printer, self.other_printer)

    def test_report_printer_beats_everything(self):
        self._reset()
        self.company.write({'printing_action': 'server',
                            'printing_printer_id': self.printer.id})
        self.user.write({'printing_printer_id': self.printer.id})
        self.report.write({'printing_action': 'server',
                           'printing_printer_id': self.other_printer.id})
        _behaviour, printer = self.report._printing_behaviour(self.user)
        self.assertEqual(printer, self.other_printer)

    def test_global_default_printer_is_the_last_resort(self):
        self._reset()
        self.company.printing_action = 'server'
        self.other_printer.action_set_default()
        _behaviour, printer = self.report._printing_behaviour(self.user)
        self.assertEqual(printer, self.other_printer)

    def test_print_without_a_printer_falls_back_to_download(self):
        """Silently printing nowhere is worse than downloading a PDF."""
        self._reset()
        self.company.printing_action = 'server'
        behaviour, printer = self.report._printing_behaviour(self.user)
        self.assertEqual(behaviour, 'client')
        self.assertFalse(printer)

    def test_follow_company_is_not_treated_as_a_behaviour(self):
        self._reset()
        self.company.write({'printing_action': 'server',
                            'printing_printer_id': self.printer.id})
        self.user.printing_action = 'company'
        behaviour, _printer = self.report._printing_behaviour(self.user)
        self.assertEqual(behaviour, 'server')

    # -- the default printer -----------------------------------------------

    def test_only_one_default_printer(self):
        self.printer.action_set_default()
        with self.assertRaises(ValidationError):
            self.other_printer.is_default = True

    def test_set_default_clears_the_previous_one(self):
        self.printer.action_set_default()
        self.other_printer.action_set_default()
        self.assertFalse(self.printer.is_default)
        self.assertTrue(self.other_printer.is_default)

    def test_display_name_names_the_queue(self):
        self.assertEqual(self.printer.display_name, 'Office (office)')

    # -- transport ---------------------------------------------------------

    def test_printing_without_pycups_says_so(self):
        """The server has no pycups, so this is the path most users hit first."""
        from odoo.addons.sl_report_to_printer.models import printing_server
        if printing_server.cups is not None:
            self.skipTest('pycups is installed on this machine')
        with self.assertRaises(UserError) as caught:
            self.printer._print_bytes(b'%PDF-1.4\n', 'x.pdf')
        self.assertIn('pycups', str(caught.exception))
