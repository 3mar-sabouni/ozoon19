# -*- coding: utf-8 -*-

from odoo import models, fields, api


class WebhookEvent(models.Model):
    """Defines the types of events that can trigger webhooks."""
    _name = 'webhook.event'
    _description = 'Webhook Event Type'
    _order = 'sequence, id'

    name = fields.Char(string='Event Name', required=True)
    code = fields.Char(
        string='Event Code', required=True,
        help='Technical code: on_create, on_write, on_unlink, on_state_change'
    )
    description = fields.Text(string='Description')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Event code must be unique!'),
    ]
