# -*- coding: utf-8 -*-

import ast
import logging

from odoo import SUPERUSER_ID, api, models


_logger = logging.getLogger(__name__)


# Models already patched in the current Python process.
# The key contains the registry ID because Odoo can serve multiple databases.
_PATCHED_MODELS = set()

# Also store a marker directly on the model class.
# This prevents accidental nested hooks after a module/registry reload.
_PATCH_MARKER = '_odoo_webhook_engine_patched'


class IrModelHook(models.AbstractModel):
    """
    Installs ORM hooks on models used by outgoing webhook rules.

    The hooks intercept:

    - create()
    - write()
    - unlink()

    For stock.quant updates, repeated writes inside the same database
    transaction are grouped into one final webhook after commit.
    """

    _name = 'ir.model.hook'
    _description = 'Webhook ORM Hook Installer'

    # ─────────────────────────────────────────────────────────
    # Hook installation
    # ─────────────────────────────────────────────────────────

    @api.model
    def _register_hook(self):
        """
        Called when the Odoo registry loads.

        Existing active webhook rules are automatically installed again
        after every full Odoo restart.
        """
        result = super()._register_hook()

        try:
            self._install_hooks()
        except Exception:
            # This can happen during the module's first installation,
            # before all webhook tables are completely available.
            _logger.exception(
                "Webhook: failed to install hooks during registry loading."
            )

        return result

    @api.model
    def _install_hooks(self):
        """Install hooks for every model having an active webhook rule."""

        rules = self.env['webhook.rule'].sudo().search([
            ('active', '=', True),
            ('model_name', '!=', False),
        ])

        model_names = {
            model_name
            for model_name in rules.mapped('model_name')
            if model_name
        }

        for model_name in model_names:
            self._patch_model(model_name)

        _logger.warning(
            "Webhook: hook installation completed. Models=%s",
            sorted(model_names),
        )

        return True

    @api.model
    def _patch_model(self, model_name):
        """
        Patch create, write and unlink for one model.

        All three methods are patched together. Active rules are searched
        dynamically whenever an event happens.
        """
        if not model_name:
            return False

        patch_key = (
            id(self.env.registry),
            model_name,
        )

        if patch_key in _PATCHED_MODELS:
            return True

        model_recordset = self.env.get(model_name)

        if model_recordset is None:
            _logger.warning(
                "Webhook: model '%s' was not found.",
                model_name,
            )
            return False

        model_class = type(model_recordset)

        # Prevent wrapping a method more than once.
        if model_class.__dict__.get(_PATCH_MARKER, False):
            _logger.info(
                "Webhook: model '%s' is already patched.",
                model_name,
            )

            _PATCHED_MODELS.add(patch_key)
            return True

        original_create = model_class.create
        original_write = model_class.write
        original_unlink = model_class.unlink

        # ─────────────────────────────────────────────────────
        # CREATE
        # ─────────────────────────────────────────────────────

        @api.model_create_multi
        def webhook_create(self_model, vals_list):
            records = original_create(
                self_model,
                vals_list,
            )

            if self_model.env.context.get('skip_webhook'):
                return records

            try:
                self_model.env['ir.model.hook']._fire_event(
                    event_code='on_create',
                    model_name=model_name,
                    records=records,
                )
            except Exception:
                _logger.exception(
                    "Webhook: on_create failed for model '%s'.",
                    model_name,
                )

            return records

        # ─────────────────────────────────────────────────────
        # WRITE
        # ─────────────────────────────────────────────────────

        def webhook_write(self_model, vals):
            if self_model.env.context.get('skip_webhook'):
                return original_write(
                    self_model,
                    vals,
                )

            old_states = {}

            # Save previous values needed by state-change rules.
            state_rules = self_model.env['webhook.rule'].sudo().search([
                ('model_name', '=', model_name),
                ('event_code', '=', 'on_state_change'),
                ('active', '=', True),
            ])

            state_fields = {
                field_name
                for field_name in state_rules.mapped('state_field')
                if field_name
            }

            for record in self_model:
                record_states = {}

                for field_name in state_fields:
                    if (
                        field_name in vals
                        and field_name in record._fields
                    ):
                        record_states[field_name] = record[field_name]

                if record_states:
                    old_states[record.id] = record_states

            result = original_write(
                self_model,
                vals,
            )

            changed_fields = list(vals.keys())

            _logger.info(
                "WEBHOOK WRITE | model=%s | ids=%s | fields=%s",
                model_name,
                self_model.ids,
                changed_fields,
            )

            try:
                self_model.env['ir.model.hook']._fire_event(
                    event_code='on_write',
                    model_name=model_name,
                    records=self_model,
                    changed_fields=changed_fields,
                )

                if old_states:
                    self_model.env['ir.model.hook']._fire_event(
                        event_code='on_state_change',
                        model_name=model_name,
                        records=self_model,
                        old_states=old_states,
                        vals=vals,
                    )

            except Exception:
                _logger.exception(
                    "Webhook: write event failed for model '%s'.",
                    model_name,
                )

            return result

        # ─────────────────────────────────────────────────────
        # UNLINK
        # ─────────────────────────────────────────────────────

        def webhook_unlink(self_model):
            if self_model.env.context.get('skip_webhook'):
                return original_unlink(self_model)

            # Records cannot be read after unlink, so preserve basic data.
            snapshots = [
                {
                    'id': record.id,
                    'display_name': record.display_name,
                }
                for record in self_model
            ]

            result = original_unlink(self_model)

            try:
                self_model.env['ir.model.hook']._fire_event(
                    event_code='on_unlink',
                    model_name=model_name,
                    records=self_model,
                    snapshot=snapshots,
                )
            except Exception:
                _logger.exception(
                    "Webhook: on_unlink failed for model '%s'.",
                    model_name,
                )

            return result

        # Apply hooks.
        model_class.create = webhook_create
        model_class.write = webhook_write
        model_class.unlink = webhook_unlink

        setattr(
            model_class,
            _PATCH_MARKER,
            True,
        )

        _PATCHED_MODELS.add(patch_key)

        _logger.warning(
            "Webhook: create/write/unlink hooked for model '%s'.",
            model_name,
        )

        return True

    # ─────────────────────────────────────────────────────────
    # Quant update grouping
    # ─────────────────────────────────────────────────────────

    @api.model
    def _queue_final_dispatch(self, rule, record, event_code):
        """
        Queue one final webhook per rule/record/event/transaction.

        Odoo may write stock.quant several times during one inventory
        operation. This method sends only the final committed state.
        """
        cursor = self.env.cr

        pending_events = getattr(
            cursor,
            '_webhook_pending_events',
            None,
        )

        if pending_events is None:
            pending_events = set()

            setattr(
                cursor,
                '_webhook_pending_events',
                pending_events,
            )

        event_key = (
            rule.id,
            record._name,
            record.id,
            event_code,
        )

        if event_key in pending_events:
            _logger.debug(
                "Webhook: duplicate queued event skipped: %s",
                event_key,
            )
            return False

        pending_events.add(event_key)

        registry = self.env.registry
        rule_id = rule.id
        model_name = record._name
        record_id = record.id

        def dispatch_after_commit():
            """
            Execute with a new cursor because the original transaction
            has already committed.
            """
            try:
                with registry.cursor() as new_cursor:
                    new_env = api.Environment(
                        new_cursor,
                        SUPERUSER_ID,
                        {},
                    )

                    final_rule = (
                        new_env['webhook.rule']
                        .sudo()
                        .browse(rule_id)
                        .exists()
                    )

                    final_record = (
                        new_env[model_name]
                        .sudo()
                        .browse(record_id)
                        .exists()
                    )

                    if not final_rule:
                        return

                    if not final_rule.active:
                        return

                    if final_rule.model_name != model_name:
                        return

                    if final_rule.event_code != event_code:
                        return

                    if not final_record:
                        return

                    from odoo.addons.odoo_webhook_engine.services.dispatcher import (
                        WebhookDispatcher,
                    )

                    WebhookDispatcher(new_env).dispatch(
                        final_rule,
                        final_record,
                        event_code,
                    )

                    # The webhook log is created using this new cursor.
                    new_cursor.commit()

            except Exception:
                _logger.exception(
                    "Webhook: post-commit dispatch failed. "
                    "Rule=%s model=%s record=%s event=%s",
                    rule_id,
                    model_name,
                    record_id,
                    event_code,
                )

        cursor.postcommit.add(dispatch_after_commit)

        return True

    # ─────────────────────────────────────────────────────────
    # Event processing
    # ─────────────────────────────────────────────────────────

    @api.model
    def _fire_event(
        self,
        event_code,
        model_name,
        records,
        **kwargs,
    ):
        """Find matching rules and dispatch their webhooks."""

        rules = self.env['webhook.rule'].sudo().search([
            ('model_name', '=', model_name),
            ('event_code', '=', event_code),
            ('active', '=', True),
        ])

        _logger.info(
            "WEBHOOK EVENT | event=%s | model=%s | rules=%s",
            event_code,
            model_name,
            rules.mapped('name'),
        )

        if not rules:
            return False

        from odoo.addons.odoo_webhook_engine.services.dispatcher import (
            WebhookDispatcher,
        )

        dispatcher = WebhookDispatcher(self.env)

        for rule in rules:
            filtered_records = self._filter_records(
                rule=rule,
                event_code=event_code,
                records=records,
                snapshot=kwargs.get('snapshot', []),
            )

            if not filtered_records:
                continue

            # Only run an on_write rule when one of its watched fields
            # actually appears in vals.
            if (
                event_code == 'on_write'
                and rule.watched_fields
            ):
                watched_fields = {
                    field_name.strip()
                    for field_name in rule.watched_fields.split(',')
                    if field_name.strip()
                }

                changed_fields = set(
                    kwargs.get('changed_fields', [])
                )

                if not watched_fields.intersection(changed_fields):
                    _logger.debug(
                        "Webhook: rule '%s' skipped. "
                        "Watched=%s Changed=%s",
                        rule.name,
                        sorted(watched_fields),
                        sorted(changed_fields),
                    )
                    continue

            # Optional destination state check.
            if (
                event_code == 'on_state_change'
                and rule.state_value
            ):
                vals = kwargs.get('vals', {})
                new_value = vals.get(rule.state_field)

                if str(new_value) != str(rule.state_value):
                    continue

            # Deleted records use their pre-unlink snapshot.
            if event_code == 'on_unlink':
                snapshots = (
                    filtered_records
                    if isinstance(filtered_records, list)
                    else [filtered_records]
                )

                for snapshot in snapshots:
                    dispatcher.dispatch_raw(
                        rule,
                        snapshot,
                        event_code,
                    )

                continue

            for record in filtered_records:
                # Group repeated stock.quant updates and send the final
                # state only after the transaction commits.
                if (
                    model_name == 'stock.quant'
                    and event_code == 'on_write'
                ):
                    self._queue_final_dispatch(
                        rule,
                        record,
                        event_code,
                    )
                else:
                    dispatcher.dispatch(
                        rule,
                        record,
                        event_code,
                    )

        return True

    # ─────────────────────────────────────────────────────────
    # Domain filtering
    # ─────────────────────────────────────────────────────────

    @api.model
    def _filter_records(
        self,
        rule,
        event_code,
        records,
        snapshot=None,
    ):
        """Apply the rule domain to its records."""

        snapshot = snapshot or []

        domain_text = (
            rule.domain_filter.strip()
            if rule.domain_filter
            else '[]'
        )

        if event_code == 'on_unlink':
            # Full domain evaluation is not possible after deletion because
            # only the prepared snapshot remains.
            return snapshot

        if not domain_text or domain_text == '[]':
            return records

        try:
            domain = ast.literal_eval(domain_text)

            if not isinstance(domain, list):
                _logger.error(
                    "Webhook: domain is not a list. Rule=%s Domain=%s",
                    rule.name,
                    domain_text,
                )
                return records.browse()

            return records.filtered_domain(domain)

        except Exception:
            _logger.exception(
                "Webhook: invalid domain '%s' on rule '%s'.",
                domain_text,
                rule.name,
            )

            return records.browse()