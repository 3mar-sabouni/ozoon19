# -*- coding: utf-8 -*-
"""
Payload builder — converts an Odoo record into a JSON-serializable dict
based on the webhook rule's payload configuration.
"""

import json
import logging
from datetime import date, datetime

from odoo.fields import Date, Datetime

_logger = logging.getLogger(__name__)


def _serialize_value(value):
    """Convert Odoo field values to JSON-safe types."""
    if value is False or value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return value


class PayloadBuilder:
    """Builds outgoing webhook payloads from Odoo records."""

    def __init__(self, env):
        self.env = env

    def build(self, rule, record, event_code):
        """
        Build payload dict based on rule.payload_mode.

        :param rule: webhook.rule record
        :param record: Odoo record that triggered the event
        :param event_code: str event code
        :return: dict ready for JSON serialization
        """
        mode = rule.payload_mode
        if mode == 'full':
            return self._build_full(rule, record, event_code)
        elif mode == 'fields':
            return self._build_fields(rule, record, event_code)
        elif mode == 'template':
            return self._build_template(rule, record, event_code)
        return {}

    def build_from_snapshot(self, rule, snapshot, event_code):
        """Build payload from a pre-deletion snapshot dict."""
        return {
            'event': event_code,
            'model': rule.model_name,
            'data': snapshot,
            'timestamp': datetime.utcnow().isoformat(),
        }

    # ─────────────────────────────────────────────────────
    # Full mode — all readable fields
    # ─────────────────────────────────────────────────────
    def _build_full(self, rule, record, event_code):
        data = {}
        for fname, field in record._fields.items():
            if field.type in ('binary',):
                continue  # skip binary fields by default
            try:
                val = record[fname]
                if field.type == 'many2one':
                    data[fname] = {
                        'id': val.id,
                        'display_name': val.display_name,
                    } if val else None
                elif field.type in ('one2many', 'many2many'):
                    data[fname] = [{'id': r.id, 'display_name': r.display_name} for r in val]
                else:
                    data[fname] = _serialize_value(val)
            except Exception:
                continue

        return {
            'event': event_code,
            'model': rule.model_name,
            'record_id': record.id,
            'data': data,
            'timestamp': datetime.utcnow().isoformat(),
        }

    # ─────────────────────────────────────────────────────
    # Fields mode — hand-picked fields
    # ─────────────────────────────────────────────────────
    def _build_fields(self, rule, record, event_code):
        data = {}
        for pf in rule.payload_field_ids:
            key = pf.json_key or pf.field_name
            field_obj = record._fields.get(pf.field_name)
            if not field_obj:
                continue

            val = record[pf.field_name]

            if field_obj.type == 'many2one':
                if pf.include_relation and val:
                    data[key] = self._read_relation(val, pf.relation_fields)
                else:
                    data[key] = {'id': val.id, 'display_name': val.display_name} if val else None

            elif field_obj.type in ('one2many', 'many2many'):
                if pf.include_relation and val:
                    data[key] = [self._read_relation(r, pf.relation_fields) for r in val]
                else:
                    data[key] = [{'id': r.id, 'display_name': r.display_name} for r in val]
            else:
                data[key] = _serialize_value(val)

        return {
            'event': event_code,
            'model': rule.model_name,
            'record_id': record.id,
            'data': data,
            'timestamp': datetime.utcnow().isoformat(),
        }

    def _read_relation(self, record, relation_fields_str):
        """Read specific fields from a related record."""
        result = {'id': record.id}
        if relation_fields_str:
            fields_list = [f.strip() for f in relation_fields_str.split(',') if f.strip()]
        else:
            fields_list = ['display_name']

        for fname in fields_list:
            try:
                result[fname] = _serialize_value(record[fname])
            except Exception:
                result[fname] = None
        return result

    # ─────────────────────────────────────────────────────
    # Template mode — Jinja2
    # ─────────────────────────────────────────────────────
    def _build_template(self, rule, record, event_code):
        try:
            import jinja2
        except ImportError:
            _logger.error("jinja2 is required for template payload mode.")
            return {'error': 'jinja2 not installed'}

        try:
            env = jinja2.Environment(
                undefined=jinja2.StrictUndefined,
                autoescape=False,
            )
            template = env.from_string(rule.payload_template or '{}')
            rendered = template.render(
                record=record,
                event=event_code,
                env=self.env,
                timestamp=datetime.utcnow().isoformat(),
            )
            return json.loads(rendered)
        except Exception as e:
            _logger.exception("Webhook payload template error: %s", e)
            return {
                'error': str(e),
                'event': event_code,
                'record_id': record.id,
            }
