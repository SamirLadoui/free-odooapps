# -*- coding: utf-8 -*-
"""The half of an integration that is the same whatever it talks to.

Connecting to a shop is mostly not about the shop. It is retries, back-off,
timeouts, knowing what was already imported, and being able to say afterwards
what happened. That part is written here once so that a connector only has to
describe the thing it actually connects to.

Every real HTTP call goes through one method. That is deliberate: it is the
seam a test replaces with recorded answers, so the mapping, the retries and
the state machine can all be exercised without a live shop and without the
network deciding whether the build passes.
"""
import logging
import time

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TIMEOUT = 30
RETRIES = 3
# Worth trying again: the other side is busy or briefly broken. A 404 or a 401
# is an answer, and asking again will not change it.
RETRY_STATUS = (429, 500, 502, 503, 504)


class ConnectorError(UserError):
    """Something the other side said, or failed to say."""


class ConnectorBackend(models.AbstractModel):
    _name = 'sl.connector.backend'
    _description = 'Connector Backend'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)

    state = fields.Selection(
        [('draft', 'Not Connected'),
         ('connected', 'Connected'),
         ('error', 'Error')],
        default='draft', readonly=True, copy=False)
    last_sync = fields.Datetime(readonly=True, copy=False)
    last_error = fields.Text(readonly=True, copy=False)

    # -- the seam ----------------------------------------------------------

    def _perform_request(self, method, url, headers, payload, timeout):
        """The one place a real HTTP request is made.

        Everything above this is testable without a network.
        """
        return requests.request(
            method, url, headers=headers, json=payload, timeout=timeout)

    def _wait(self, seconds):
        """Also a seam: a test should not sit through a back-off."""
        time.sleep(seconds)

    # -- asking politely ---------------------------------------------------

    def _retry_after(self, response, attempt):
        """How long to wait before asking again.

        The other side's own answer is preferred over a guess; failing that,
        back off so a struggling shop is not hammered by a retry loop.
        """
        header = (response.headers or {}).get('Retry-After') if response else None
        if header:
            try:
                return min(float(header), 60.0)
            except (TypeError, ValueError):
                pass
        return min(2 ** attempt, 30)

    def _request(self, method, url, headers=None, payload=None,
                 timeout=TIMEOUT, retries=RETRIES):
        """One request, retried while the answer says it is worth retrying.

        No ensure_one: nothing here reads the backend, and being callable on
        the model itself is what lets the transport be tested on its own.
        """
        last = None
        for attempt in range(retries):
            try:
                response = self._perform_request(
                    method, url, headers or {}, payload, timeout)
            except requests.RequestException as error:
                # A refused connection or a timeout is worth another go; a
                # shop being restarted should not lose the day's orders.
                last = ConnectorError(_(
                    'Could not reach %(url)s: %(error)s', url=url, error=error))
                if attempt + 1 < retries:
                    self._wait(self._retry_after(None, attempt))
                    continue
                raise last
            if response.status_code in RETRY_STATUS and attempt + 1 < retries:
                self._wait(self._retry_after(response, attempt))
                continue
            return response
        raise last or ConnectorError(_('No answer from %s.', url))

    def _json(self, method, url, headers=None, payload=None, **kwargs):
        """A request whose answer is expected to be JSON."""
        response = self._request(method, url, headers, payload, **kwargs)
        if response.status_code >= 400:
            raise ConnectorError(_(
                '%(url)s answered %(status)s: %(body)s',
                url=url, status=response.status_code,
                body=(response.text or '')[:2000]))
        try:
            return response.json()
        except ValueError:
            raise ConnectorError(_(
                '%(url)s answered something that is not JSON: %(body)s',
                url=url, body=(response.text or '')[:500]))

    # -- saying what happened ---------------------------------------------

    def _log(self, operation, state='done', message=None, record=None,
             external_id=None, duration=0.0):
        self.ensure_one()
        return self.env['sl.connector.log']._record_run(
            self, operation, state=state, message=message, record=record,
            external_id=external_id, duration=duration)

    def _mapping(self):
        return self.env['sl.connector.mapping']

    def _note_success(self):
        self.ensure_one()
        self.sudo().write({
            'state': 'connected',
            'last_sync': fields.Datetime.now(),
            'last_error': False,
        })

    def _note_failure(self, error):
        self.ensure_one()
        self.sudo().write({'state': 'error', 'last_error': str(error)[:8000]})

    def action_view_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Synchronisation Log'),
            'res_model': 'sl.connector.log',
            'view_mode': 'list,form',
            'domain': [('backend_model', '=', self._name),
                       ('backend_id', '=', self.id)],
        }

    def action_view_mappings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Linked Records'),
            'res_model': 'sl.connector.mapping',
            'view_mode': 'list,form',
            'domain': [('backend_model', '=', self._name),
                       ('backend_id', '=', self.id)],
        }
