# -*- coding: utf-8 -*-

import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class WebhookRetry(models.Model):
    """Dead-letter queue for permanently failed deliveries."""
    _name = 'webhook.retry'
    _description = 'Webhook Dead Letter Queue'
    _order = 'create_date desc'

    log_id = fields.Many2one(
        'webhook.log', string='Original Log',
        required=True, ondelete='cascade',
    )
    rule_id = fields.Many2one(
        'webhook.rule', string='Webhook Rule',
        related='log_id.rule_id', store=True,
    )
    model_name = fields.Char(related='log_id.model_name', store=True)
    record_id = fields.Integer(related='log_id.record_id', store=True)
    payload = fields.Text(related='log_id.request_payload')
    error_message = fields.Text(related='log_id.error_message')
    retry_count = fields.Integer(related='log_id.retry_count')

    state = fields.Selection([
        ('pending', 'Pending Review'),
        ('retried', 'Retried'),
        ('discarded', 'Discarded'),
    ], default='pending', string='Status')

    def action_retry(self):
        """Retry from dead-letter queue."""
        self.ensure_one()
        if self.state != 'pending':
            return
        self.log_id.action_retry_now()
        self.state = 'retried'

    def action_discard(self):
        """Mark as discarded — will not be retried."""
        self.ensure_one()
        self.state = 'discarded'
