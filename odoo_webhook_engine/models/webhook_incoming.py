# -*- coding: utf-8 -*-

import json
import logging
import secrets

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class WebhookIncoming(models.Model):
    """Incoming webhook endpoint — allows external systems to call Odoo."""
    _name = 'webhook.incoming'
    _description = 'Incoming Webhook Endpoint'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(string='Endpoint Name', required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    slug = fields.Char(
        string='URL Slug', required=True,
        help='Unique slug for the URL path: /webhook/incoming/<slug>',
    )
    api_key = fields.Char(
        string='API Key', readonly=True,
        default=lambda self: secrets.token_hex(32),
    )
    auth_mode = fields.Selection([
        ('none', 'No Authentication'),
        ('api_key', 'API Key (Header)'),
        ('bearer', 'Bearer Token'),
    ], string='Authentication', default='api_key', required=True)
    allowed_ips = fields.Char(
        string='Allowed IPs',
        help='Comma-separated list of allowed IP addresses. Leave empty to allow all.',
    )
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
    )

    # ── Action on receive ──────────────────────────────────
    action_type = fields.Selection([
        ('server_action', 'Run Server Action'),
        ('create_record', 'Create Record'),
        ('custom_code', 'Execute Python Code'),
    ], string='Action Type', default='create_record', required=True)
    target_model_id = fields.Many2one(
        'ir.model', string='Target Model',
        help='Model in which to create records (for create_record action).',
    )
    target_model_name = fields.Char(
        related='target_model_id.model', store=True, readonly=True,
    )
    server_action_id = fields.Many2one(
        'ir.actions.server', string='Server Action',
    )
    field_mapping = fields.Text(
        string='Field Mapping (JSON)',
        default='{}',
        help='JSON mapping: {"json_field": "odoo_field"}. Used for create_record action.',
    )
    python_code = fields.Text(
        string='Python Code',
        help='Python code to execute. Available: payload (dict), env, log.',
        default="# Access incoming JSON via `payload` dict\n# result = env['res.partner'].create({'name': payload.get('name')})\n",
    )

    # ── Logging ────────────────────────────────────────────
    log_requests = fields.Boolean(string='Log Incoming Requests', default=True)
    last_called = fields.Datetime(string='Last Called', readonly=True)
    call_count = fields.Integer(string='Total Calls', readonly=True, default=0)

    _sql_constraints = [
        ('slug_unique', 'UNIQUE(slug)', 'Endpoint slug must be unique!'),
    ]

    @api.constrains('field_mapping')
    def _check_field_mapping(self):
        for rec in self:
            if rec.field_mapping:
                try:
                    m = json.loads(rec.field_mapping)
                    if not isinstance(m, dict):
                        raise ValidationError(_('Field mapping must be a JSON object.'))
                except json.JSONDecodeError as e:
                    raise ValidationError(_('Invalid field mapping JSON: %s') % str(e))

    def action_regenerate_key(self):
        """Generate a new API key."""
        self.ensure_one()
        self.api_key = secrets.token_hex(32)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('API Key'),
                'message': _('New API key generated.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_copy_url(self):
        """Return the full endpoint URL for display."""
        self.ensure_one()
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        url = f"{base}/webhook/incoming/{self.slug}"
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Endpoint URL'),
                'message': url,
                'type': 'info',
                'sticky': True,
            },
        }
