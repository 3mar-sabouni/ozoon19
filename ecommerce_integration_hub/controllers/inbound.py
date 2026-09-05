import json
import time

from odoo import http
from odoo.http import request

from ..utils.signing import verify_signature


class EcommerceInboundController(http.Controller):
    def _json_response(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _load_payload(self):
        raw_body = request.httprequest.get_data(cache=True) or b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return raw_body, None
        return raw_body, payload

    def _authenticate(self, raw_body, payload):
        instance_code = (
            (payload or {}).get("instance_code")
            or request.httprequest.headers.get("X-Ecommerce-Instance")
        )
        if not instance_code:
            return None, "Missing instance_code."
        instance = request.env["ecommerce.integration.instance"].sudo().search(
            [("code", "=", str(instance_code)), ("active", "=", True)], limit=1
        )
        if not instance:
            return None, "Unknown or inactive ecommerce instance."
        timestamp = request.httprequest.headers.get("X-Ecommerce-Timestamp")
        signature = request.httprequest.headers.get("X-Ecommerce-Signature")
        if not instance.shared_secret or not verify_signature(
            instance.shared_secret, timestamp, raw_body, signature
        ):
            return None, "Invalid or expired signature."
        return instance, None

    def _log_inbound(self, instance, sync_type, status, summary, payload, response, started, order=None, error=None, http_status=200):
        duration_ms = int((time.perf_counter() - started) * 1000)
        request.env["ecommerce.integration.log"].sudo().create(
            {
                "instance_id": instance.id,
                "sync_type": sync_type,
                "direction": "in",
                "status": status,
                "model_name": order._name if order else False,
                "res_id": order.id if order else False,
                "summary": summary,
                "http_status": http_status,
                "duration_ms": duration_ms,
                "request_json": json.dumps(payload or {}, ensure_ascii=False, default=str),
                "response_json": json.dumps(response or {}, ensure_ascii=False, default=str),
                "error_message": error or False,
            }
        )
        if status == "failure":
            instance._touch_failure(error or summary)
        else:
            instance._touch_success()

    def _handle(self, status_only=False):
        started = time.perf_counter()
        raw_body, payload = self._load_payload()
        if payload is None or not isinstance(payload, dict):
            return self._json_response({"status": "error", "message": "Invalid JSON object."}, status=400)

        instance, auth_error = self._authenticate(raw_body, payload)
        if auth_error:
            return self._json_response({"status": "error", "message": auth_error}, status=401)

        sync_type = "order_status" if status_only else "order"
        order_payload = payload.get("order") if isinstance(payload.get("order"), dict) else payload
        if payload.get("event_id") and not order_payload.get("event_id"):
            order_payload = dict(order_payload, event_id=payload.get("event_id"))

        try:
            # Keep inbound processing atomic. If product/line creation fails, rollback
            # the partial order before writing the failure log. This prevents empty
            # ecommerce quotations from being committed after a failed webhook.
            with request.env.cr.savepoint():
                order, created, cancel_result, fulfillment_result, accounting_result = instance._upsert_inbound_order(
                    order_payload, status_only=status_only
                )
            response = {
                "status": "ok",
                "odoo_order_id": order.id,
                "odoo_order_name": order.name,
                "created": created,
                "odoo_state": order.state,
                "store_status": order.ecommerce_store_status,
                "payment_status": order.ecommerce_payment_status,
                "fulfillment_status": order.ecommerce_fulfillment_status,
                "cancellation_action": cancel_result or False,
                "fulfillment_action": fulfillment_result or False,
                "accounting": accounting_result or False,
                "delivery_states": [
                    {"name": picking.name, "state": picking.state}
                    for picking in order.picking_ids.filtered(
                        lambda p: p.picking_type_id.code == "outgoing" and not p.return_id
                    )
                ],
            }
            self._log_inbound(
                instance,
                sync_type,
                "success",
                "Store order created" if created else "Store order updated",
                payload,
                response,
                started,
                order=order,
            )
            return self._json_response(response, status=200)
        except Exception as exc:
            response = {"status": "error", "message": str(exc)}
            self._log_inbound(
                instance,
                sync_type,
                "failure",
                "Inbound store order failed",
                payload,
                response,
                started,
                error=str(exc),
                http_status=400,
            )
            return self._json_response(response, status=400)

    @http.route(
        "/ecommerce/inbound/order",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def inbound_order(self, **kwargs):
        return self._handle(status_only=False)

    @http.route(
        "/ecommerce/inbound/order/status",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def inbound_order_status(self, **kwargs):
        return self._handle(status_only=True)
