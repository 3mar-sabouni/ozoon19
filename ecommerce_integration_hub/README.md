# Ecommerce Integration Hub — Odoo 19

Technical addon name: `ecommerce_integration_hub`.

A neutral, reusable Odoo 19 connector for multi-company / multi-store ecommerce integrations. It keeps Odoo as the source of catalog, pricing and inventory data while allowing the external store to create orders and push subsequent order-status changes back into Odoo.

## Direction of synchronization

| Data | Direction | Behavior |
|---|---|---|
| Product categories | Odoo → Store | Queued REST sync |
| Product templates + variants | Odoo → Store | Queued REST sync |
| Attributes + values | Odoo → Store | Attribute changes re-queue affected product/variant payloads |
| Inventory by variant | Odoo → Store | Warehouse-specific quantity sync |
| Price | Odoo → Store | Optional instance pricelist; otherwise standard Odoo Sales Price, converted to target currency |
| Store order creation | Store → Odoo | Authenticated inbound webhook creates/updates `sale.order` |
| Store order/payment/fulfillment status | Store → Odoo | Records remote state; full fulfillment/shipment validates the related Odoo outgoing delivery |
| Odoo sale-order status | **Not sent to Store** | Deliberately disabled |

## Kept from the previous solution

- Same full-screen dashboard and date/instance filtering.
- Multi-instance and multi-company separation.
- Instance configuration for company, warehouse, optional pricelist and target currency.
- Publish to Ecommerce boolean on product template, product category and product attribute.
- Optional instance restriction; an empty instance selection means all applicable active instances.
- Publication at attribute level only; attribute values inherit the attribute publication scope.
- Variant-level SKU/barcode, pricing and inventory.
- Worker-safe PostgreSQL queue with retry/backoff and detailed logs.
- Bindings between Odoo records and external records.
- Bulk Sync and manager-only transaction cleanup.
- No dependency on Odoo Website / `website_sale`.

## Odoo 19 order workflow

Incoming orders are matched by `external_order_id` and store lines are matched to Odoo `product.product` records by the configured SKU source. New online-paid and COD orders can be automatically confirmed in Odoo so the configured warehouse reserves stock.

The module records these remote fields on the sales order:

- Store Order Status
- Store Payment Status
- Store Fulfillment Status
- Store Payment Method / COD flag
- Last external event ID and timestamp
- Return status, reason and sellable flag
- Raw latest store payload for audit/troubleshooting

When the store reports a full fulfillment/shipment/delivery, the module validates the related open outgoing Odoo delivery through standard Odoo stock logic, so the transfer becomes Done and delivered quantity/stock are updated. Partial fulfillment is recorded but does not force the whole delivery to Done. If the store reports a cancellation before an outgoing delivery is completed, the module can cancel the Odoo sales order, which releases reservation through standard Odoo stock logic. If an outgoing delivery is already done, the connector only records the cancellation/refusal status; it does **not** reverse stock automatically. Returns must be received and validated through the normal Odoo return process before stock is available again. This prevents a refused, damaged or not-yet-received item from being incorrectly added to sellable stock.

## Instance configuration

Each instance contains:

- Company
- Warehouse
- Pricelist
- Source currency (from pricelist when selected, otherwise company currency)
- Target/store currency
- SKU source: reference, barcode, or fallback order
- Multi-attribute behavior: native Color/Size-style option groups by default, optional flattened fallback
- External API base URL
- Category / product / stock endpoint paths
- Shared HMAC secret
- Public Odoo image URL
- Queue limits and timeout/retry settings
- Automatic category/product/stock sync switches
- Inbound order enable/disable
- Automatic confirmation for new inbound orders
- Apply incoming cancellations switch

## Outbound security

Outbound requests are signed using:

`HMAC-SHA256(secret, timestamp + "." + raw_json_body)`

Headers:

- `X-Ecommerce-Instance`
- `X-Ecommerce-Timestamp`
- `X-Ecommerce-Signature`
- `Content-Type: application/json`

HTTP 200, 201 and 202 are accepted as successful transport responses. HTTP 429 and 5xx are retried; authentication and malformed contract responses fail permanently.

## Inbound endpoints

- `POST /ecommerce/inbound/order`
- `POST /ecommerce/inbound/order/status`

Both use the same HMAC algorithm and require `instance_code` in the JSON body or `X-Ecommerce-Instance` header. The timestamp must be within five minutes.

See `API_CONTRACT.md` for payload examples.

## Product / variant behavior

The remote product payload contains the Odoo template and every active actual variant. Each variant includes:

- Odoo variant ID
- SKU
- Exact option mapping, for example `{"Color": "Black", "Size": "M"}`
- Price from the optional instance pricelist; if empty, standard Odoo Sales Price is used
- Target currency on the product payload
- Quantity from the instance warehouse

By default the product payload sends native multiple option groups, for example separate `Color` and `Size` options. A flattened single-option fallback remains configurable for gateways that need it.

Inventory synchronization is always variant-specific. A zero-stock size/color combination therefore remains unavailable without making the other variants unavailable.

## Attribute behavior

Publication is configured only on `product.attribute`. Values inherit that scope. When an attribute or value changes, the connector re-queues affected products so the external store receives the updated option structure in the product/variant payload.

## Installation

1. Put `ecommerce_integration_hub` in the Odoo 19 custom addons path.
2. Restart Odoo and update the Apps list.
3. Install **Ecommerce Integration Hub**.
4. Create an instance under **Ecommerce Integration → Instances**.
5. Configure company, warehouse, target currency, external API URL/endpoints and shared secret. Pricelist is optional.
6. Mark categories, attributes and products as **Publish to Ecommerce**.
7. Run **Bulk Sync**.
8. Configure the external ecommerce gateway/webhook sender to call the inbound order endpoints.

## Important implementation boundary

The Odoo addon is intentionally platform-neutral. A store-specific adapter or gateway translates the ecommerce platform's native API/webhook payloads into the generic contract documented in `API_CONTRACT.md`, and translates the generic Odoo catalog/stock payloads into that platform's API calls. This keeps the Odoo module reusable for future customers without vendor or agency naming in the codebase.

### Order-independent category hierarchy

Categories no longer wait for their parent in the Odoo queue. Every category is sent immediately with `parent_odoo_category_id`. If the parent has already been synchronized, `parent_external_id` is included as well. After a parent synchronizes successfully, its published direct children are queued again so the store can reconcile/reorder the hierarchy. This prevents large category trees from failing only because queue order was different.


## Instance Accounting Automation (19.0.1.0.9)

Accounting automation is optional per ecommerce instance. When disabled, the connector only creates/updates the Sale Order and stock delivery. When enabled, the instance can define an invoice trigger (paid, fulfilled, or completed), an optional Sales Journal, optional Payment Terms, automatic invoice posting, and optional automatic customer payment registration using a configured Bank/Cash/Credit journal and inbound payment method.

The connector intentionally does not duplicate Odoo product income accounts, customer receivable accounts, taxes, or fiscal positions. Standard Odoo accounting configuration remains authoritative. COD orders are only registered as paid after the store reports a paid/collected payment status.

## Accounting configuration (Odoo 19)

Each ecommerce instance has an **Accounting** tab. Accounting automation is disabled by default.
When enabled, the administrator can configure:

- Invoice trigger: store Paid, Fulfilled/Delivered, Completed, or Manual.
- Optional Sales Journal and Payment Terms.
- Auto Post Invoice.
- Auto Register Store Payment.
- Online / Default Payment Journal and inbound Payment Method.
- Optional separate COD Payment Journal and inbound Payment Method. If the COD journal is empty, the default payment configuration is used.

The connector never replaces normal Odoo product income accounts, receivable accounts, taxes, fiscal positions, or invoice policy. If a product is invoiced on delivered quantities and is not invoiceable yet, the webhook remains successful and accounting waits for a later status update.

Payment registration is idempotent: repeated store webhooks do not create a second payment once the invoice is paid/in payment.
