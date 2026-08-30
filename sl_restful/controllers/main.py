# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)

MAX_LIMIT = 1000
DEFAULT_LIMIT = 80


def _json(payload, status=200):
    # make_response only grew a status kwarg after 15.0, so the code is set on
    # the response instead - that works on every version.
    response = request.make_response(
        json.dumps(payload, default=str),
        [('Content-Type', 'application/json')])
    response.status_code = status
    return response


def _error(message, status):
    return _json({'error': message}, status=status)


class RestApi(http.Controller):
    """A small, predictable REST surface over the ORM.

    Every request runs as the user the key names, so Odoo's own access rights
    and record rules decide what happens. The key can narrow that further but
    never widens it.
    """

    # -- authentication ----------------------------------------------------

    def _authenticate(self, model_name):
        """Returns (env, error_response). Exactly one of them is set."""
        raw_key = request.httprequest.headers.get('X-Api-Key')
        if not raw_key:
            return None, _error('Missing X-Api-Key header.', 401)

        key = request.env['sl.api.key'].sudo()._resolve(raw_key)
        if not key or not key._is_usable():
            # Deliberately the same message for unknown, revoked and expired:
            # a caller learns whether their key works, not why it does not.
            return None, _error('Invalid or expired API key.', 401)
        if not key._may_touch(model_name):
            return None, _error('This key may not access %s.' % model_name, 403)
        if model_name not in request.env:
            return None, _error('No such model: %s.' % model_name, 404)

        key._note_use()
        return request.env(user=key.user_id.id), None

    # -- helpers -----------------------------------------------------------

    def _payload(self):
        try:
            raw = request.httprequest.get_data(as_text=True) or '{}'
            data = json.loads(raw)
        except ValueError:
            return None, _error('Body is not valid JSON.', 400)
        if not isinstance(data, dict):
            return None, _error('Body must be a JSON object.', 400)
        return data, None

    def _limit(self, raw):
        try:
            limit = int(raw) if raw else DEFAULT_LIMIT
        except (TypeError, ValueError):
            limit = DEFAULT_LIMIT
        return max(1, min(limit, MAX_LIMIT))

    def _fields(self, raw):
        if not raw:
            return None
        return [name.strip() for name in raw.split(',') if name.strip()]

    # -- routes ------------------------------------------------------------

    @http.route('/api/v1/<string:model_name>', type='http', auth='none',
                methods=['GET'], csrf=False, save_session=False)
    def search_read(self, model_name, **params):
        env, error = self._authenticate(model_name)
        if error:
            return error
        try:
            domain = json.loads(params.get('domain') or '[]')
        except ValueError:
            return _error('domain is not valid JSON.', 400)

        try:
            model = env[model_name]
            records = model.search_read(
                domain,
                self._fields(params.get('fields')),
                offset=int(params.get('offset') or 0),
                limit=self._limit(params.get('limit')),
                order=params.get('order') or None)
            total = model.search_count(domain)
        except AccessError as err:
            return _error(str(err), 403)
        except (ValueError, TypeError) as err:
            return _error(str(err), 400)
        return _json({'count': total, 'results': records})

    @http.route('/api/v1/<string:model_name>/<int:record_id>', type='http',
                auth='none', methods=['GET'], csrf=False, save_session=False)
    def read_one(self, model_name, record_id, **params):
        env, error = self._authenticate(model_name)
        if error:
            return error
        record = env[model_name].browse(record_id)
        try:
            data = record.read(self._fields(params.get('fields')))
        except AccessError as err:
            return _error(str(err), 403)
        except MissingError:
            return _error('Record %s not found.' % record_id, 404)
        if not data:
            return _error('Record %s not found.' % record_id, 404)
        return _json(data[0])

    @http.route('/api/v1/<string:model_name>', type='http', auth='none',
                methods=['POST'], csrf=False, save_session=False)
    def create(self, model_name, **params):
        env, error = self._authenticate(model_name)
        if error:
            return error
        data, error = self._payload()
        if error:
            return error
        try:
            record = env[model_name].create(data)
        except AccessError as err:
            return _error(str(err), 403)
        except (UserError, ValidationError) as err:
            return _error(str(err), 400)
        except (ValueError, TypeError, KeyError) as err:
            return _error(str(err), 400)
        return _json({'id': record.id}, status=201)

    @http.route('/api/v1/<string:model_name>/<int:record_id>', type='http',
                auth='none', methods=['PUT', 'PATCH'], csrf=False, save_session=False)
    def update(self, model_name, record_id, **params):
        env, error = self._authenticate(model_name)
        if error:
            return error
        data, error = self._payload()
        if error:
            return error
        record = env[model_name].browse(record_id).exists()
        if not record:
            return _error('Record %s not found.' % record_id, 404)
        try:
            record.write(data)
        except AccessError as err:
            return _error(str(err), 403)
        except (UserError, ValidationError) as err:
            return _error(str(err), 400)
        except (ValueError, TypeError, KeyError) as err:
            return _error(str(err), 400)
        return _json({'id': record.id, 'updated': True})

    @http.route('/api/v1/<string:model_name>/<int:record_id>', type='http',
                auth='none', methods=['DELETE'], csrf=False, save_session=False)
    def delete(self, model_name, record_id, **params):
        env, error = self._authenticate(model_name)
        if error:
            return error
        record = env[model_name].browse(record_id).exists()
        if not record:
            return _error('Record %s not found.' % record_id, 404)
        try:
            record.unlink()
        except AccessError as err:
            return _error(str(err), 403)
        except (UserError, ValidationError) as err:
            return _error(str(err), 400)
        return _json({'id': record_id, 'deleted': True})
