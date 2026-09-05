import json

from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError


class EcommerceIntegrationInstanceOrderSync(models.Model):
    _inherit = "ecommerce.integration.instance"

    def _find_variant_by_store_sku(self, sku):
        self.ensure_one()
        sku = (sku or "").strip()
        if not sku:
            raise ValidationError(_("Every incoming order line must contain a SKU."))

        Product = self.env["product.product"].sudo().with_company(self.company_id)
        company_domain = ["|", ("company_id", "=", False), ("company_id", "=", self.company_id.id)]
        if self.sku_source == "reference":
            domains = [[("default_code", "=", sku)]]
        elif self.sku_source == "barcode":
            domains = [[("barcode", "=", sku)]]
        elif self.sku_source == "reference_barcode":
            domains = [[("default_code", "=", sku)], [("barcode", "=", sku)]]
        else:
            domains = [[("barcode", "=", sku)], [("default_code", "=", sku)]]

        for identifier_domain in domains:
            products = Product.search(company_domain + identifier_domain, limit=2)
            if len(products) > 1:
                raise ValidationError(_("SKU '%s' matches more than one Odoo variant.") % sku)
            if products:
                return products
        raise ValidationError(_("SKU '%s' does not match any Odoo product variant.") % sku)

    def _find_or_create_store_partner(self, customer, shipping):
        self.ensure_one()
        customer = customer or {}
        shipping = shipping or {}
        email = (customer.get("email") or shipping.get("email") or "").strip()
        phone = (customer.get("phone") or shipping.get("phone") or "").strip()
        name = (
            customer.get("name")
            or shipping.get("name")
            or email
            or phone
            or _("Ecommerce Customer")
        )
        Partner = self.env["res.partner"].sudo().with_company(self.company_id)
        partner = self.env["res.partner"]
        if email:
            partner = Partner.search([("email", "=ilike", email)], limit=1)
        if not partner and phone:
            partner = Partner.search([("phone", "=", phone)], limit=1)
        if not partner:
            country = self.env["res.country"]
            country_code = (shipping.get("country_code") or customer.get("country_code") or "").upper()
            if country_code:
                country = self.env["res.country"].sudo().search([("code", "=", country_code)], limit=1)
            vals = {
                "name": name,
                "email": email or False,
                "phone": phone or False,
                "street": shipping.get("address1") or shipping.get("street") or False,
                "street2": shipping.get("address2") or shipping.get("street2") or False,
                "city": shipping.get("city") or False,
                "zip": shipping.get("zip") or shipping.get("postal_code") or False,
                "country_id": country.id or False,
                "company_type": "person",
            }
            partner = Partner.create(vals)
        return partner

    def _incoming_price_to_currency(self, amount, target_currency, incoming_currency_code=None):
        self.ensure_one()
        amount = float(amount or 0.0)
        incoming_currency = self.target_currency_id
        if incoming_currency_code:
            incoming_currency = self.env["res.currency"].sudo().search(
                [("name", "=", str(incoming_currency_code).upper())], limit=1
            ) or incoming_currency
        target_currency = target_currency or self.company_id.currency_id
        if incoming_currency == target_currency:
            return amount
        return incoming_currency._convert(
            amount,
            target_currency,
            self.company_id,
            fields.Date.context_today(self),
        )

    def _store_status_values(self, payload):
        status = payload.get("status") or payload.get("order_status") or ""
        payment_status = payload.get("payment_status") or payload.get("financial_status") or ""
        fulfillment_status = payload.get("fulfillment_status") or ""
        payment_method = payload.get("payment_method") or payload.get("gateway") or ""
        payment_method_lower = str(payment_method).lower().replace("_", " ")
        is_cod = "cash on delivery" in payment_method_lower or payment_method_lower.strip() == "cod"
        return {
            "ecommerce_store_status": status or False,
            "ecommerce_payment_status": payment_status or False,
            "ecommerce_fulfillment_status": fulfillment_status or False,
            "ecommerce_payment_method": payment_method or False,
            "ecommerce_is_cod": is_cod,
            "ecommerce_last_event_id": payload.get("event_id") or False,
            "ecommerce_last_status_at": fields.Datetime.now(),
            "ecommerce_return_status": payload.get("return_status") or False,
            "ecommerce_return_reason": payload.get("return_reason") or False,
            "ecommerce_return_sellable": str(payload.get("return_sellable", "")).lower() in {"1", "true", "yes", "y"},
            "ecommerce_raw_status_json": json.dumps(payload, ensure_ascii=False, default=str),
        }

    def _apply_inbound_cancellation(self, order, payload):
        self.ensure_one()
        if not self.apply_store_cancellations or order.state == "cancel":
            return False
        status = str(payload.get("status") or payload.get("order_status") or "").lower()
        cancelled_flag = str(payload.get("cancelled", "")).lower() in {"1", "true", "yes", "y"}
        cancelled = cancelled_flag or status in {
            "cancelled", "canceled", "refused", "unsuccessful"
        }
        if not cancelled:
            return False
        done_delivery = order.picking_ids.filtered(
            lambda p: p.picking_type_id.code == "outgoing" and p.state == "done"
        )
        if done_delivery:
            # Never reverse completed stock moves from a status flag alone. A real Odoo return
            # must be received and validated before stock becomes sellable again.
            return "recorded_only_after_delivery"
        order.with_context(ecommerce_skip_enqueue=True).action_cancel()
        return "cancelled"

    def _apply_inbound_fulfillment(self, order, payload):
        """Apply a completed store fulfillment to Odoo stock.

        The external ecommerce store is the source of order/fulfillment status.
        When it reports a full shipment/fulfillment, complete the related outgoing
        Odoo delivery using standard stock validation. Partial fulfillment is only
        recorded for now and never forces the whole Odoo delivery to Done.
        """
        self.ensure_one()
        if order.state == "cancel":
            return False

        fulfillment_status = str(payload.get("fulfillment_status") or "").strip().lower()
        order_status = str(payload.get("status") or payload.get("order_status") or "").strip().lower()

        full_fulfillment_statuses = {
            "fulfilled",
            "shipped",
            "delivered",
            "complete",
            "completed",
        }
        # Some generic gateways may put shipped/fulfilled/delivered in the order
        # status while leaving fulfillment_status empty. Do not use "completed"
        # as a fallback by itself because it may mean payment/order completion only.
        should_fulfill = fulfillment_status in full_fulfillment_statuses or (
            not fulfillment_status and order_status in {"fulfilled", "shipped", "delivered"}
        )
        if not should_fulfill:
            return False

        outgoing_pickings = order.picking_ids.filtered(
            lambda p: p.picking_type_id.code == "outgoing" and not p.return_id
        )
        if not outgoing_pickings:
            return "no_outgoing_delivery"

        open_pickings = outgoing_pickings.filtered(lambda p: p.state not in ("done", "cancel"))
        if not open_pickings:
            return "already_fulfilled" if outgoing_pickings.filtered(lambda p: p.state == "done") else "no_open_delivery"

        validated_names = []
        for picking in open_pickings.sorted(lambda p: (p.scheduled_date or fields.Datetime.now(), p.id)):
            if picking.state == "draft":
                picking.action_confirm()

            # Try normal reservation first. If the store says the shipment is
            # fulfilled, Odoo must reflect the physical movement even when its
            # reservation was incomplete. Setting move.quantity to demand uses
            # Odoo 19's standard inverse to create/update move lines.
            if picking.state not in ("assigned", "done", "cancel"):
                picking.action_assign()

            moves = picking.move_ids.filtered(lambda m: m.state not in ("done", "cancel"))
            for move in moves:
                # In Odoo 19 ``quantity`` is the processed/reserved quantity shown
                # on the stock move. A full store fulfillment means the full demand
                # was physically shipped, so make the processed quantity equal to
                # the demand and explicitly mark the move as picked.
                if move.product_uom.compare(move.quantity, move.product_uom_qty) < 0:
                    move.quantity = move.product_uom_qty
                move.picked = True

            # ``button_validate`` is designed for the interactive UI and can be
            # intercepted by optional stock/enterprise modules that return an
            # action or wizard. A webhook has no UI to complete such an action.
            # Reuse Odoo's own validation primitives directly instead: keep the
            # standard sanity checks (lots/serials, quantities, empty transfers),
            # then complete the stock moves without creating a backorder.
            picking._sanity_check()
            picking.with_context(
                cancel_backorder=True,
                skip_backorder=True,
                ecommerce_inbound_fulfillment=True,
            )._action_done()

            # Refresh state after the stock operation because downstream modules
            # may have touched the picking through another environment/cache.
            picking.invalidate_recordset(["state"])
            if picking.state != "done":
                raise ValidationError(
                    _(
                        "Store fulfillment could not complete Odoo delivery %(delivery)s "
                        "(current state: %(state)s).",
                        delivery=picking.display_name,
                        state=picking.state,
                    )
                )
            validated_names.append(picking.name)

        return "validated:%s" % ",".join(validated_names) if validated_names else "already_fulfilled"

    def _normalize_store_status(self, value):
        return str(value or "").strip().lower().replace("-", " ").replace("_", " ")

    def _store_payment_is_paid(self, payload):
        payment_status = self._normalize_store_status(
            payload.get("payment_status") or payload.get("financial_status")
        )
        return payment_status in {
            "paid",
            "captured",
            "settled",
            "collected",
            "payment collected",
            "complete",
            "completed",
            "success",
            "successful",
            "succeeded",
        }

    def _store_is_fulfilled(self, payload):
        fulfillment = self._normalize_store_status(payload.get("fulfillment_status"))
        status = self._normalize_store_status(payload.get("status") or payload.get("order_status"))
        return fulfillment in {
            "fulfilled",
            "shipped",
            "delivered",
            "complete",
            "completed",
        } or (not fulfillment and status in {"fulfilled", "shipped", "delivered"})

    def _accounting_trigger_reached(self, payload):
        self.ensure_one()
        if self.invoice_trigger == "manual":
            return False
        if self.invoice_trigger == "paid":
            return self._store_payment_is_paid(payload)
        if self.invoice_trigger == "fulfilled":
            return self._store_is_fulfilled(payload)
        status = self._normalize_store_status(payload.get("status") or payload.get("order_status"))
        return status in {"complete", "completed", "delivered"}

    def _payment_configuration_for_order(self, order):
        self.ensure_one()
        if order.ecommerce_is_cod and self.cod_payment_journal_id:
            journal = self.cod_payment_journal_id
            method_line = self.cod_payment_method_line_id
            kind = "cod"
        else:
            journal = self.payment_journal_id
            method_line = self.payment_method_line_id
            kind = "cod_fallback" if order.ecommerce_is_cod else "online"

        if not journal:
            return journal, method_line, kind

        available_methods = journal._get_available_payment_method_lines("inbound")
        if method_line and method_line not in available_methods:
            method_line = self.env["account.payment.method.line"]
        if not method_line:
            method_line = available_methods[:1]
        return journal, method_line, kind

    def _apply_inbound_accounting(self, order, payload):
        """Apply optional per-instance accounting using standard Odoo flows.

        The method is idempotent: repeated status webhooks reuse existing invoices
        and only register payment while a posted invoice still has a residual.
        Product accounts, taxes, fiscal positions and invoice policy remain Odoo's
        standard configuration and are never overridden by the connector.
        """
        self.ensure_one()
        result = {
            "enabled": bool(self.accounting_enabled),
            "trigger": self.invoice_trigger,
            "trigger_reached": False,
            "invoice_action": False,
            "invoice_ids": [],
            "invoice_names": [],
            "invoice_states": [],
            "payment_action": False,
            "payment_ids": [],
        }

        if not self.accounting_enabled:
            result["invoice_action"] = "disabled"
            result["payment_action"] = "disabled"
            return result
        if order.state == "cancel":
            result["invoice_action"] = "skipped_cancelled_order"
            result["payment_action"] = "skipped_cancelled_order"
            return result
        if self.invoice_trigger == "manual":
            result["invoice_action"] = "manual"
            result["payment_action"] = "manual"
            return result

        result["trigger_reached"] = self._accounting_trigger_reached(payload)

        if order.state in ("draft", "sent") and result["trigger_reached"]:
            order.action_confirm()

        if self.invoice_payment_term_id and order.payment_term_id != self.invoice_payment_term_id:
            order.payment_term_id = self.invoice_payment_term_id

        invoices = order.invoice_ids.filtered(
            lambda move: move.move_type == "out_invoice" and move.state != "cancel"
        )
        created_invoices = self.env["account.move"]

        # The invoice trigger controls invoice creation/posting, but payment status
        # may arrive in a later webhook without repeating fulfillment/completion.
        # If an invoice already exists, keep processing payment independently.
        if not result["trigger_reached"] and not invoices:
            result["invoice_action"] = "waiting_trigger"
            result["payment_action"] = "waiting_invoice"
            return result

        if not invoices and result["trigger_reached"]:
            order.invalidate_recordset(["invoice_status"])
            if order.invoice_status != "to invoice":
                result["invoice_action"] = "waiting_invoiceable_qty"
                result["payment_action"] = "waiting_invoice"
                return result

            context = {"default_move_type": "out_invoice"}
            if self.invoice_journal_id:
                context["default_journal_id"] = self.invoice_journal_id.id
            try:
                created_invoices = order.with_context(**context)._create_invoices()
            except UserError:
                order.invalidate_recordset(["invoice_status"])
                if order.invoice_status != "to invoice":
                    result["invoice_action"] = "waiting_invoiceable_qty"
                    result["payment_action"] = "waiting_invoice"
                    return result
                raise
            invoices = created_invoices.filtered(lambda move: move.state != "cancel")

        draft_invoices = invoices.filtered(lambda move: move.state == "draft")
        if self.invoice_journal_id and draft_invoices:
            draft_invoices.filtered(
                lambda move: move.journal_id != self.invoice_journal_id
            ).write({"journal_id": self.invoice_journal_id.id})

        if result["trigger_reached"] and self.auto_post_invoice and draft_invoices:
            draft_invoices.action_post()
            result["invoice_action"] = "created_and_posted" if created_invoices else "posted_existing"
        elif created_invoices:
            result["invoice_action"] = "created_draft"
        elif draft_invoices:
            result["invoice_action"] = (
                "existing_draft" if result["trigger_reached"] else "existing_draft_waiting_trigger"
            )
        else:
            result["invoice_action"] = (
                "existing_posted" if result["trigger_reached"] else "existing_posted_before_trigger"
            )

        invoices.invalidate_recordset(["state", "payment_state", "amount_residual"])
        result["invoice_ids"] = invoices.ids
        result["invoice_names"] = invoices.mapped("name")
        result["invoice_states"] = [
            {
                "id": invoice.id,
                "name": invoice.name,
                "state": invoice.state,
                "payment_state": invoice.payment_state,
                "amount_residual": invoice.amount_residual,
            }
            for invoice in invoices
        ]

        if not self.auto_register_payment:
            result["payment_action"] = "disabled"
            return result
        if not self._store_payment_is_paid(payload):
            result["payment_action"] = "waiting_store_payment"
            return result

        payable_invoices = invoices.filtered(
            lambda move: move.state == "posted" and move.amount_residual > 0
        )
        if not payable_invoices:
            if invoices and all(move.payment_state in ("paid", "in_payment") for move in invoices):
                result["payment_action"] = "already_paid"
            elif invoices.filtered(lambda move: move.state != "posted"):
                result["payment_action"] = "waiting_invoice_post"
            else:
                result["payment_action"] = "nothing_to_pay"
            return result

        journal, method_line, payment_kind = self._payment_configuration_for_order(order)
        if not journal:
            result["payment_action"] = f"missing_{payment_kind}_payment_journal"
            return result
        if not method_line:
            result["payment_action"] = f"missing_{payment_kind}_payment_method"
            return result

        wizard = self.env["account.payment.register"].sudo().with_company(self.company_id).with_context(
            active_model="account.move",
            active_ids=payable_invoices.ids,
        ).create(
            {
                "journal_id": journal.id,
                "payment_method_line_id": method_line.id,
                "group_payment": True,
            }
        )
        payments = wizard._create_payments()
        result["payment_action"] = "registered"
        result["payment_ids"] = payments.ids
        return result

    def _create_inbound_order_lines(self, order, lines, incoming_currency):
        """Create store order lines on an Odoo quotation.

        This helper is intentionally idempotent at the order level: callers only
        invoke it for a newly created order or after clearing an incomplete draft
        order left by an older failed webhook implementation.
        """
        self.ensure_one()
        for line in lines:
            product = self._find_variant_by_store_sku(line.get("sku"))
            qty = float(line.get("quantity") or line.get("qty") or 0.0)
            if qty <= 0:
                raise ValidationError(_("Order line SKU '%s' has an invalid quantity.") % line.get("sku"))

            if line.get("unit_price") is None and line.get("price") is None:
                effective_pricelist = self.pricelist_id or order.pricelist_id
                if effective_pricelist:
                    price_unit = effective_pricelist.with_company(self.company_id)._get_product_price(
                        product.with_company(self.company_id),
                        quantity=qty,
                        currency=order.currency_id or effective_pricelist.currency_id,
                    )
                else:
                    price_unit = product.with_company(self.company_id).lst_price
                    if self.company_id.currency_id != order.currency_id:
                        price_unit = self.company_id.currency_id._convert(
                            price_unit,
                            order.currency_id or self.company_id.currency_id,
                            self.company_id,
                            fields.Date.context_today(self),
                        )
            else:
                price_unit = self._incoming_price_to_currency(
                    line.get("unit_price", line.get("price")),
                    order.currency_id or self.company_id.currency_id,
                    incoming_currency,
                )

            self.env["sale.order.line"].sudo().with_company(self.company_id).create(
                {
                    "order_id": order.id,
                    "product_id": product.id,
                    "name": line.get("name") or product.display_name,
                    "product_uom_qty": qty,
                    "product_uom_id": product.uom_id.id,
                    "price_unit": price_unit,
                }
            )

    def _upsert_inbound_order(self, payload, status_only=False):
        self.ensure_one()
        if not self.inbound_orders_enabled:
            raise ValidationError(_("Inbound ecommerce orders are disabled for this instance."))

        external_id = str(payload.get("external_order_id") or payload.get("order_id") or payload.get("id") or "").strip()
        if not external_id:
            raise ValidationError(_("external_order_id is required."))

        SaleOrder = self.env["sale.order"].sudo().with_company(self.company_id)
        order = SaleOrder.search(
            [
                ("ecommerce_integration_instance_id", "=", self.id),
                ("ecommerce_external_order_id", "=", external_id),
            ],
            limit=1,
        )
        created = False

        if not order:
            if status_only:
                raise ValidationError(_("Store order %s does not exist in Odoo yet.") % external_id)
            lines = payload.get("lines") or []
            if not lines:
                raise ValidationError(_("An incoming new order must contain at least one line."))
            partner = self._find_or_create_store_partner(payload.get("customer"), payload.get("shipping_address"))
            order_number = payload.get("order_number") or payload.get("name") or external_id
            order_vals = {
                "partner_id": partner.id,
                "partner_invoice_id": partner.id,
                "partner_shipping_id": partner.id,
                "company_id": self.company_id.id,
                "warehouse_id": self.warehouse_id.id,
                "origin": str(order_number),
                "client_order_ref": str(order_number),
                "ecommerce_integration_instance_id": self.id,
                "ecommerce_external_order_id": external_id,
                "ecommerce_external_order_number": str(order_number),
            }
            # The connector pricelist is optional. When it is not configured,
            # let standard Odoo compute the sale order's normal customer/company pricelist.
            if self.pricelist_id:
                order_vals["pricelist_id"] = self.pricelist_id.id
            if self.accounting_enabled and self.invoice_payment_term_id:
                order_vals["payment_term_id"] = self.invoice_payment_term_id.id
            order = SaleOrder.create(order_vals)
            incoming_currency = payload.get("currency") or self.target_currency_id.name
            self._create_inbound_order_lines(order, lines, incoming_currency)
            created = True
            if self.auto_confirm_inbound_orders:
                order.action_confirm()

        elif not status_only:
            # Repair/retry behavior for an existing draft ecommerce order. Older
            # versions could leave an empty quotation behind if line creation failed
            # after the order itself had already been created. Re-sending the same
            # store order should restore its lines instead of silently returning OK.
            lines = payload.get("lines") or []
            if lines and order.state in ("draft", "sent") and not order.order_line:
                incoming_currency = payload.get("currency") or self.target_currency_id.name
                self._create_inbound_order_lines(order, lines, incoming_currency)
                if self.auto_confirm_inbound_orders:
                    order.action_confirm()

        order.write(self._store_status_values(payload))
        cancel_result = self._apply_inbound_cancellation(order, payload)
        fulfillment_result = False
        accounting_result = False
        if not cancel_result:
            fulfillment_result = self._apply_inbound_fulfillment(order, payload)
            accounting_result = self._apply_inbound_accounting(order, payload)

        binding = self.env["ecommerce.integration.binding"].sudo().get_or_create(self, order)
        binding.write(
            {
                "external_id": external_id,
                "sync_state": "synced",
                "last_sync_at": fields.Datetime.now(),
                "last_error": False,
            }
        )
        return order, created, cancel_result, fulfillment_result, accounting_result
