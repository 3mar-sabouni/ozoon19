from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class EcommerceIntegrationDashboard(models.Model):
    _inherit = "ecommerce.integration.instance"

    @api.model
    def get_dashboard_bootstrap(self):
        """Return the lightweight data required to open the OWL dashboard.

        The first active instance visible to the current user is selected by default.
        If all instances are disabled, the first visible instance is used instead.
        The default period is the current month in the user's Odoo timezone.
        """
        instances = self.search([("active", "=", True)], order="name, id")
        if not instances:
            instances = self.search([], order="name, id")

        today = fields.Date.context_today(self)
        month_start = today.replace(day=1)

        return {
            "instances": [
                {
                    "id": instance.id,
                    "name": instance.name,
                    "code": instance.code,
                    "company": instance.company_id.display_name,
                    "health": instance.health,
                    "active": instance.active,
                }
                for instance in instances
            ],
            "default_instance_id": instances[0].id if instances else False,
            "default_date_from": fields.Date.to_string(month_start),
            "default_date_to": fields.Date.to_string(today),
        }

    @api.model
    def get_dashboard_data(self, instance_id, date_from, date_to):
        """Return all data used by the full-screen integration dashboard.

        Heavy transaction aggregates are calculated directly in PostgreSQL after the
        selected instance is resolved through normal Odoo record rules. This keeps the
        dashboard responsive even when the log table becomes large while preserving
        the connector's multi-company access boundary.
        """
        instance = self.search([("id", "=", int(instance_id or 0))], limit=1)
        if not instance:
            raise UserError(_("The selected ecommerce instance is not available."))

        date_from_value, date_to_value = self._dashboard_validate_dates(date_from, date_to)
        utc_from, utc_to = self._dashboard_utc_bounds(date_from_value, date_to_value)

        log_summary = self._dashboard_log_summary(
            instance, utc_from, utc_to, date_from_value, date_to_value
        )
        queue = self._dashboard_queue_snapshot(instance)
        bindings = self._dashboard_binding_snapshot(instance)
        publications = self._dashboard_publication_snapshot(instance)
        recent = self._dashboard_recent_logs(instance, utc_from, utc_to)

        return {
            "instance": {
                "id": instance.id,
                "name": instance.name,
                "code": instance.code,
                "active": instance.active,
                "health": instance.health,
                "connector_type": "Generic REST",
                "company": instance.company_id.display_name,
                "warehouse": instance.warehouse_id.display_name,
                "pricelist": instance.pricelist_id.display_name or _("Standard Sales Price"),
                "source_currency": instance.source_currency_id.name,
                "target_currency": instance.target_currency_id.name,
                "last_success_at": fields.Datetime.to_string(instance.last_success_at)
                if instance.last_success_at
                else False,
                "last_failure_at": fields.Datetime.to_string(instance.last_failure_at)
                if instance.last_failure_at
                else False,
                "last_failure_message": instance.last_failure_message or False,
                "timeout_seconds": instance.timeout_seconds,
                "max_attempts": instance.max_attempts,
                "queue_batch_size": instance.queue_batch_size,
                "stock_batch_size": instance.stock_batch_size,
                "auto_sync_category": instance.auto_sync_category,
                "auto_sync_product": instance.auto_sync_product,
                "auto_sync_stock": instance.auto_sync_stock,
                "inbound_orders_enabled": instance.inbound_orders_enabled,
            },
            "period": {
                "date_from": fields.Date.to_string(date_from_value),
                "date_to": fields.Date.to_string(date_to_value),
                "utc_from": fields.Datetime.to_string(utc_from),
                "utc_to": fields.Datetime.to_string(utc_to),
            },
            "logs": log_summary,
            "queue": queue,
            "bindings": bindings,
            "publications": publications,
            "recent": recent,
            "generated_at": fields.Datetime.to_string(fields.Datetime.now()),
        }

    def _dashboard_validate_dates(self, date_from, date_to):
        try:
            date_from_value = fields.Date.to_date(date_from)
            date_to_value = fields.Date.to_date(date_to)
        except (TypeError, ValueError):
            raise ValidationError(_("Please select a valid dashboard date range."))
        if not date_from_value or not date_to_value:
            raise ValidationError(_("Dashboard From and To dates are required."))
        if date_from_value > date_to_value:
            raise ValidationError(_("Dashboard From date cannot be after the To date."))
        if (date_to_value - date_from_value).days > 730:
            raise ValidationError(_("Dashboard date range cannot exceed two years."))
        return date_from_value, date_to_value

    def _dashboard_utc_bounds(self, date_from, date_to):
        """Convert inclusive user-local dates to a [UTC start, UTC end) interval."""
        tz_name = self.env.user.tz or "UTC"
        try:
            user_tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            user_tz = pytz.UTC
            tz_name = "UTC"

        local_from = user_tz.localize(datetime.combine(date_from, time.min))
        local_to = user_tz.localize(datetime.combine(date_to + timedelta(days=1), time.min))
        utc_from = local_from.astimezone(pytz.UTC).replace(tzinfo=None)
        utc_to = local_to.astimezone(pytz.UTC).replace(tzinfo=None)
        return utc_from, utc_to

    def _dashboard_log_summary(self, instance, utc_from, utc_to, date_from, date_to):
        cr = self.env.cr
        base_params = (instance.id, utc_from, utc_to)

        cr.execute(
            """
                SELECT status,
                       COUNT(*)::int AS count,
                       COALESCE(SUM(duration_ms), 0)::bigint AS total_duration
                  FROM ecommerce_integration_log
                 WHERE instance_id = %s
                   AND create_date >= %s
                   AND create_date < %s
                 GROUP BY status
            """,
            base_params,
        )
        status_counts = {"success": 0, "warning": 0, "failure": 0}
        total_duration = 0
        total = 0
        for status, count, duration_sum in cr.fetchall():
            status_counts[status] = count
            total += count
            total_duration += int(duration_sum or 0)

        success_rate = round((status_counts["success"] / total) * 100, 1) if total else 0.0
        avg_duration_ms = round(total_duration / total) if total else 0

        cr.execute(
            """
                SELECT sync_type, status, COUNT(*)::int
                  FROM ecommerce_integration_log
                 WHERE instance_id = %s
                   AND create_date >= %s
                   AND create_date < %s
                 GROUP BY sync_type, status
                 ORDER BY sync_type, status
            """,
            base_params,
        )
        types = defaultdict(lambda: {"success": 0, "warning": 0, "failure": 0})
        for sync_type, status, count in cr.fetchall():
            types[sync_type][status] = count

        type_labels = dict(self.env["ecommerce.integration.log"]._fields["sync_type"].selection)
        type_rows = []
        for sync_type in ["category", "attribute", "product", "stock", "order", "order_status"]:
            counts = types[sync_type]
            row_total = sum(counts.values())
            type_rows.append(
                {
                    "key": sync_type,
                    "label": type_labels.get(sync_type, sync_type),
                    "success": counts["success"],
                    "warning": counts["warning"],
                    "failure": counts["failure"],
                    "total": row_total,
                }
            )

        tz_name = self.env.user.tz or "UTC"
        try:
            pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz_name = "UTC"
        cr.execute(
            """
                SELECT (create_date AT TIME ZONE 'UTC' AT TIME ZONE %s)::date AS local_day,
                       status,
                       COUNT(*)::int
                  FROM ecommerce_integration_log
                 WHERE instance_id = %s
                   AND create_date >= %s
                   AND create_date < %s
                 GROUP BY local_day, status
                 ORDER BY local_day
            """,
            (tz_name, instance.id, utc_from, utc_to),
        )
        daily = defaultdict(lambda: {"success": 0, "warning": 0, "failure": 0})
        for day, status, count in cr.fetchall():
            daily[day][status] = count
        trend = []
        day = date_from
        while day <= date_to:
            counts = daily[day]
            trend.append(
                {
                    "date": fields.Date.to_string(day),
                    "success": counts["success"],
                    "warning": counts["warning"],
                    "failure": counts["failure"],
                    "total": sum(counts.values()),
                }
            )
            day += timedelta(days=1)

        cr.execute(
            """
                SELECT http_status, COUNT(*)::int
                  FROM ecommerce_integration_log
                 WHERE instance_id = %s
                   AND create_date >= %s
                   AND create_date < %s
                   AND http_status IS NOT NULL
                 GROUP BY http_status
                 ORDER BY COUNT(*) DESC, http_status
                 LIMIT 8
            """,
            base_params,
        )
        http_statuses = [{"code": code, "count": count} for code, count in cr.fetchall()]

        cr.execute(
            """
                SELECT COALESCE(NULLIF(error_message, ''), NULLIF(summary, ''), 'Unknown error') AS error,
                       COUNT(*)::int
                  FROM ecommerce_integration_log
                 WHERE instance_id = %s
                   AND create_date >= %s
                   AND create_date < %s
                   AND status = 'failure'
                 GROUP BY error
                 ORDER BY COUNT(*) DESC, error
                 LIMIT 5
            """,
            base_params,
        )
        top_errors = [
            {"message": (message or _("Unknown error"))[:220], "count": count}
            for message, count in cr.fetchall()
        ]

        return {
            "total": total,
            "success": status_counts["success"],
            "warning": status_counts["warning"],
            "failure": status_counts["failure"],
            "success_rate": success_rate,
            "avg_duration_ms": avg_duration_ms,
            "by_type": type_rows,
            "trend": trend,
            "http_statuses": http_statuses,
            "top_errors": top_errors,
        }

    def _dashboard_queue_snapshot(self, instance):
        cr = self.env.cr
        cr.execute(
            """
                SELECT state, COUNT(*)::int
                  FROM ecommerce_integration_queue
                 WHERE instance_id = %s
                 GROUP BY state
            """,
            (instance.id,),
        )
        counts = {"pending": 0, "processing": 0, "retry": 0, "done": 0, "failed": 0}
        for state, count in cr.fetchall():
            counts[state] = count

        cr.execute(
            """
                SELECT MIN(create_date)
                  FROM ecommerce_integration_queue
                 WHERE instance_id = %s
                   AND state IN ('pending', 'retry', 'processing')
            """,
            (instance.id,),
        )
        oldest = cr.fetchone()[0]
        age_minutes = 0
        if oldest:
            age_minutes = max(0, int((fields.Datetime.now() - oldest).total_seconds() // 60))

        active = counts["pending"] + counts["processing"] + counts["retry"]
        return {
            **counts,
            "active": active,
            "total": sum(counts.values()),
            "oldest_active_age_minutes": age_minutes,
        }

    def _dashboard_binding_snapshot(self, instance):
        cr = self.env.cr
        cr.execute(
            """
                SELECT model_name, sync_state, COUNT(*)::int
                  FROM ecommerce_integration_binding
                 WHERE instance_id = %s
                 GROUP BY model_name, sync_state
                 ORDER BY model_name, sync_state
            """,
            (instance.id,),
        )
        models = defaultdict(lambda: {"new": 0, "synced": 0, "error": 0})
        for model_name, sync_state, count in cr.fetchall():
            models[model_name][sync_state] = count

        labels = dict(self.env["ecommerce.integration.binding"]._fields["model_name"].selection)
        rows = []
        totals = {"new": 0, "synced": 0, "error": 0}
        for model_name, states in models.items():
            total = sum(states.values())
            for key in totals:
                totals[key] += states[key]
            rows.append(
                {
                    "key": model_name,
                    "label": labels.get(model_name, model_name),
                    **states,
                    "total": total,
                }
            )

        return {**totals, "total": sum(totals.values()), "by_model": rows}

    def _dashboard_publication_snapshot(self, instance):
        scope = [
            ("ecommerce_integration_publish", "=", True),
            "|",
            ("ecommerce_integration_instance_ids", "=", False),
            ("ecommerce_integration_instance_ids", "in", [instance.id]),
        ]
        product_domain = scope + [
            "|",
            ("company_id", "=", False),
            ("company_id", "=", instance.company_id.id),
        ]

        templates = self.env["product.template"].sudo().search(product_domain)
        categories = self.env["product.category"].sudo().search_count(scope)
        attributes = self.env["product.attribute"].sudo().search_count(scope)
        variants = self.env["product.product"].sudo().search_count(
            [("product_tmpl_id", "in", templates.ids), ("active", "=", True)]
        ) if templates else 0

        return {
            "products": len(templates),
            "variants": variants,
            "categories": categories,
            "attributes": attributes,
        }

    def _dashboard_recent_logs(self, instance, utc_from, utc_to):
        logs = self.env["ecommerce.integration.log"].search(
            [
                ("instance_id", "=", instance.id),
                ("create_date", ">=", utc_from),
                ("create_date", "<", utc_to),
            ],
            order="create_date desc, id desc",
            limit=15,
        )
        type_labels = dict(self.env["ecommerce.integration.log"]._fields["sync_type"].selection)
        return [
            {
                "id": log.id,
                "create_date": fields.Datetime.to_string(log.create_date),
                "sync_type": log.sync_type,
                "sync_type_label": type_labels.get(log.sync_type, log.sync_type),
                "status": log.status,
                "summary": log.summary,
                "http_status": log.http_status or False,
                "duration_ms": log.duration_ms or 0,
                "attempt": log.attempt,
                "error_message": log.error_message or False,
            }
            for log in logs
        ]
