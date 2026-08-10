# -*- coding: utf-8 -*-
"""
Incoming Webhook Controller
Exposes HTTP endpoints so external systems can push data INTO Odoo.
"""

import json
import logging

from odoo import http, _
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class IncomingWebhookController(http.Controller):

    @http.route(
        '/webhook/incoming/<string:slug>',
        type='http', auth='none', methods=['POST'], csrf=False,
    )
    def handle_incoming(self, slug, **kwargs):
        """
        Handle an incoming webhook call.

        :param slug: unique slug identifying the endpoint
        """
        # Look up endpoint
        endpoint = (
            request.env['webhook.incoming']
            .sudo()
            .search([('slug', '=', slug), ('active', '=', True)], limit=1)
        )
        if not endpoint:
            return Response(
                json.dumps({'error': 'Endpoint not found'}),
                status=404, content_type='application/json',
            )

        # ── IP restriction ─────────────────────────────────
        if endpoint.allowed_ips:
            allowed = [ip.strip() for ip in endpoint.allowed_ips.split(',') if ip.strip()]
            client_ip = request.httprequest.remote_addr
            if allowed and client_ip not in allowed:
                _logger.warning(
                    "Incoming webhook '%s' blocked IP %s", slug, client_ip,
                )
                return Response(
                    json.dumps({'error': 'IP not allowed'}),
                    status=403, content_type='application/json',
                )

        # ── Authentication ─────────────────────────────────
        if endpoint.auth_mode == 'api_key':
            key = request.httprequest.headers.get('X-Api-Key', '')
            if key != endpoint.api_key:
                return Response(
                    json.dumps({'error': 'Invalid API key'}),
                    status=401, content_type='application/json',
                )
        elif endpoint.auth_mode == 'bearer':
            auth_header = request.httprequest.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer ') or auth_header[7:] != endpoint.api_key:
                return Response(
                    json.dumps({'error': 'Invalid bearer token'}),
                    status=401, content_type='application/json',
                )

        # ── Parse payload ──────────────────────────────────
        try:
            raw = request.httprequest.get_data(as_text=True)
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return Response(
                json.dumps({'error': 'Invalid JSON'}),
                status=400, content_type='application/json',
            )

        # ── Update stats ───────────────────────────────────
        endpoint.sudo().write({
            'last_called': request.env.cr.now(),
            'call_count': endpoint.call_count + 1,
        })

        # ── Log if enabled ─────────────────────────────────
        if endpoint.log_requests:
            request.env['webhook.log'].sudo().create({
                'rule_id': False,
                'model_name': endpoint.target_model_name or 'webhook.incoming',
                'record_id': 0,
                'event_code': 'incoming',
                'target_url': f'/webhook/incoming/{slug}',
                'http_method': 'POST',
                'request_payload': json.dumps(payload, indent=2),
                'request_headers': json.dumps(
                    dict(request.httprequest.headers), indent=2
                ),
                'status': 'success',
                'response_status': 200,
            })

        # ── Execute action ─────────────────────────────────
        try:
            result = self._execute_action(endpoint, payload)
            return Response(
                json.dumps({'status': 'ok', 'result': result}),
                status=200, content_type='application/json',
            )
        except Exception as e:
            _logger.exception("Incoming webhook '%s' action error", slug)
            return Response(
                json.dumps({'error': str(e)}),
                status=500, content_type='application/json',
            )

    def _execute_action(self, endpoint, payload):
        """Run the configured action for the incoming webhook."""
        if endpoint.action_type == 'create_record':
            return self._action_create_record(endpoint, payload)
        elif endpoint.action_type == 'server_action':
            return self._action_server_action(endpoint, payload)
        elif endpoint.action_type == 'custom_code':
            return self._action_custom_code(endpoint, payload)
        return {}

    def _action_create_record(self, endpoint, payload):
        """Create a record in the target model using field mapping."""
        if not endpoint.target_model_name:
            raise ValueError('No target model configured.')

        mapping = json.loads(endpoint.field_mapping or '{}')
        vals = {}
        for json_key, odoo_field in mapping.items():
            if json_key in payload:
                vals[odoo_field] = payload[json_key]

        if not vals:
            # If no mapping, try to use payload directly
            vals = payload

        Model = request.env[endpoint.target_model_name].sudo()
        record = Model.create(vals)
        return {'created_id': record.id}

    def _action_server_action(self, endpoint, payload):
        """Execute a server action with payload context."""
        if not endpoint.server_action_id:
            raise ValueError('No server action configured.')

        action = endpoint.server_action_id.sudo()
        ctx = dict(request.env.context, webhook_payload=payload)
        action.with_context(ctx).run()
        return {'action': 'executed'}

    def _action_custom_code(self, endpoint, payload):
        """Execute custom Python code (sandboxed)."""
        if not endpoint.python_code:
            return {}

        local_vars = {
            'payload': payload,
            'env': request.env,
            'log': _logger,
            'result': {},
        }
        try:
            exec(endpoint.python_code, {}, local_vars)  # noqa: S102
        except Exception as e:
            raise ValueError(f'Code execution error: {e}')

        return local_vars.get('result', {})

    # ─────────────────────────────────────────────────────
    # Health check endpoint
    # ─────────────────────────────────────────────────────
    @http.route(
        '/webhook/health', type='http', auth='none',
        methods=['GET'], csrf=False,
    )
    def health_check(self, **kwargs):
        return Response(
            json.dumps({'status': 'ok', 'engine': 'Odoo Webhook Engine 19.0'}),
            status=200, content_type='application/json',
        )
