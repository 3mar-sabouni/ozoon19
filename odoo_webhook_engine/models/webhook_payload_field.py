# -*- coding: utf-8 -*-

from odoo import models, fields, api


class WebhookPayloadField(models.Model):
    """Defines which fields to include in outgoing webhook payload."""
    _name = 'webhook.payload.field'
    _description = 'Webhook Payload Field'
    _order = 'sequence, id'

    rule_id = fields.Many2one(
        'webhook.rule', string='Webhook Rule',
        required=True, ondelete='cascade',
    )
    sequence = fields.Integer(default=10)
    field_id = fields.Many2one(
        'ir.model.fields', string='Field',
        domain="[('model_id', '=', parent.model_id)]",
        required=True, ondelete='cascade',
    )
    field_name = fields.Char(related='field_id.name', store=True, readonly=True)
    field_type = fields.Selection(related='field_id.ttype', store=True, readonly=True)
    json_key = fields.Char(
        string='JSON Key',
        help='Custom key name in JSON payload. Defaults to field name.',
    )
    include_relation = fields.Boolean(
        string='Include Related Data',
        help='For relational fields (Many2one, One2many, Many2many), include nested data instead of just IDs.',
    )
    relation_fields = fields.Char(
        string='Relation Fields',
        help='Comma-separated field names to include from the related model. e.g. "name,email,phone"',
    )

    @api.onchange('field_id')
    def _onchange_field_id(self):
        if self.field_id and not self.json_key:
            self.json_key = self.field_id.name
