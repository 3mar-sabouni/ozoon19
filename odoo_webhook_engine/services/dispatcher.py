# -*- coding: utf-8 -*-
"""
HTTP Dispatcher — sends outgoing webhook HTTP requests with retry logic,
HMAC signing, logging, and exponential backoff.
"""

import json
import logging
import time
from datetime import datetime, timedelta

import requests as http_requests

from .signature import compute_signature
from .payload_builder import PayloadBuilder

_logger = logging.getLogger(__name__)


class WebhookDispatcher:
    """Dispatches webhook HTTP calls and manages retries."""

    def __init__(self, env):
        self.env = env
        self.payload_builder = PayloadBuilder(env)

    # ─────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────
    def dispatch(self, rule, record, event_code, test=False):
        """
        Build payload and send HTTP request for a single record.

        :param rule: webhook.rule record
        :param record: Odoo record that triggered the event
        :param event_code: str
        :param test: if True, log but don't send
        """
        payload = self.payload_builder.build(rule, record, event_code)
        self._send(rule, payload, record.id, event_code, test=test or rule.test_mode)

    def dispatch_raw(self, rule, snapshot, event_code):
        """Dispatch from a pre-deletion snapshot dict."""
        payload = self.payload_builder.build_from_snapshot(rule, snapshot, event_code)
        record_id = snapshot.get('id', 0) if isinstance(snapshot, dict) else 0
        self._send(rule, payload, record_id, event_code, test=rule.test_mode)

    def retry_single(self, log):
        """Retry a single failed log entry."""
        rule = log.rule_id
        if not rule:
            return
        payload = json.loads(log.request_payload or '{}')
        self._send(
            rule, payload, log.record_id, log.event_code,
            test=False, existing_log=log,
        )

    # ─────────────────────────────────────────────────────
    # Core send logic
    # ─────────────────────────────────────────────────────
    def _send(self, rule, payload, record_id, event_code, test=False, existing_log=None):
        payload_json = json.dumps(payload, default=str, ensure_ascii=False)
        payload_bytes = payload_json.encode('utf-8')

        # Headers
        headers = {
            'Content-Type': rule.content_type or 'application/json',
            'User-Agent': 'Odoo-Webhook-Engine/19.0',
            'X-Odoo-Event': event_code or '',
            'X-Odoo-Model': rule.model_name or '',
        }
        # Custom headers
        if rule.custom_headers:
            try:
                custom = json.loads(rule.custom_headers)
                headers.update(custom)
            except Exception:
                pass

        # HMAC signature
        if rule.secret_key:
            sig = compute_signature(payload_bytes, rule.secret_key)
            headers['X-Odoo-Signature'] = sig

        # Prepare log values
        log_vals = {
            'rule_id': rule.id,
            'model_name': rule.model_name,
            'record_id': record_id,
            'event_code': event_code,
            'target_url': rule.target_url,
            'http_method': rule.http_method,
            'request_headers': json.dumps(headers, indent=2),
            'request_payload': payload_json,
            'is_test': test,
        }

        if test:
            log_vals.update({
                'status': 'test',
                'response_status': 0,
                'response_body': '--- TEST MODE: no request sent ---',
                'execution_time': 0,
            })
            if existing_log:
                existing_log.write(log_vals)
            else:
                self.env['webhook.log'].sudo().create(log_vals)
            return

        # ── Actually send ──────────────────────────────────
        start = time.time()
        try:
            method_fn = getattr(http_requests, rule.http_method.lower(), http_requests.post)
            response = method_fn(
                rule.target_url,
                data=payload_bytes,
                headers=headers,
                timeout=rule.timeout or 30,
            )
            elapsed = (time.time() - start) * 1000  # ms

            is_success = 200 <= response.status_code < 300
            log_vals.update({
                'response_status': response.status_code,
                'response_body': response.text[:10000] if response.text else '',
                'response_headers': json.dumps(dict(response.headers), indent=2),
                'execution_time': elapsed,
                'status': 'success' if is_success else 'failed',
                'error_message': '' if is_success else f'HTTP {response.status_code}',
            })

            if existing_log:
                existing_log.write(log_vals)
            else:
                log = self.env['webhook.log'].sudo().create(log_vals)
                # Schedule retry if failed
                if not is_success:
                    self._schedule_retry(rule, log)

        except http_requests.exceptions.Timeout:
            elapsed = (time.time() - start) * 1000
            log_vals.update({
                'status': 'failed',
                'error_message': 'Request timed out',
                'execution_time': elapsed,
            })
            if existing_log:
                existing_log.write(log_vals)
            else:
                log = self.env['webhook.log'].sudo().create(log_vals)
                self._schedule_retry(rule, log)

        except http_requests.exceptions.ConnectionError as e:
            elapsed = (time.time() - start) * 1000
            log_vals.update({
                'status': 'failed',
                'error_message': f'Connection error: {str(e)[:500]}',
                'execution_time': elapsed,
            })
            if existing_log:
                existing_log.write(log_vals)
            else:
                log = self.env['webhook.log'].sudo().create(log_vals)
                self._schedule_retry(rule, log)

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            _logger.exception("Webhook dispatch error")
            log_vals.update({
                'status': 'failed',
                'error_message': str(e)[:1000],
                'execution_time': elapsed,
            })
            if existing_log:
                existing_log.write(log_vals)
            else:
                log = self.env['webhook.log'].sudo().create(log_vals)
                self._schedule_retry(rule, log)

    # ─────────────────────────────────────────────────────
    # Retry scheduling
    # ─────────────────────────────────────────────────────
    def _schedule_retry(self, rule, log):
        """Set next_retry with exponential backoff."""
        if log.retry_count >= rule.max_retries:
            # Move to dead-letter queue
            self.env['webhook.retry'].sudo().create({
                'log_id': log.id,
                'state': 'pending',
            })
            _logger.warning(
                "Webhook '%s' exhausted retries for record %s. Moved to dead-letter queue.",
                rule.name, log.record_id,
            )
            return

        delay = rule.retry_delay * (2 ** log.retry_count)  # exponential backoff
        next_dt = datetime.utcnow() + timedelta(seconds=delay)
        log.write({
            'status': 'pending',
            'next_retry': next_dt,
            'retry_count': log.retry_count + 1,
        })

    # ─────────────────────────────────────────────────────
    # Cron: process pending retries
    # ─────────────────────────────────────────────────────
    @staticmethod
    def cron_process_retries(env):
        """Called by cron — retry all pending logs whose next_retry has passed."""
        now = datetime.utcnow()
        pending = env['webhook.log'].sudo().search([
            ('status', '=', 'pending'),
            ('next_retry', '<=', now),
        ], limit=100)

        dispatcher = WebhookDispatcher(env)
        for log in pending:
            try:
                dispatcher.retry_single(log)
            except Exception:
                _logger.exception("Cron retry error for log %s", log.id)

    # ─────────────────────────────────────────────────────
    # Cron: clean old logs
    # ─────────────────────────────────────────────────────
    @staticmethod
    def cron_cleanup_logs(env, days=30):
        """Delete successful logs older than `days`."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        old_logs = env['webhook.log'].sudo().search([
            ('status', '=', 'success'),
            ('create_date', '<', cutoff),
        ])
        count = len(old_logs)
        old_logs.unlink()
        _logger.info("Webhook log cleanup: removed %d old success logs.", count)
