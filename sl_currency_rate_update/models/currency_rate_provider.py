# -*- coding: utf-8 -*-
import logging
from datetime import date

import requests
from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

TIMEOUT = 30

# The European Central Bank publishes a free daily feed, quoted against EUR.
ECB_DAILY = 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml'
ECB_NS = {
    'gesmes': 'http://www.gesmes.org/xml/2002-08-01',
    'ecb': 'http://www.ecb.int/vocabulary/2002-08-01/eurofxref',
}
# Frankfurter is a free JSON wrapper over the same ECB data, and lets the base
# currency be chosen server-side.
FRANKFURTER = 'https://api.frankfurter.app/latest'


class CurrencyRateProvider(models.Model):
    _name = 'sl.currency.rate.provider'
    _description = 'Currency Rate Provider'
    _order = 'company_id, name'

    name = fields.Char(compute='_compute_name', store=True)
    provider = fields.Selection(
        [('ecb', 'European Central Bank'),
         ('frankfurter', 'Frankfurter (ECB data, JSON)')],
        default='ecb', required=True)
    company_id = fields.Many2one(
        'res.company', required=True, ondelete='cascade',
        default=lambda self: self.env.company)
    company_currency_id = fields.Many2one(
        related='company_id.currency_id', string='Company Currency')
    currency_ids = fields.Many2many(
        'res.currency', string='Currencies To Update', required=True,
        help="Rates are written only for these currencies.")
    active = fields.Boolean(default=True)

    last_run = fields.Datetime(readonly=True)
    last_state = fields.Selection(
        [('ok', 'Success'), ('fail', 'Failed')], readonly=True)
    last_message = fields.Text(readonly=True)

    @api.depends('provider', 'company_id')
    def _compute_name(self):
        labels = dict(self._fields['provider'].selection)
        for record in self:
            record.name = '%s - %s' % (
                labels.get(record.provider, record.provider or ''),
                record.company_id.name or '')

    @api.constrains('currency_ids', 'company_id')
    def _check_currencies(self):
        for record in self:
            base = record.company_id.currency_id
            if base in record.currency_ids:
                raise ValidationError(_(
                    "%s is the company currency, so its rate is always 1. "
                    "Remove it from the list.") % base.name)

    # -- fetching ----------------------------------------------------------

    def _fetch(self):
        """Return the provider's raw payload. Split out so the parsing and
        rebasing below can be tested without touching the network."""
        self.ensure_one()
        if self.provider == 'ecb':
            response = requests.get(ECB_DAILY, timeout=TIMEOUT)
            response.raise_for_status()
            return response.content
        params = {'base': self.company_id.currency_id.name,
                  'symbols': ','.join(self.currency_ids.mapped('name'))}
        response = requests.get(FRANKFURTER, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()

    @api.model
    def _parse_ecb(self, payload):
        """(date, {currency_name: rate_per_EUR}) from the ECB daily feed."""
        root = etree.fromstring(payload)
        cube = root.find('.//ecb:Cube/ecb:Cube', namespaces=ECB_NS)
        if cube is None:
            raise UserError(_("The ECB feed did not contain any rates."))
        rates = {'EUR': 1.0}
        for node in cube.findall('ecb:Cube', namespaces=ECB_NS):
            currency, rate = node.get('currency'), node.get('rate')
            if currency and rate:
                rates[currency] = float(rate)
        return fields.Date.to_date(cube.get('time')), rates

    @api.model
    def _parse_frankfurter(self, payload):
        rates = dict(payload.get('rates') or {})
        rates[payload['base']] = 1.0
        return fields.Date.to_date(payload['date']), rates

    @api.model
    def _rebase(self, rates, base):
        """Re-express `rates` against `base` instead of the feed's own base.

        Odoo stores res.currency.rate as "how many units of this currency per
        one unit of the company currency", so a EUR-quoted feed has to be
        divided through by the company currency's own quote.
        """
        if base not in rates:
            raise UserError(_(
                "The feed does not quote %s, so rates cannot be expressed "
                "against it.") % base)
        divisor = rates[base]
        if not divisor:
            raise UserError(_("The feed quotes %s as zero.") % base)
        return {name: value / divisor for name, value in rates.items()}

    # -- writing -----------------------------------------------------------

    def _apply_rates(self, rate_date, rates):
        """Create or update one res.currency.rate per selected currency."""
        self.ensure_one()
        Rate = self.env['res.currency.rate']
        written = []
        for currency in self.currency_ids:
            value = rates.get(currency.name)
            if not value:
                _logger.info("%s not quoted by %s, skipped", currency.name, self.provider)
                continue
            existing = Rate.search([
                ('currency_id', '=', currency.id),
                ('name', '=', rate_date),
                ('company_id', '=', self.company_id.id),
            ], limit=1)
            if existing:
                existing.rate = value
            else:
                Rate.create({
                    'currency_id': currency.id,
                    'name': rate_date,
                    'rate': value,
                    'company_id': self.company_id.id,
                })
            written.append(currency.name)
        return written

    def action_update_rates(self):
        for record in self:
            record._update()
        return True

    def _update(self):
        self.ensure_one()
        try:
            payload = self._fetch()
            if self.provider == 'ecb':
                rate_date, rates = self._parse_ecb(payload)
            else:
                rate_date, rates = self._parse_frankfurter(payload)
            rates = self._rebase(rates, self.company_id.currency_id.name)
            written = self._apply_rates(rate_date, rates)
        except Exception as err:
            _logger.exception("Currency update failed for %s", self.name)
            self.sudo().write({
                'last_run': fields.Datetime.now(),
                'last_state': 'fail',
                'last_message': str(err),
            })
            raise UserError(_("Could not update rates: %s") % err)
        self.sudo().write({
            'last_run': fields.Datetime.now(),
            'last_state': 'ok',
            'last_message': _("%(count)s rate(s) for %(date)s: %(names)s") % {
                'count': len(written), 'date': rate_date,
                'names': ', '.join(written) or _("none")},
        })
        return True

    @api.model
    def _cron_update_rates(self):
        """One unreachable provider must not stop the others."""
        failures = []
        for record in self.search([]):
            try:
                record._update()
                self.env.cr.commit()
            except Exception as err:
                self.env.cr.rollback()
                failures.append('%s: %s' % (record.name, err))
        if failures:
            _logger.warning("Currency updates failed:\n%s", '\n'.join(failures))
        return True
