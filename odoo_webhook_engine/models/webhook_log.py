# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from odoo import models, fields, api


class WebhookLog(models.Model):
    """Stores the full request/response log for every webhook dispatch."""
    _name = 'webhook.log'
    _description = 'Webhook Log'
    _order = 'create_date desc'
    _rec_name = 'display_name'

    rule_id = fields.Many2one(
        'webhook.rule', string='Webhook Rule',
        required=True, ondelete='cascade', index=True,
    )
    rule_name = fields.Char(related='rule_id.name', store=True)
    model_name = fields.Char(string='Model', index=True)
    record_id = fields.Integer(string='Record ID')
    event_code = fields.Char(string='Event')

    # ── Request ────────────────────────────────────────────
    target_url = fields.Char(string='Target URL')
    http_method = fields.Char(string='HTTP Method')
    request_headers = fields.Text(string='Request Headers')
    request_payload = fields.Text(string='Request Payload')

    # ── Response ───────────────────────────────────────────
    response_status = fields.Integer(string='HTTP Status Code')
    response_body = fields.Text(string='Response Body')
    response_headers = fields.Text(string='Response Headers')

    # ── Meta ───────────────────────────────────────────────
    status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('pending', 'Pending Retry'),
        ('test', 'Test Mode'),
    ], string='Status', default='pending', index=True)
    error_message = fields.Text(string='Error Message')
    execution_time = fields.Float(
        string='Execution Time (ms)',
        digits=(12, 2),
    )
    retry_count = fields.Integer(string='Retry Attempts', default=0)
    next_retry = fields.Datetime(string='Next Retry At')
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
    )
    is_test = fields.Boolean(string='Test Mode', default=False)

    display_name = fields.Char(compute='_compute_display_name', store=False)

    @api.depends('rule_name', 'create_date')
    def _compute_display_name(self):
        for log in self:
            dt = log.create_date.strftime('%Y-%m-%d %H:%M:%S') if log.create_date else ''
            log.display_name = f"{log.rule_name or 'Log'} — {dt}"

    def action_retry_now(self):
        """Manually retry a failed webhook delivery."""
        self.ensure_one()
        if self.status != 'failed':
            return
        from odoo.addons.odoo_webhook_engine.services.dispatcher import WebhookDispatcher
        dispatcher = WebhookDispatcher(self.env)
        dispatcher.retry_single(self)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Retry',
                'message': 'Webhook retried. Check updated log.',
                'type': 'info',
                'sticky': False,
            },
        }

    def _cron_process_retries(self):
        """Process pending webhook retries (called by cron)."""
        from odoo.addons.odoo_webhook_engine.services.dispatcher import WebhookDispatcher
        dispatcher = WebhookDispatcher(self.env)
        # Find all logs with pending retries
        pending_logs = self.search([
            ('status', '=', 'pending'),
            ('next_retry', '<=', fields.Datetime.now()),
        ])
        for log in pending_logs:
            dispatcher.retry_single(log)

    def _cron_cleanup_logs(self, days=30):
        """Cleanup old success logs (called by cron)."""
        cutoff_date = datetime.now() - timedelta(days=days)
        old_success_logs = self.search([
            ('status', '=', 'success'),
            ('create_date', '<', cutoff_date),
        ])
        old_success_logs.unlink()
