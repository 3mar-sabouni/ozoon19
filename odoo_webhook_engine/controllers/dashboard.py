# -*- coding: utf-8 -*-
"""
Dashboard data controller — serves analytics JSON for the OWL dashboard.
"""

import json
import logging
from datetime import datetime, timedelta

from odoo import http, fields
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class WebhookDashboardController(http.Controller):

    @http.route(
        '/webhook/dashboard/data', type='http', auth='user',
        methods=['GET'], csrf=False,
    )
    def dashboard_data(self, **kwargs):
        """Return aggregated webhook analytics for the dashboard."""
        env = request.env
        Log = env['webhook.log'].sudo()
        Rule = env['webhook.rule'].sudo()

        now = fields.Datetime.now()
        thirty_days_ago = now - timedelta(days=30)

        # All logs from last 30 days
        recent_logs = Log.search([
            ('create_date', '>=', thirty_days_ago),
        ])

        total = len(recent_logs)
        success = len(recent_logs.filtered(lambda l: l.status == 'success'))
        failed = len(recent_logs.filtered(lambda l: l.status == 'failed'))
        pending = len(recent_logs.filtered(lambda l: l.status == 'pending'))
        test_count = len(recent_logs.filtered(lambda l: l.status == 'test'))

        # Average execution time (success only)
        success_logs = recent_logs.filtered(lambda l: l.status == 'success' and l.execution_time)
        avg_time = (
            sum(l.execution_time for l in success_logs) / len(success_logs)
            if success_logs else 0
        )

        # Active rules
        active_rules = Rule.search_count([('active', '=', True)])

        # ── Top endpoints (target URLs) ────────────────────
        url_stats = {}
        for log in recent_logs:
            key = log.target_url or 'unknown'
            if key not in url_stats:
                url_stats[key] = {'url': key, 'calls': 0, 'total_time': 0, 'success': 0}
            url_stats[key]['calls'] += 1
            url_stats[key]['total_time'] += log.execution_time or 0
            if log.status == 'success':
                url_stats[key]['success'] += 1

        top_endpoints = sorted(url_stats.values(), key=lambda x: x['calls'], reverse=True)[:10]
        for ep in top_endpoints:
            ep['avg_time'] = ep['total_time'] / ep['calls'] if ep['calls'] else 0
            ep['success_rate'] = (ep['success'] / ep['calls'] * 100) if ep['calls'] else 0

        # ── Events per model ───────────────────────────────
        model_stats = {}
        for log in recent_logs:
            model = log.model_name or 'unknown'
            if model not in model_stats:
                model_stats[model] = 0
            model_stats[model] += 1

        events_per_model = sorted(
            [{'model': k, 'count': v} for k, v in model_stats.items()],
            key=lambda x: x['count'], reverse=True,
        )[:10]

        # ── Daily traffic ──────────────────────────────────
        daily = {}
        for log in recent_logs:
            day = log.create_date.strftime('%Y-%m-%d') if log.create_date else 'unknown'
            if day not in daily:
                daily[day] = {'date': day, 'calls': 0, 'success': 0, 'failed': 0}
            daily[day]['calls'] += 1
            if log.status == 'success':
                daily[day]['success'] += 1
            elif log.status == 'failed':
                daily[day]['failed'] += 1

        daily_stats = sorted(daily.values(), key=lambda x: x['date'])

        # ── Events per type ────────────────────────────────
        event_stats = {}
        for log in recent_logs:
            ev = log.event_code or 'unknown'
            if ev not in event_stats:
                event_stats[ev] = 0
            event_stats[ev] += 1

        events_by_type = [{'event': k, 'count': v} for k, v in event_stats.items()]

        # ── Dead-letter queue count ────────────────────────
        dlq_count = env['webhook.retry'].sudo().search_count([('state', '=', 'pending')])

        data = {
            'summary': {
                'total_sent': total,
                'success_count': success,
                'failed_count': failed,
                'pending_count': pending,
                'test_count': test_count,
                'avg_response_time': round(avg_time, 1),
                'active_rules': active_rules,
                'dlq_count': dlq_count,
                'success_rate': round((success / total * 100), 1) if total else 0,
            },
            'top_endpoints': top_endpoints,
            'events_per_model': events_per_model,
            'events_by_type': events_by_type,
            'daily_stats': daily_stats,
        }

        return Response(
            json.dumps(data, default=str),
            status=200,
            content_type='application/json',
        )
