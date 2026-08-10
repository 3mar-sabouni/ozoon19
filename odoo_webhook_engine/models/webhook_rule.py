# -*- coding: utf-8 -*-

import json
import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class WebhookRule(models.Model):
    """Webhook rule: maps an Odoo model event to an outgoing HTTP call."""
    _name = 'webhook.rule'
    _description = 'Webhook Rule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id'

    # ── Core ───────────────────────────────────────────────
    name = fields.Char(string='Webhook Name', required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
    )

    # ── Event configuration ────────────────────────────────
    model_id = fields.Many2one(
        'ir.model', string='Model', required=True,
        ondelete='cascade', tracking=True,
        help='Odoo model to watch for events',
    )
    model_name = fields.Char(
        related='model_id.model', store=True, readonly=True,
    )
    event_id = fields.Many2one(
        'webhook.event', string='Trigger Event', required=True,
        tracking=True,
    )
    event_code = fields.Char(
        related='event_id.code', store=True, readonly=True,
    )
    domain_filter = fields.Text(
        string='Domain Filter',
        default='[]',
        help='Odoo domain to filter records. Only matching records trigger the webhook.',
    )
    watched_fields = fields.Char(
        string='Watched Fields',
        help='Comma-separated field names. Only triggers on_write when these fields change. Leave empty for any change.',
    )
    state_field = fields.Char(
        string='State Field',
        default='state',
        help='Field name to watch for state changes (used with on_state_change event).',
    )
    state_value = fields.Char(
        string='State Value',
        help='Trigger only when state field equals this value. Leave empty for any state change.',
    )

    # ── Endpoint configuration ─────────────────────────────
    target_url = fields.Char(
        string='Target URL', required=True, tracking=True,
        help='External endpoint URL to call when the event fires.',
    )
    http_method = fields.Selection([
        ('POST', 'POST'),
        ('PUT', 'PUT'),
        ('PATCH', 'PATCH'),
    ], string='HTTP Method', default='POST', required=True)
    custom_headers = fields.Text(
        string='Custom Headers (JSON)',
        default='{}',
        help='Additional HTTP headers as JSON object. Example: {"Authorization": "Bearer xxx"}',
    )
    content_type = fields.Selection([
        ('application/json', 'JSON'),
        ('application/x-www-form-urlencoded', 'Form URL-Encoded'),
    ], string='Content Type', default='application/json', required=True)

    # ── Security ───────────────────────────────────────────
    secret_key = fields.Char(
        string='Secret Key',
        help='HMAC-SHA256 signing key. The signature is sent in X-Odoo-Signature header.',
    )

    # ── Payload ────────────────────────────────────────────
    payload_mode = fields.Selection([
        ('fields', 'Field Picker'),
        ('template', 'Jinja2 Template'),
        ('full', 'Full Record Data'),
    ], string='Payload Mode', default='fields', required=True)
    payload_field_ids = fields.One2many(
        'webhook.payload.field', 'rule_id',
        string='Payload Fields',
    )
    payload_template = fields.Text(
        string='Payload Template (Jinja2)',
        help='Jinja2 template for advanced payload. Available variables: record, event, env.',
        default="""{
  "id": {{ record.id }},
  "name": "{{ record.display_name }}",
  "event": "{{ event }}",
  "timestamp": "{{ timestamp }}"
}""",
    )

    # ── Retry configuration ────────────────────────────────
    max_retries = fields.Integer(
        string='Max Retries', default=3,
        help='Number of retry attempts on failure.',
    )
    retry_delay = fields.Integer(
        string='Initial Retry Delay (s)', default=60,
        help='Delay in seconds before first retry. Doubles each attempt (exponential backoff).',
    )
    timeout = fields.Integer(
        string='Request Timeout (s)', default=30,
        help='HTTP request timeout in seconds.',
    )

    # ── Statistics ─────────────────────────────────────────
    log_ids = fields.One2many('webhook.log', 'rule_id', string='Logs')
    total_sent = fields.Integer(
        string='Total Sent', compute='_compute_stats', store=False,
    )
    success_count = fields.Integer(
        string='Success', compute='_compute_stats', store=False,
    )
    fail_count = fields.Integer(
        string='Failed', compute='_compute_stats', store=False,
    )
    success_rate = fields.Float(
        string='Success Rate (%)', compute='_compute_stats', store=False,
    )

    # ── Test mode ──────────────────────────────────────────
    test_mode = fields.Boolean(
        string='Test Mode',
        help='When enabled, payloads are logged but NOT actually sent.',
    )

    # ─────────────────────────────────────────────────────
    # Computed
    # ─────────────────────────────────────────────────────
    @api.depends('log_ids', 'log_ids.status')
    def _compute_stats(self):
        for rule in self:
            logs = rule.log_ids
            rule.total_sent = len(logs)
            rule.success_count = len(logs.filtered(lambda l: l.status == 'success'))
            rule.fail_count = len(logs.filtered(lambda l: l.status == 'failed'))
            rule.success_rate = (
                (rule.success_count / rule.total_sent * 100)
                if rule.total_sent else 0.0
            )

    # ─────────────────────────────────────────────────────
    # Validation
    # ─────────────────────────────────────────────────────
    @api.constrains('domain_filter')
    def _check_domain_filter(self):
        for rule in self:
            if rule.domain_filter:
                try:
                    domain = eval(rule.domain_filter)  # noqa: S307
                    if not isinstance(domain, list):
                        raise ValidationError(_('Domain filter must be a list.'))
                except Exception as e:
                    raise ValidationError(
                        _('Invalid domain filter: %s') % str(e)
                    )

    @api.constrains('custom_headers')
    def _check_custom_headers(self):
        for rule in self:
            if rule.custom_headers:
                try:
                    h = json.loads(rule.custom_headers)
                    if not isinstance(h, dict):
                        raise ValidationError(_('Custom headers must be a JSON object.'))
                except json.JSONDecodeError as e:
                    raise ValidationError(
                        _('Invalid headers JSON: %s') % str(e)
                    )

    @api.constrains('target_url')
    def _check_target_url(self):
        for rule in self:
            if rule.target_url and not rule.target_url.startswith(('http://', 'https://')):
                raise ValidationError(
                    _('Target URL must start with http:// or https://')
                )



    @api.model_create_multi
    def create(self, vals_list):
        rules = super().create(vals_list)

        for model_name in set(rules.mapped('model_name')):
            if model_name:
                self.env['ir.model.hook']._patch_model(model_name)

        return rules


    def write(self, vals):
        old_model_names = {
            model_name
            for model_name in self.mapped('model_name')
            if model_name
        }

        result = super().write(vals)

        new_model_names = {
            model_name
            for model_name in self.mapped('model_name')
            if model_name
        }

        for model_name in old_model_names | new_model_names:
            self.env['ir.model.hook']._patch_model(model_name)

        return result
    # ─────────────────────────────────────────────────────
    # Actions
    # ─────────────────────────────────────────────────────
    def action_test_webhook(self):
        """Send a test payload to the target URL."""
        self.ensure_one()
        from odoo.addons.odoo_webhook_engine.services.dispatcher import WebhookDispatcher
        dispatcher = WebhookDispatcher(self.env)
        # Build a sample record
        Model = self.env[self.model_name]
        sample = Model.search([], limit=1)
        if not sample:
            raise ValidationError(
                _('No records found in %s to build a test payload.') % self.model_name
            )
        dispatcher.dispatch(self, sample, self.event_code, test=True)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Test Webhook'),
                'message': _('Test webhook sent. Check the logs.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_view_logs(self):
        """Open log view filtered to this rule."""
        self.ensure_one()
        return {
            'name': _('Webhook Logs'),
            'type': 'ir.actions.act_window',
            'res_model': 'webhook.log',
            'view_mode': 'list,form',
            'domain': [('rule_id', '=', self.id)],
            'context': {'default_rule_id': self.id},
        }