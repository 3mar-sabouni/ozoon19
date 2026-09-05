import json
from datetime import timedelta

from odoo import _, api, fields, models

from .common import DependencyPending, PermanentConnectorError, RetryableConnectorError


class EcommerceIntegrationQueue(models.Model):
    _name = "ecommerce.integration.queue"
    _description = "Ecommerce Sync Queue"
    _order = "priority, id"
    _rec_name = "summary"

    instance_id = fields.Many2one(
        "ecommerce.integration.instance",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        related="instance_id.company_id",
        store=True,
        index=True,
    )
    sync_type = fields.Selection(
        [
            ("category", "Category"),
            ("attribute", "Attribute"),
            ("product", "Product"),
            ("stock", "Stock"),
        ],
        required=True,
        index=True,
    )
    model_name = fields.Char(required=True, index=True)
    res_id = fields.Integer(required=True, index=True)
    summary = fields.Char(compute="_compute_summary")
    priority = fields.Integer(default=50, index=True)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("retry", "Retry"),
            ("done", "Done"),
            ("failed", "Failed"),
        ],
        default="pending",
        required=True,
        index=True,
    )
    attempt_count = fields.Integer(default=0, readonly=True)
    max_attempts = fields.Integer(required=True, default=5)
    next_attempt_at = fields.Datetime(default=fields.Datetime.now, index=True)
    processing_started_at = fields.Datetime(copy=False, index=True)
    last_error = fields.Text(copy=False)
    data_json = fields.Text(copy=False)
    completed_at = fields.Datetime(copy=False, index=True)

    @api.depends("sync_type", "model_name", "res_id")
    def _compute_summary(self):
        for queue in self:
            label = dict(queue._fields["sync_type"].selection).get(queue.sync_type, queue.sync_type)
            record_name = False
            if queue.model_name and queue.res_id:
                try:
                    record = self.env[queue.model_name].browse(queue.res_id).exists()
                except KeyError:
                    record = False
                record_name = record.display_name if record else False
            queue.summary = f"{label}: {record_name or f'{queue.model_name}:{queue.res_id}'}"

    @api.model
    def _default_priority(self, sync_type):
        return {
            "category": 10,
            "attribute": 20,
            "product": 30,
            "stock": 40,
        }.get(sync_type, 50)

    @api.model
    def enqueue(self, instance, sync_type, record, *, priority=None, data=None):
        """Deduplicate active work and revive failed work when a record is queued again."""
        if not instance or not record or not record.exists():
            return self.browse()
        domain = [
            ("instance_id", "=", instance.id),
            ("sync_type", "=", sync_type),
            ("model_name", "=", record._name),
            ("res_id", "=", record.id),
            ("state", "in", ["pending", "retry", "failed"]),
        ]
        existing = self.search(domain, order="id desc", limit=1)
        vals = {
            "priority": priority if priority is not None else self._default_priority(sync_type),
            "next_attempt_at": fields.Datetime.now(),
            "last_error": False,
        }
        if existing and existing.state == "failed":
            vals.update(
                {
                    "state": "retry",
                    "attempt_count": 0,
                    "completed_at": False,
                    "processing_started_at": False,
                    "max_attempts": instance.max_attempts,
                }
            )
        if data is not None:
            vals["data_json"] = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        if existing:
            existing.write(vals)
            return existing
        vals.update(
            {
                "instance_id": instance.id,
                "sync_type": sync_type,
                "model_name": record._name,
                "res_id": record.id,
                "state": "pending",
                "max_attempts": instance.max_attempts,
            }
        )
        return self.create(vals)

    def action_retry(self):
        self.filtered(lambda q: q.state == "failed").write(
            {
                "state": "retry",
                "attempt_count": 0,
                "next_attempt_at": fields.Datetime.now(),
                "last_error": False,
                "completed_at": False,
            }
        )
        return True

    def action_mark_done(self):
        self.write({"state": "done", "completed_at": fields.Datetime.now(), "last_error": False})
        return True

    @api.model
    def _lock_batch(self, instance, *, stock=False, limit=100):
        type_operator = "=" if stock else "!="
        self.env.cr.execute(
            f"""
                SELECT id
                  FROM ecommerce_integration_queue
                 WHERE instance_id = %s
                   AND state IN ('pending', 'retry')
                   AND (next_attempt_at IS NULL OR next_attempt_at <= NOW())
                   AND sync_type {type_operator} 'stock'
                 ORDER BY priority, id
                 FOR UPDATE SKIP LOCKED
                 LIMIT %s
            """,
            (instance.id, limit),
        )
        ids = [row[0] for row in self.env.cr.fetchall()]
        queues = self.browse(ids)
        if queues:
            queues.write({"state": "processing", "processing_started_at": fields.Datetime.now()})
        return queues

    @api.model
    def _cron_process_queue(self):
        stale_before = fields.Datetime.now() - timedelta(minutes=30)
        stale = self.search(
            [("state", "=", "processing"), ("processing_started_at", "<", stale_before)]
        )
        if stale:
            stale.write(
                {
                    "state": "retry",
                    "next_attempt_at": fields.Datetime.now(),
                    "processing_started_at": False,
                    "last_error": _("Recovered a stale processing job."),
                }
            )

        instances = self.env["ecommerce.integration.instance"].search([("active", "=", True)])
        for instance in instances:
            non_stock = self._lock_batch(instance, stock=False, limit=instance.queue_batch_size)
            for queue in non_stock:
                self._process_single(queue)

            stock_queues = self._lock_batch(instance, stock=True, limit=instance.stock_batch_size)
            if stock_queues:
                self._process_stock_batch(instance, stock_queues)
        return True

    def _get_record(self, queue):
        if queue.model_name not in self.env:
            raise PermanentConnectorError(_("Unknown Odoo model %s.") % queue.model_name)
        record = self.env[queue.model_name].browse(queue.res_id).exists()
        if not record:
            raise PermanentConnectorError(_("The Odoo record was deleted before it could be synchronized."))
        return record

    def _record_is_in_scope(self, instance, queue, record):
        if queue.sync_type == "category":
            return instance._category_should_sync(record)
        if queue.sync_type == "product":
            return instance._template_should_sync(record)
        if queue.sync_type == "attribute":
            return instance._attribute_should_sync(record)
        if queue.sync_type == "stock":
            return bool(record.active and instance._template_should_sync(record.product_tmpl_id))
        return True

    def _mark_skipped(self, queue, reason, attempt):
        queue.write(
            {
                "state": "done",
                "completed_at": fields.Datetime.now(),
                "processing_started_at": False,
                "last_error": False,
            }
        )
        self._create_log(
            queue,
            status="warning",
            summary=_("Synchronization skipped"),
            error=reason,
            attempt=attempt,
        )

    def _process_single(self, queue):
        instance = queue.instance_id
        attempt = queue.attempt_count + 1
        queue.write({"attempt_count": attempt})
        payload = None
        response = None
        http_status = None
        duration_ms = 0
        try:
            record = self._get_record(queue)
            if not self._record_is_in_scope(instance, queue, record):
                self._mark_skipped(
                    queue,
                    _("Record is not currently published to this ecommerce instance."),
                    attempt,
                )
                return
            with self.env.cr.savepoint():
                if queue.sync_type == "category":
                    payload, response, http_status, duration_ms = instance._sync_category(record)
                elif queue.sync_type == "product":
                    payload, response, http_status, duration_ms = instance._sync_product(record)
                elif queue.sync_type == "attribute":
                    payload, response, http_status, duration_ms = instance._sync_attribute_local(record)
                else:
                    raise PermanentConnectorError(_("Unsupported queue type %s.") % queue.sync_type)
        except DependencyPending as exc:
            self._schedule_retry(queue, str(exc), dependency=True)
            self._create_log(
                queue,
                status="warning",
                summary=_("Waiting for dependency"),
                payload=payload,
                response=response,
                error=str(exc),
                attempt=attempt,
            )
            return
        except RetryableConnectorError as exc:
            self._schedule_retry(queue, str(exc))
            self._create_log(
                queue,
                status="failure",
                summary=_("Retryable synchronization failure"),
                payload=payload,
                response=exc.response_text,
                error=str(exc),
                http_status=exc.status_code,
                attempt=attempt,
            )
            instance._touch_failure(str(exc))
            return
        except PermanentConnectorError as exc:
            self._mark_failed(queue, str(exc))
            self._create_log(
                queue,
                status="failure",
                summary=_("Synchronization failed"),
                payload=payload,
                response=exc.response_text,
                error=str(exc),
                http_status=exc.status_code,
                attempt=attempt,
            )
            instance._touch_failure(str(exc))
            return
        except Exception as exc:  # Defensive boundary: cron must continue with other jobs.
            self._schedule_retry(queue, str(exc))
            self._create_log(
                queue,
                status="failure",
                summary=_("Unexpected synchronization error"),
                payload=payload,
                response=response,
                error=str(exc),
                attempt=attempt,
            )
            instance._touch_failure(str(exc))
            return

        queue.write(
            {
                "state": "done",
                "completed_at": fields.Datetime.now(),
                "processing_started_at": False,
                "last_error": False,
            }
        )
        self._create_log(
            queue,
            status="success",
            summary=_("Synchronization completed"),
            payload=payload,
            response=response,
            http_status=http_status,
            duration_ms=duration_ms,
            attempt=attempt,
        )
        instance._touch_success()

    def _process_stock_batch(self, instance, queues):
        attempt_by_queue = {}
        ready = self.browse()
        variants = self.env["product.product"]

        for queue in queues:
            attempt = queue.attempt_count + 1
            attempt_by_queue[queue.id] = attempt
            queue.attempt_count = attempt
            try:
                variant = self._get_record(queue)
            except PermanentConnectorError as exc:
                self._mark_failed(queue, str(exc))
                self._create_log(
                    queue,
                    status="failure",
                    summary=_("Stock synchronization failed"),
                    error=str(exc),
                    attempt=attempt,
                )
                continue

            if not self._record_is_in_scope(instance, queue, variant):
                self._mark_skipped(
                    queue,
                    _("Product is not currently published to this ecommerce instance."),
                    attempt,
                )
                continue

            template_binding = self.env["ecommerce.integration.binding"].search(
                [
                    ("instance_id", "=", instance.id),
                    ("model_name", "=", "product.template"),
                    ("res_id", "=", variant.product_tmpl_id.id),
                    ("sync_state", "=", "synced"),
                ],
                limit=1,
            )
            variant_binding = self.env["ecommerce.integration.binding"].search(
                [
                    ("instance_id", "=", instance.id),
                    ("model_name", "=", "product.product"),
                    ("res_id", "=", variant.id),
                    ("sync_state", "=", "synced"),
                ],
                limit=1,
            )
            if not template_binding or not variant_binding:
                self.enqueue(instance, "product", variant.product_tmpl_id, priority=30)
                self._schedule_retry(queue, _("Product must be synchronized before stock."), dependency=True)
                self._create_log(
                    queue,
                    status="warning",
                    summary=_("Stock waiting for product mapping"),
                    error=_("Product must be synchronized before stock."),
                    attempt=attempt,
                )
                continue
            ready |= queue
            variants |= variant

        if not ready:
            return

        quantities = instance._variant_quantities(variants)
        updates = [
            {
                "odoo_variant_id": self.env[q.model_name].browse(q.res_id).id,
                "quantity": quantities.get(q.res_id, 0.0),
            }
            for q in ready
        ]
        payload = {"updates": updates}
        try:
            response, http_status, duration_ms = instance._request_json(instance.stock_endpoint, payload)
        except RetryableConnectorError as exc:
            for queue in ready:
                self._schedule_retry(queue, str(exc))
                item_payload = {"updates": [next(item for item in updates if item["odoo_variant_id"] == queue.res_id)]}
                self._create_log(
                    queue,
                    status="failure",
                    summary=_("Retryable stock synchronization failure"),
                    payload=item_payload,
                    response=exc.response_text,
                    error=str(exc),
                    http_status=exc.status_code,
                    attempt=attempt_by_queue[queue.id],
                )
            instance._touch_failure(str(exc))
            return
        except PermanentConnectorError as exc:
            for queue in ready:
                self._mark_failed(queue, str(exc))
                item_payload = {"updates": [next(item for item in updates if item["odoo_variant_id"] == queue.res_id)]}
                self._create_log(
                    queue,
                    status="failure",
                    summary=_("Stock synchronization failed"),
                    payload=item_payload,
                    response=exc.response_text,
                    error=str(exc),
                    http_status=exc.status_code,
                    attempt=attempt_by_queue[queue.id],
                )
            instance._touch_failure(str(exc))
            return
        except Exception as exc:
            for queue in ready:
                self._schedule_retry(queue, str(exc))
                self._create_log(
                    queue,
                    status="failure",
                    summary=_("Unexpected stock synchronization error"),
                    error=str(exc),
                    attempt=attempt_by_queue[queue.id],
                )
            instance._touch_failure(str(exc))
            return

        results = {
            item.get("odoo_variant_id"): item
            for item in response.get("results", [])
            if item.get("odoo_variant_id")
        }
        for queue in ready:
            item = results.get(queue.res_id, {"status": "error", "reason": "Missing item result"})
            item_payload = {"updates": [next(value for value in updates if value["odoo_variant_id"] == queue.res_id)]}
            if item.get("status") == "updated":
                queue.write(
                    {
                        "state": "done",
                        "completed_at": fields.Datetime.now(),
                        "processing_started_at": False,
                        "last_error": False,
                    }
                )
                self._create_log(
                    queue,
                    status="success",
                    summary=_("Stock synchronized"),
                    payload=item_payload,
                    response=item,
                    http_status=http_status,
                    duration_ms=duration_ms,
                    attempt=attempt_by_queue[queue.id],
                )
            else:
                variant = self.env[queue.model_name].browse(queue.res_id).exists()
                if variant:
                    self.enqueue(instance, "product", variant.product_tmpl_id, priority=30)
                reason = item.get("reason") or _("Remote variant is not mapped yet.")
                self._schedule_retry(queue, reason, dependency=True)
                self._create_log(
                    queue,
                    status="warning",
                    summary=_("Stock mapping not ready"),
                    payload=item_payload,
                    response=item,
                    http_status=http_status,
                    duration_ms=duration_ms,
                    error=reason,
                    attempt=attempt_by_queue[queue.id],
                )
        if any(queue.state != "done" for queue in ready):
            instance._touch_failure(_("One or more stock items were not synchronized."))
        else:
            instance._touch_success()

    def _schedule_retry(self, queue, message, *, dependency=False):
        if queue.attempt_count >= queue.max_attempts:
            self._mark_failed(queue, message)
            return
        delay_seconds = 15 if dependency else min(60 * (2 ** max(queue.attempt_count - 1, 0)), 3600)
        queue.write(
            {
                "state": "retry",
                "next_attempt_at": fields.Datetime.now() + timedelta(seconds=delay_seconds),
                "processing_started_at": False,
                "last_error": message,
            }
        )

    def _mark_failed(self, queue, message):
        queue.write(
            {
                "state": "failed",
                "completed_at": fields.Datetime.now(),
                "processing_started_at": False,
                "last_error": message,
            }
        )

    def _create_log(
        self,
        queue,
        *,
        status,
        summary,
        payload=None,
        response=None,
        error=None,
        http_status=None,
        duration_ms=0,
        attempt=1,
    ):
        instance = queue.instance_id
        vals = {
            "instance_id": instance.id,
            "queue_id": queue.id,
            "sync_type": queue.sync_type,
            "direction": "out",
            "status": status,
            "model_name": queue.model_name,
            "res_id": queue.res_id,
            "summary": summary,
            "http_status": http_status,
            "attempt": attempt,
            "duration_ms": duration_ms or 0,
            "error_message": error,
        }
        if payload is not None:
            vals["request_json"] = instance.json_text(payload)
        if response is not None:
            if isinstance(response, str):
                vals["response_json"] = response[:20000]
            else:
                vals["response_json"] = instance.json_text(response)
        self.env["ecommerce.integration.log"].sudo().create(vals)
