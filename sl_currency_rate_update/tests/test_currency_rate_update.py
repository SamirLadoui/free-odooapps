# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

# A trimmed copy of the real ECB daily feed, so parsing is tested without
# reaching the network.
ECB_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <gesmes:subject>Reference rates</gesmes:subject>
  <Cube>
    <Cube time="2026-03-04">
      <Cube currency="USD" rate="1.0850"/>
      <Cube currency="GBP" rate="0.8500"/>
      <Cube currency="JPY" rate="163.00"/>
    </Cube>
  </Cube>
</gesmes:Envelope>"""

ECB_EMPTY = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <gesmes:subject>Reference rates</gesmes:subject>
</gesmes:Envelope>"""


@tagged('post_install', '-at_install')
class TestCurrencyRateUpdate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Provider = cls.env['sl.currency.rate.provider']
        cls.usd = cls.env.ref('base.USD')
        cls.gbp = cls.env.ref('base.GBP')
        cls.eur = cls.env.ref('base.EUR')
        (cls.usd | cls.gbp | cls.eur).write({'active': True})

    def _provider(self, base_currency, currencies):
        company = self.env['res.company'].create({
            'name': 'Rates Co %s' % base_currency.name,
            'currency_id': base_currency.id,
        })
        return self.Provider.create({
            'provider': 'ecb',
            'company_id': company.id,
            'currency_ids': [(6, 0, currencies.ids)],
        })

    # -- parsing -----------------------------------------------------------

    def test_parse_ecb(self):
        rate_date, rates = self.Provider._parse_ecb(ECB_XML)
        self.assertEqual(str(rate_date), '2026-03-04')
        self.assertEqual(rates['USD'], 1.0850)
        self.assertEqual(rates['GBP'], 0.8500)
        self.assertEqual(rates['EUR'], 1.0, "the feed's own base must be included")

    def test_parse_ecb_without_rates(self):
        with self.assertRaises(UserError):
            self.Provider._parse_ecb(ECB_EMPTY)

    def test_parse_frankfurter(self):
        rate_date, rates = self.Provider._parse_frankfurter({
            'base': 'USD', 'date': '2026-03-04', 'rates': {'EUR': 0.92, 'GBP': 0.78}})
        self.assertEqual(str(rate_date), '2026-03-04')
        self.assertEqual(rates['USD'], 1.0)
        self.assertEqual(rates['EUR'], 0.92)

    # -- rebasing ----------------------------------------------------------

    def test_rebase_is_identity_for_the_feed_base(self):
        _d, rates = self.Provider._parse_ecb(ECB_XML)
        rebased = self.Provider._rebase(rates, 'EUR')
        self.assertEqual(rebased['USD'], 1.0850)
        self.assertEqual(rebased['EUR'], 1.0)

    def test_rebase_to_another_currency(self):
        """A USD company must see EUR quoted per USD, not per EUR."""
        _d, rates = self.Provider._parse_ecb(ECB_XML)
        rebased = self.Provider._rebase(rates, 'USD')
        self.assertAlmostEqual(rebased['USD'], 1.0, places=9)
        self.assertAlmostEqual(rebased['EUR'], 1 / 1.0850, places=9)
        self.assertAlmostEqual(rebased['GBP'], 0.8500 / 1.0850, places=9)

    def test_rebase_to_an_unquoted_currency(self):
        _d, rates = self.Provider._parse_ecb(ECB_XML)
        with self.assertRaises(UserError):
            self.Provider._rebase(rates, 'XYZ')

    def test_rebase_refuses_a_zero_quote(self):
        with self.assertRaises(UserError):
            self.Provider._rebase({'EUR': 1.0, 'USD': 0.0}, 'USD')

    # -- writing -----------------------------------------------------------

    def test_apply_rates_creates_records(self):
        provider = self._provider(self.eur, self.usd | self.gbp)
        rate_date, rates = self.Provider._parse_ecb(ECB_XML)
        written = provider._apply_rates(rate_date, rates)
        self.assertEqual(set(written), {'USD', 'GBP'})

        rate = self.env['res.currency.rate'].search([
            ('currency_id', '=', self.usd.id), ('name', '=', rate_date),
            ('company_id', '=', provider.company_id.id)])
        self.assertEqual(len(rate), 1)
        self.assertAlmostEqual(rate.rate, 1.0850, places=6)

    def test_apply_rates_updates_rather_than_duplicates(self):
        """Running twice in one day must not leave two rates for that day."""
        provider = self._provider(self.eur, self.usd)
        rate_date, rates = self.Provider._parse_ecb(ECB_XML)
        provider._apply_rates(rate_date, rates)
        provider._apply_rates(rate_date, dict(rates, USD=1.2))

        rate = self.env['res.currency.rate'].search([
            ('currency_id', '=', self.usd.id), ('name', '=', rate_date),
            ('company_id', '=', provider.company_id.id)])
        self.assertEqual(len(rate), 1)
        self.assertAlmostEqual(rate.rate, 1.2, places=6)

    def test_unquoted_currency_is_skipped_not_fatal(self):
        chf = self.env.ref('base.CHF')
        chf.active = True
        provider = self._provider(self.eur, self.usd | chf)
        rate_date, rates = self.Provider._parse_ecb(ECB_XML)
        written = provider._apply_rates(rate_date, rates)
        self.assertEqual(written, ['USD'], "CHF is not in the feed, so it is skipped")

    def test_company_currency_cannot_be_updated(self):
        with self.assertRaises(ValidationError):
            self._provider(self.eur, self.usd | self.eur)

    def test_name_is_readable(self):
        provider = self._provider(self.eur, self.usd)
        self.assertIn('European Central Bank', provider.name)
