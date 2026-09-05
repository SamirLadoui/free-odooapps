# -*- coding: utf-8 -*-
"""The half of an integration that has nothing to do with any shop.

There is no live service here on purpose: the request seam is replaced with
recorded answers, so retries, back-off and error handling are exercised
without the network deciding whether the build passes.

res.company stands in as a backend. The mapping and the log only ever ask a
backend for its model name and its id, which is what lets one table serve a
Shopify backend, a Salla backend and something written in-house.
"""
from unittest.mock import patch

import requests

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.sl_connector_base.models.connector_backend import (
    ConnectorError)


class FakeResponse:
    """Just enough of a requests response to answer the code under test."""

    def __init__(self, status_code=200, payload=None, text=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else ''
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError('not json')
        return self._payload


@tagged('post_install', '-at_install')
class TestConnectorBase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.backend = self.env.company
        self.other_backend = self.env['res.company'].create(
            {'name': 'Second Backend'})
        self.mapping = self.env['sl.connector.mapping']
        self.partner = self.env['res.partner'].create({'name': 'Imported Ltd'})
        self.transport = self.env['sl.connector.backend']

    # -- the link table ----------------------------------------------------

    def test_a_record_can_be_found_by_its_external_id(self):
        self.mapping._bind(self.backend, self.partner, '1234')
        found = self.mapping._record(self.backend, 'res.partner', '1234')
        self.assertEqual(found, self.partner)

    def test_an_unknown_external_id_finds_nothing(self):
        found = self.mapping._record(self.backend, 'res.partner', 'nope')
        self.assertFalse(found)

    def test_the_external_id_can_be_found_from_the_record(self):
        self.mapping._bind(self.backend, self.partner, '1234')
        self.assertEqual(
            self.mapping._external_id(self.backend, self.partner), '1234')

    def test_an_id_is_matched_as_text_whatever_it_arrives_as(self):
        """Shopify ids are numbers in JSON and strings in a URL."""
        self.mapping._bind(self.backend, self.partner, 1234)
        self.assertEqual(
            self.mapping._record(self.backend, 'res.partner', '1234'),
            self.partner)

    def test_binding_the_same_pair_again_is_not_an_error(self):
        """Re-importing an order should refresh it, not fail or duplicate."""
        first = self.mapping._bind(self.backend, self.partner, '1234')
        second = self.mapping._bind(self.backend, self.partner, '1234')
        self.assertEqual(first, second)
        self.assertEqual(self.mapping.search_count(
            [('external_id', '=', '1234')]), 1)

    def test_two_backends_do_not_share_their_links(self):
        """The same order number on two shops is two different orders."""
        other = self.env['res.partner'].create({'name': 'Other Shop Ltd'})
        self.mapping._bind(self.backend, self.partner, '1')
        self.mapping._bind(self.other_backend, other, '1')
        self.assertEqual(
            self.mapping._record(self.backend, 'res.partner', '1'),
            self.partner)
        self.assertEqual(
            self.mapping._record(self.other_backend, 'res.partner', '1'),
            other)

    def test_a_link_to_a_deleted_record_is_cleaned_up(self):
        """A stale id handed back would move the error somewhere worse."""
        self.mapping._bind(self.backend, self.partner, '1234')
        self.partner.unlink()
        self.assertFalse(self.mapping._record(self.backend, 'res.partner', '1234'))
        self.assertFalse(self.mapping.search(
            [('external_id', '=', '1234')]))

    def test_an_external_record_with_no_id_is_refused(self):
        with self.assertRaises(UserError):
            self.mapping._bind(self.backend, self.partner, False)

    def test_rebinding_a_record_to_a_new_external_id_moves_the_link(self):
        self.mapping._bind(self.backend, self.partner, 'old')
        self.mapping._bind(self.backend, self.partner, 'new')
        self.assertEqual(
            self.mapping._external_id(self.backend, self.partner), 'new')
        self.assertEqual(self.mapping.search_count(
            [('res_id', '=', self.partner.id),
             ('model_name', '=', 'res.partner')]), 1)

    # -- doing no work twice -----------------------------------------------

    def test_something_never_seen_counts_as_newer(self):
        self.assertTrue(self.mapping._is_newer(
            self.backend, 'res.partner', 'unknown',
            fields.Datetime.now()))

    def test_an_unchanged_record_is_not_newer(self):
        when = fields.Datetime.now()
        self.mapping._bind(self.backend, self.partner, '1', external_written=when)
        self.assertFalse(self.mapping._is_newer(
            self.backend, 'res.partner', '1', when))

    def test_a_changed_record_is_newer(self):
        when = fields.Datetime.now()
        self.mapping._bind(self.backend, self.partner, '1', external_written=when)
        later = fields.Datetime.add(when, hours=1)
        self.assertTrue(self.mapping._is_newer(
            self.backend, 'res.partner', '1', later))

    # -- the log -----------------------------------------------------------

    def test_a_run_leaves_a_line(self):
        log = self.env['sl.connector.log']._record_run(
            self.backend, 'import orders', state='done', external_id='42')
        self.assertEqual(log.operation, 'import orders')
        self.assertEqual(log.external_id, '42')
        self.assertEqual(log.backend_model, 'res.company')

    def test_a_failure_keeps_what_the_other_side_said(self):
        log = self.env['sl.connector.log']._record_run(
            self.backend, 'import orders', state='error',
            message='401 Unauthorized: bad token')
        self.assertEqual(log.state, 'error')
        self.assertIn('bad token', log.message)

    def test_the_log_cannot_be_rewritten(self):
        """A record of what happened that can be edited is not a record."""
        log = self.env['sl.connector.log']._record_run(self.backend, 'x')
        with self.assertRaises(UserError):
            log.state = 'done'
        with self.assertRaises(UserError):
            log.message = 'nothing to see'

    def test_old_lines_are_pruned_and_recent_ones_are_not(self):
        old = self.env['sl.connector.log']._record_run(self.backend, 'old')
        recent = self.env['sl.connector.log']._record_run(self.backend, 'recent')
        self.env.cr.execute(
            "UPDATE sl_connector_log SET create_date = %s WHERE id = %s",
            (fields.Datetime.subtract(fields.Datetime.now(), days=200), old.id))
        old.invalidate_recordset()
        self.env['sl.connector.log']._prune(90)
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())

    # -- asking politely ---------------------------------------------------

    def _with_responses(self, *responses):
        """Answer each call with the next recorded response."""
        calls = []

        def fake(model, method, url, headers, payload, timeout):
            calls.append((method, url, headers, payload))
            answer = responses[min(len(calls) - 1, len(responses) - 1)]
            if isinstance(answer, Exception):
                raise answer
            return answer

        return fake, calls

    def _patched(self, fake):
        model = type(self.env['sl.connector.backend'])
        return patch.multiple(model, _perform_request=fake,
                              _wait=lambda self, seconds: None)

    def test_a_good_answer_comes_straight_back(self):
        fake, calls = self._with_responses(FakeResponse(200, {'ok': True}))
        with self._patched(fake):
            result = self.transport._json('GET', 'https://shop/x')
        self.assertEqual(result, {'ok': True})
        self.assertEqual(len(calls), 1)

    def test_being_told_to_slow_down_is_tried_again(self):
        """429 is the answer a busy shop gives, not a refusal."""
        fake, calls = self._with_responses(
            FakeResponse(429, headers={'Retry-After': '1'}),
            FakeResponse(200, {'ok': True}))
        with self._patched(fake):
            result = self.transport._json('GET', 'https://shop/x')
        self.assertEqual(result, {'ok': True})
        self.assertEqual(len(calls), 2)

    def test_a_refusal_is_not_tried_again(self):
        """Asking twice will not turn a 401 into a 200."""
        fake, calls = self._with_responses(FakeResponse(401, text='bad token'))
        with self._patched(fake):
            with self.assertRaises(ConnectorError):
                self.transport._json('GET', 'https://shop/x')
        self.assertEqual(len(calls), 1)

    def test_the_error_carries_what_the_other_side_said(self):
        fake, _calls = self._with_responses(
            FakeResponse(422, text='barcode has already been taken'))
        with self._patched(fake):
            with self.assertRaises(ConnectorError) as caught:
                self.transport._json('POST', 'https://shop/x')
        self.assertIn('barcode has already been taken', str(caught.exception))

    def test_a_dropped_connection_is_tried_again(self):
        fake, calls = self._with_responses(
            requests.ConnectionError('connection refused'),
            FakeResponse(200, {'ok': True}))
        with self._patched(fake):
            result = self.transport._json('GET', 'https://shop/x')
        self.assertEqual(result, {'ok': True})
        self.assertEqual(len(calls), 2)

    def test_it_gives_up_rather_than_retrying_for_ever(self):
        fake, calls = self._with_responses(
            requests.ConnectionError('connection refused'))
        with self._patched(fake):
            with self.assertRaises(ConnectorError):
                self.transport._json('GET', 'https://shop/x')
        self.assertEqual(len(calls), 3)

    def test_an_answer_that_is_not_json_is_reported_as_such(self):
        """A shop behind a broken proxy answers 200 with an HTML error page."""
        fake, _calls = self._with_responses(
            FakeResponse(200, payload=None, text='<html>Gateway Error</html>'))
        with self._patched(fake):
            with self.assertRaises(ConnectorError) as caught:
                self.transport._json('GET', 'https://shop/x')
        self.assertIn('not JSON', str(caught.exception))

    def test_the_other_sides_own_retry_after_is_preferred(self):
        response = FakeResponse(429, headers={'Retry-After': '7'})
        self.assertEqual(self.transport._retry_after(response, 0), 7.0)

    def test_a_nonsense_retry_after_falls_back_to_backing_off(self):
        response = FakeResponse(429, headers={'Retry-After': 'soon'})
        self.assertEqual(self.transport._retry_after(response, 2), 4)

    def test_a_wait_is_never_longer_than_a_minute(self):
        response = FakeResponse(429, headers={'Retry-After': '86400'})
        self.assertEqual(self.transport._retry_after(response, 0), 60.0)
