import json
import time
from urllib.parse import urljoin

import requests

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..utils.signing import build_signature, serialize_payload
from .common import PermanentConnectorError, RetryableConnectorError


class EcommerceIntegrationInstance(models.Model):
    _name = "ecommerce.integration.instance"
    _description = "Ecommerce Integration Instance"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name, id"

    def _default_public_url(self):
        return self.env["ir.config_parameter"].sudo().get_param("web.base.url")

    def _default_target_currency(self):
        return self.env["res.currency"].search([("name", "=", "IQD")], limit=1) or self.env.company.currency_id

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(
        required=True,
        copy=False,
        default=lambda self: self.env["ir.sequence"].next_by_code("ecommerce.integration.instance") or _("New"),
        index=True,
        tracking=True,
    )
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        required=True,
        check_company=True,
        tracking=True,
    )
    pricelist_id = fields.Many2one(
        "product.pricelist",
        check_company=True,
        tracking=True,
        help=(
            "Optional. When set, this pricelist is used for outgoing product prices. "
            "When empty, the connector uses the product's normal Odoo Sales Price in the company currency."
        ),
    )
    source_currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_source_currency_id",
        store=True,
        readonly=True,
        help="Pricelist currency when a pricelist is selected; otherwise the company currency.",
    )
    target_currency_id = fields.Many2one(
        "res.currency",
        required=True,
        default=_default_target_currency,
        tracking=True,
        help="Currency used in outgoing store price payloads.",
    )

    @api.depends("pricelist_id.currency_id", "company_id.currency_id")
    def _compute_source_currency_id(self):
        for instance in self:
            instance.source_currency_id = (
                instance.pricelist_id.currency_id or instance.company_id.currency_id
            )

    base_url = fields.Char(
        required=True,
        tracking=True,
        help="Base URL of the external ecommerce gateway/API.",
    )
    category_endpoint = fields.Char(default="/hooks/odoo/category", required=True)
    product_endpoint = fields.Char(default="/hooks/odoo/product", required=True)
    stock_endpoint = fields.Char(default="/hooks/odoo/stock", required=True)
    shared_secret = fields.Char(
        groups="ecommerce_integration_hub.group_ecommerce_connector_manager",
        copy=False,
        help="HMAC shared secret. It is masked in the UI and is never written to sync logs.",
    )
    odoo_public_url = fields.Char(
        required=True,
        default=_default_public_url,
        help="Public Odoo base URL used to build product image URLs.",
    )

    locale_ids = fields.One2many(
        "ecommerce.integration.locale",
        "instance_id",
        string="Translations",
    )

    auto_sync_category = fields.Boolean(default=True)
    auto_sync_product = fields.Boolean(default=True)
    auto_sync_stock = fields.Boolean(default=True)
    inbound_orders_enabled = fields.Boolean(
        default=True,
        help="Allow authenticated store order and order-status webhooks to update Odoo.",
    )
    auto_confirm_inbound_orders = fields.Boolean(
        default=True,
        help="Confirm newly received store orders so Odoo can reserve stock using the configured warehouse.",
    )
    apply_store_cancellations = fields.Boolean(
        default=True,
        help="Cancel the Odoo sale order when the store reports a cancellation before completion.",
    )

    # Accounting automation is deliberately optional. When disabled, incoming
    # ecommerce orders keep using normal Odoo sale/stock behavior only.
    accounting_enabled = fields.Boolean(
        string="Accounting Automation",
        default=False,
        tracking=True,
        help="Enable optional invoice and payment automation for orders received by this instance.",
    )
    invoice_trigger = fields.Selection(
        [
            ("manual", "Manual / No Automatic Invoice"),
            ("paid", "When Store Reports Paid"),
            ("fulfilled", "When Store Reports Fulfilled"),
            ("completed", "When Store Reports Completed"),
        ],
        string="Invoice Trigger",
        default="fulfilled",
        required=True,
        tracking=True,
        help=(
            "Controls when the connector attempts to create the customer invoice. "
            "Odoo invoicing policy is still respected; invoice-on-delivery products "
            "wait until the delivered quantity becomes invoiceable."
        ),
    )
    invoice_journal_id = fields.Many2one(
        "account.journal",
        string="Sales Journal",
        check_company=True,
        tracking=True,
        help="Optional sales journal for ecommerce invoices. Leave empty to use Odoo's normal sales journal.",
    )
    invoice_payment_term_id = fields.Many2one(
        "account.payment.term",
        string="Payment Terms",
        tracking=True,
        help="Optional payment terms assigned to incoming ecommerce sale orders and their invoices.",
    )
    auto_post_invoice = fields.Boolean(
        string="Auto Post Invoice",
        default=True,
        tracking=True,
        help="Post automatically created invoices. Disable to leave them in Draft for accounting review.",
    )
    auto_register_payment = fields.Boolean(
        string="Auto Register Store Payment",
        default=False,
        tracking=True,
        help=(
            "When the store reports the order as paid/collected, automatically register payment "
            "against a posted ecommerce invoice."
        ),
    )
    payment_journal_id = fields.Many2one(
        "account.journal",
        string="Online / Default Payment Journal",
        check_company=True,
        tracking=True,
        help="Bank, Cash, or Credit journal used for non-COD store payments and as the fallback for COD.",
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Online / Default Payment Method",
        check_company=True,
        tracking=True,
        help="Inbound payment method for the default payment journal. Empty uses its first available inbound method.",
    )
    cod_payment_journal_id = fields.Many2one(
        "account.journal",
        string="COD Payment Journal",
        check_company=True,
        tracking=True,
        help="Optional Cash on Delivery payment journal. Empty falls back to the Online / Default Payment Journal.",
    )
    cod_payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="COD Payment Method",
        check_company=True,
        tracking=True,
        help="Inbound method for the COD journal. Empty uses the journal's first available inbound method.",
    )
    multi_attribute_mode = fields.Selection(
        [
            ("native", "Native Multiple Options"),
            ("flatten", "Flatten Combination into One Option"),
        ],
        default="native",
        required=True,
        help=(
            "Native sends each variant-generating attribute as its own option group (for example Color and Size). "
            "Flatten combines the full variant combination into one generic option when a remote adapter requires it."
        ),
    )
    sku_source = fields.Selection(
        [
            ("reference", "Internal Reference"),
            ("barcode", "Barcode"),
            ("barcode_reference", "Barcode, then Internal Reference"),
            ("reference_barcode", "Internal Reference, then Barcode"),
        ],
        default="barcode_reference",
        required=True,
        help="Choose which Odoo variant identifier is exposed as the store SKU.",
    )
    timeout_seconds = fields.Integer(default=20, required=True)
    max_attempts = fields.Integer(default=5, required=True)
    stock_batch_size = fields.Integer(
        default=500,
        required=True,
        help="Maximum stock updates sent in one remote request.",
    )
    queue_batch_size = fields.Integer(default=100, required=True)

    last_success_at = fields.Datetime(readonly=True, copy=False)
    last_failure_at = fields.Datetime(readonly=True, copy=False)
    last_failure_message = fields.Text(readonly=True, copy=False)
    health = fields.Selection(
        [("ok", "Healthy"), ("warning", "Attention"), ("disabled", "Disabled")],
        compute="_compute_health",
    )

    pending_count = fields.Integer(compute="_compute_dashboard_counts")
    success_count = fields.Integer(compute="_compute_dashboard_counts")
    failure_count = fields.Integer(compute="_compute_dashboard_counts")
    log_count = fields.Integer(compute="_compute_dashboard_counts")
    binding_count = fields.Integer(compute="_compute_dashboard_counts")

    _sql_constraints = [
        ("instance_code_unique", "unique(code)", "The ecommerce instance code must be unique."),
    ]

    @api.depends("active", "last_success_at", "last_failure_at")
    def _compute_health(self):
        for instance in self:
            if not instance.active:
                instance.health = "disabled"
            elif instance.last_failure_at and (
                not instance.last_success_at or instance.last_failure_at > instance.last_success_at
            ):
                instance.health = "warning"
            else:
                instance.health = "ok"

    def _compute_dashboard_counts(self):
        counts = {
            instance.id: {"pending": 0, "success": 0, "failure": 0, "logs": 0, "bindings": 0}
            for instance in self
        }
        if self.ids:
            Queue = self.env["ecommerce.integration.queue"]
            Log = self.env["ecommerce.integration.log"]
            Binding = self.env["ecommerce.integration.binding"]

            for instance, count in Queue._read_group(
                [
                    ("instance_id", "in", self.ids),
                    ("state", "in", ["pending", "retry", "processing"]),
                ],
                ["instance_id"],
                ["__count"],
            ):
                counts[instance.id]["pending"] = count

            for instance, status, count in Log._read_group(
                [("instance_id", "in", self.ids)],
                ["instance_id", "status"],
                ["__count"],
            ):
                counts[instance.id]["logs"] += count
                if status == "success":
                    counts[instance.id]["success"] += count
                elif status == "failure":
                    counts[instance.id]["failure"] += count

            for instance, count in Binding._read_group(
                [("instance_id", "in", self.ids)],
                ["instance_id"],
                ["__count"],
            ):
                counts[instance.id]["bindings"] = count

        for instance in self:
            data = counts[instance.id]
            instance.pending_count = data["pending"]
            instance.success_count = data["success"]
            instance.failure_count = data["failure"]
            instance.log_count = data["logs"]
            instance.binding_count = data["bindings"]

    @api.constrains("stock_batch_size")
    def _check_stock_batch_size(self):
        for instance in self:
            if instance.stock_batch_size < 1 or instance.stock_batch_size > 500:
                raise ValidationError(_("Stock batch size must be between 1 and 500."))

    @api.constrains("timeout_seconds", "max_attempts", "queue_batch_size")
    def _check_positive_limits(self):
        for instance in self:
            if instance.timeout_seconds < 1 or instance.max_attempts < 1 or instance.queue_batch_size < 1:
                raise ValidationError(_("Timeout, max attempts, and queue batch size must be positive."))

    @api.onchange("payment_journal_id")
    def _onchange_payment_journal_id(self):
        for instance in self:
            if (
                instance.payment_method_line_id
                and instance.payment_method_line_id.journal_id != instance.payment_journal_id
            ):
                instance.payment_method_line_id = False

    @api.onchange("cod_payment_journal_id")
    def _onchange_cod_payment_journal_id(self):
        for instance in self:
            if (
                instance.cod_payment_method_line_id
                and instance.cod_payment_method_line_id.journal_id != instance.cod_payment_journal_id
            ):
                instance.cod_payment_method_line_id = False

    @api.constrains(
        "company_id",
        "warehouse_id",
        "pricelist_id",
        "invoice_journal_id",
        "payment_journal_id",
        "payment_method_line_id",
        "cod_payment_journal_id",
        "cod_payment_method_line_id",
    )
    def _check_company_configuration(self):
        for instance in self:
            for record, label in [
                (instance.warehouse_id, _("Warehouse")),
                (instance.pricelist_id, _("Pricelist")),
                (instance.invoice_journal_id, _("Sales Journal")),
                (instance.payment_journal_id, _("Online / Default Payment Journal")),
                (instance.cod_payment_journal_id, _("COD Payment Journal")),
            ]:
                if record and record.company_id and record.company_id != instance.company_id:
                    raise ValidationError(
                        _(
                            "%(label)s must belong to company %(company)s.",
                            label=label,
                            company=instance.company_id.display_name,
                        )
                    )

            if instance.invoice_journal_id and instance.invoice_journal_id.type != "sale":
                raise ValidationError(_("The ecommerce Sales Journal must be a Sales journal."))

            for journal, label in [
                (instance.payment_journal_id, _("Online / Default Payment Journal")),
                (instance.cod_payment_journal_id, _("COD Payment Journal")),
            ]:
                if journal and journal.type not in ("bank", "cash", "credit"):
                    raise ValidationError(
                        _("%(label)s must be Bank, Cash, or Credit.", label=label)
                    )

            for method_line, journal, label in [
                (instance.payment_method_line_id, instance.payment_journal_id, _("Online / Default Payment Method")),
                (instance.cod_payment_method_line_id, instance.cod_payment_journal_id, _("COD Payment Method")),
            ]:
                if not method_line:
                    continue
                if method_line.payment_type != "inbound":
                    raise ValidationError(_("%(label)s must be an inbound payment method.", label=label))
                if not journal or method_line.journal_id != journal:
                    raise ValidationError(
                        _("%(label)s must belong to its configured payment journal.", label=label)
                    )

    def _ensure_ready(self):
        self.ensure_one()
        if not self.active:
            raise PermanentConnectorError(_("The ecommerce instance is disabled."))
        if not self.shared_secret:
            raise PermanentConnectorError(_("The shared secret is not configured for instance %s.") % self.display_name)

    def _request_json(self, path, payload):
        """Sign the exact outgoing bytes and POST without ever logging the secret/signature."""
        self.ensure_one()
        self._ensure_ready()

        raw_body = serialize_payload(payload)
        timestamp = str(int(time.time()))
        signature = build_signature(self.shared_secret, timestamp, raw_body)
        headers = {
            "Content-Type": "application/json",
            "x-ecommerce-instance": self.code,
            "x-ecommerce-timestamp": timestamp,
            "x-ecommerce-signature": signature,
        }
        url = urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))
        started = time.perf_counter()
        try:
            response = requests.post(
                url,
                data=raw_body,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise RetryableConnectorError(_("Network error: %s") % exc) from exc

        duration_ms = int((time.perf_counter() - started) * 1000)
        response_text = response.text or ""

        if response.status_code == 401:
            raise PermanentConnectorError(
                _("Authentication failed (HTTP 401). Check the shared secret and server time/NTP."),
                status_code=response.status_code,
                response_text=response_text,
            )
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableConnectorError(
                _("Remote server error HTTP %s.") % response.status_code,
                status_code=response.status_code,
                response_text=response_text,
            )
        if response.status_code not in {200, 201, 202}:
            raise PermanentConnectorError(
                _("Unexpected HTTP status %s.") % response.status_code,
                status_code=response.status_code,
                response_text=response_text,
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise PermanentConnectorError(
                _("The remote server returned invalid JSON."),
                status_code=response.status_code,
                response_text=response_text,
            ) from exc
        return body, response.status_code, duration_ms

    def _translations(self, record, field_name, external_key):
        self.ensure_one()
        result = {}
        for locale in self.locale_ids.filtered(lambda item: item.odoo_lang_id.active):
            value = record.with_context(lang=locale.odoo_lang_id.code)[field_name]
            if value:
                result[locale.external_locale] = {external_key: value}
        return result

    def _variant_identifier(self, variant):
        self.ensure_one()
        if self.sku_source == "reference":
            return variant.default_code or ""
        if self.sku_source == "barcode":
            return variant.barcode or ""
        if self.sku_source == "reference_barcode":
            return variant.default_code or variant.barcode or ""
        return variant.barcode or variant.default_code or ""

    def _variant_price(self, variant):
        self.ensure_one()
        variant = variant.with_company(self.company_id)
        if self.pricelist_id:
            source_currency = self.pricelist_id.currency_id
            price = self.pricelist_id.with_company(self.company_id)._get_product_price(
                variant,
                quantity=1.0,
                currency=source_currency,
            )
        else:
            # Odoo's standard Sales Price; no Pricelists setting is required.
            source_currency = self.company_id.currency_id
            price = variant.lst_price

        if source_currency != self.target_currency_id:
            price = source_currency._convert(
                price,
                self.target_currency_id,
                self.company_id,
                fields.Date.context_today(self),
            )
        rounded = self.target_currency_id.round(price)
        return int(rounded) if float(rounded).is_integer() else rounded

    def _variant_quantities(self, variants):
        self.ensure_one()
        if not variants:
            return {}
        records = (
            variants.with_company(self.company_id)
            .with_context(warehouse=self.warehouse_id.id)
            .read(["qty_available"])
        )
        return {item["id"]: item["qty_available"] for item in records}

    def _image_url(self, template):
        self.ensure_one()
        if not template.image_1920:
            return False
        base = self.odoo_public_url.rstrip("/")
        return f"{base}/web/image/product.template/{template.id}/image_1920"

    def _touch_success(self):
        self.write({"last_success_at": fields.Datetime.now(), "last_failure_message": False})

    def _touch_failure(self, message):
        self.write({"last_failure_at": fields.Datetime.now(), "last_failure_message": message})

    def action_view_logs(self):
        self.ensure_one()
        action = self.env.ref("ecommerce_integration_hub.action_ecommerce_integration_log").read()[0]
        action["domain"] = [("instance_id", "=", self.id)]
        action["context"] = {"default_instance_id": self.id}
        return action

    def action_view_queue(self):
        self.ensure_one()
        action = self.env.ref("ecommerce_integration_hub.action_ecommerce_integration_queue").read()[0]
        action["domain"] = [("instance_id", "=", self.id)]
        action["context"] = {"default_instance_id": self.id}
        return action

    def action_view_bindings(self):
        self.ensure_one()
        action = self.env.ref("ecommerce_integration_hub.action_ecommerce_integration_binding").read()[0]
        action["domain"] = [("instance_id", "=", self.id)]
        action["context"] = {"default_instance_id": self.id}
        return action

    def action_bulk_sync(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Bulk Sync"),
            "res_model": "ecommerce.integration.bulk.sync.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_instance_id": self.id},
        }

    def action_clear_transactions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Clear Sync Transactions"),
            "res_model": "ecommerce.integration.clear.logs.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_instance_id": self.id},
        }

    @api.model
    def json_text(self, value):
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)


class EcommerceIntegrationLocale(models.Model):
    _name = "ecommerce.integration.locale"
    _description = "Ecommerce Locale Mapping"
    _order = "external_locale, id"

    instance_id = fields.Many2one(
        "ecommerce.integration.instance",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="instance_id.company_id", store=True, index=True)
    odoo_lang_id = fields.Many2one(
        "res.lang",
        required=True,
        domain=[("active", "=", True)],
    )
    external_locale = fields.Selection(
        [
            ("ar-IQ", "Arabic (Iraq) — ar-IQ"),
            ("ckb-IQ", "Sorani Kurdish (Iraq) — ckb-IQ"),
            ("tr-TR", "Turkish (Türkiye) — tr-TR"),
        ],
        required=True,
    )

    _sql_constraints = [
        (
            "instance_external_locale_unique",
            "unique(instance_id, external_locale)",
            "Each external locale can only be configured once per instance.",
        ),
    ]
