# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class DataCleanup(models.TransientModel):
    _name = 'sl.data.cleanup'
    _description = 'Remove Transactional Data'

    remove_sales = fields.Boolean(string='Sales Orders')
    remove_purchases = fields.Boolean(string='Purchase Orders')
    remove_invoices = fields.Boolean(
        string='Invoices and Journal Entries',
        help='Posted entries are set back to draft before being removed.')
    remove_stock = fields.Boolean(string='Transfers and Stock Moves')
    remove_manufacturing = fields.Boolean(string='Manufacturing Orders')
    remove_pos = fields.Boolean(string='Point of Sale Orders')
    remove_leads = fields.Boolean(string='Leads and Opportunities')
    remove_products = fields.Boolean(string='Products')
    remove_partners = fields.Boolean(
        string='Contacts',
        help='Contacts attached to a user, and your own companies, are kept.')

    confirmation = fields.Char(
        string='Type the database name to confirm',
        help='This is not undoable. The database name has to be typed in full '
             'before anything is removed.')
    database_name = fields.Char(
        string='Database', compute='_compute_database_name')
    preview = fields.Text(string='What Will Be Removed', readonly=True)

    def _compute_database_name(self):
        for wizard in self:
            wizard.database_name = self.env.cr.dbname

    # -- what each switch covers ------------------------------------------

    def _categories(self):
        """(field, label, model, domain) for each switch, in the order they
        have to be removed: documents before the records they point at."""
        return [
            ('remove_pos', _('Point of Sale Orders'), 'pos.order', []),
            ('remove_manufacturing', _('Manufacturing Orders'), 'mrp.production', []),
            ('remove_sales', _('Sales Orders'), 'sale.order', []),
            ('remove_purchases', _('Purchase Orders'), 'purchase.order', []),
            ('remove_invoices', _('Invoices and Journal Entries'), 'account.move', []),
            ('remove_stock', _('Transfers'), 'stock.picking', []),
            ('remove_stock', _('Stock Moves'), 'stock.move', []),
            ('remove_leads', _('Leads and Opportunities'), 'crm.lead', []),
            ('remove_products', _('Products'), 'product.template', []),
            ('remove_partners', _('Contacts'), 'res.partner',
             [('user_ids', '=', False), ('id', 'not in', 'PROTECTED')]),
        ]

    def _protected_partner_ids(self):
        """Contacts that must survive: your own companies and their contacts.

        Removing these breaks the database rather than cleaning it - every
        company needs its partner, and a user needs theirs to log in.
        """
        companies = self.env['res.company'].sudo().search([])
        partners = companies.mapped('partner_id')
        partners |= self.env['res.users'].sudo().search([]).mapped('partner_id')
        return partners.ids

    def _records_for(self, model_name, domain):
        """The records a category would remove, or an empty recordset when the
        model is not installed."""
        if model_name not in self.env:
            return None
        domain = [
            (f, o, self._protected_partner_ids() if v == 'PROTECTED' else v)
            for f, o, v in domain
        ]
        return self.env[model_name].sudo().search(domain)

    # -- counting before doing --------------------------------------------

    def action_preview(self):
        """Count what each switch would remove, without removing anything."""
        self.ensure_one()
        self._check_allowed()
        lines = []
        for field, label, model_name, domain in self._categories():
            if not self[field]:
                continue
            records = self._records_for(model_name, domain)
            if records is None:
                lines.append(_('%s: not installed, skipped') % label)
            else:
                lines.append(_('%(label)s: %(count)s to remove') % {
                    'label': label, 'count': len(records)})
        self.preview = '\n'.join(lines) or _('Nothing selected.')
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # -- doing it ----------------------------------------------------------

    def _check_allowed(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Only a settings administrator can remove data.'))

    def _prepare_for_unlink(self, records):
        """Some documents refuse to be deleted until they are cancelled or set
        back to draft. Do that first rather than letting unlink raise."""
        if not records:
            return
        model = records._name
        if model == 'account.move':
            posted = records.filtered(lambda m: m.state == 'posted')
            if posted:
                posted.button_draft()
            records.filtered(lambda m: m.state != 'draft').button_cancel()
        elif model in ('sale.order', 'purchase.order'):
            done = records.filtered(lambda o: o.state not in ('draft', 'cancel'))
            if done:
                done.action_cancel() if hasattr(done, 'action_cancel') \
                    else done.button_cancel()
        elif model == 'stock.picking':
            records.filtered(lambda p: p.state != 'cancel').action_cancel()
        elif model == 'mrp.production':
            records.filtered(lambda p: p.state != 'cancel').action_cancel()
        elif model == 'pos.order':
            records.filtered(lambda o: o.state == 'paid').write({'state': 'cancel'})

    def action_remove(self):
        self.ensure_one()
        self._check_allowed()

        if (self.confirmation or '').strip() != self.env.cr.dbname:
            raise UserError(_(
                'Type the database name "%s" to confirm. Nothing has been '
                'removed.', self.env.cr.dbname))

        selected = [c for c in self._categories() if self[c[0]]]
        if not selected:
            raise UserError(_('Nothing is selected to remove.'))

        removed = {}
        for field, label, model_name, domain in selected:
            records = self._records_for(model_name, domain)
            if not records:
                continue
            count = len(records)
            self._prepare_for_unlink(records)
            records.unlink()
            removed[label] = removed.get(label, 0) + count
            _logger.warning(
                '%s removed %s %s records', self.env.user.login, count, model_name)

        self.preview = '\n'.join(
            _('%(label)s: %(count)s removed') % {'label': k, 'count': v}
            for k, v in removed.items()) or _('Nothing was removed.')
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
