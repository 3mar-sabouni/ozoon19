# Ecommerce Integration Hub — API Contract

## 1. Authentication

Exact raw request body is signed with:

`hex(HMAC_SHA256(secret, timestamp + "." + raw_body))`

Headers:

```text
X-Ecommerce-Instance: ECOMM-0001
X-Ecommerce-Timestamp: 1788648000
X-Ecommerce-Signature: <hex sha256 hmac>
Content-Type: application/json
```

Inbound verification accepts a maximum timestamp drift of 300 seconds.

---

## 2. Store → Odoo: Create / Upsert Order

`POST /ecommerce/inbound/order`

```json
{
  "instance_code": "ECOMM-0001",
  "event_id": "evt-order-1001-created",
  "order": {
    "external_order_id": "1001",
    "order_number": "#1001",
    "status": "processing",
    "payment_status": "paid",
    "fulfillment_status": "unfulfilled",
    "payment_method": "card",
    "currency": "IQD",
    "customer": {
      "name": "Customer Name",
      "phone": "+9647500000000",
      "email": "customer@example.com"
    },
    "shipping_address": {
      "name": "Customer Name",
      "phone": "+9647500000000",
      "address1": "Street / Area",
      "address2": "",
      "city": "Erbil",
      "country_code": "IQ"
    },
    "lines": [
      {
        "external_line_id": "line-1",
        "sku": "TSHIRT-BLK-M",
        "name": "Basic T-Shirt / Black / M",
        "quantity": 1,
        "unit_price": 25000
      }
    ]
  }
}
```

Required for new orders:

- `external_order_id`
- at least one line
- unique `sku` per Odoo variant
- positive quantity

If `unit_price` is omitted, Odoo uses the configured instance pricelist when present; otherwise it uses the standard Odoo sale-order/customer pricing. If a price is supplied by the store, the incoming store currency is converted to the sale order currency when necessary. The integration instance does not require the Odoo Pricelists feature to be enabled.

---

## 3. Store → Odoo: Update Order Status

`POST /ecommerce/inbound/order/status`

```json
{
  "instance_code": "ECOMM-0001",
  "event_id": "evt-order-1001-fulfilled",
  "order": {
    "external_order_id": "1001",
    "status": "completed",
    "payment_status": "paid",
    "fulfillment_status": "fulfilled",
    "payment_method": "card"
  }
}
```

When `fulfillment_status` is `fulfilled`, `shipped`, `delivered`, `complete`, or `completed`, Odoo validates the related open outgoing delivery and returns the action in `fulfillment_action`. A `partial` status is recorded only and does not validate the whole delivery.

Example successful response:

```json
{
  "status": "ok",
  "odoo_order_name": "S00003",
  "odoo_state": "sale",
  "store_status": "completed",
  "payment_status": "paid",
  "fulfillment_status": "fulfilled",
  "cancellation_action": false,
  "fulfillment_action": "validated:WH/OUT/00001",
  "delivery_states": [
    {"name": "WH/OUT/00001", "state": "done"}
  ]
}
```

COD example:

```json
{
  "instance_code": "ECOMM-0001",
  "event_id": "evt-order-1002-delivered",
  "order": {
    "external_order_id": "1002",
    "status": "completed",
    "payment_status": "paid",
    "fulfillment_status": "delivered",
    "payment_method": "cash_on_delivery"
  }
}
```

Cancellation / refusal before completed Odoo delivery:

```json
{
  "instance_code": "ECOMM-0001",
  "event_id": "evt-order-1003-cancelled",
  "order": {
    "external_order_id": "1003",
    "status": "cancelled",
    "cancelled": true,
    "payment_status": "pending",
    "fulfillment_status": "unfulfilled",
    "payment_method": "cash_on_delivery"
  }
}
```

Return status can be recorded without automatically restocking:

```json
{
  "instance_code": "ECOMM-0001",
  "event_id": "evt-order-1004-return",
  "order": {
    "external_order_id": "1004",
    "status": "returned",
    "return_status": "received",
    "return_reason": "customer_return",
    "return_sellable": false
  }
}
```

A returned product only becomes available again when the corresponding Odoo stock return is physically received and validated.

---

## 4. Odoo → Store: Category

Configured path: instance `category_endpoint`.

Core payload:

```json
{
  "odoo_category_id": 15,
  "name": "T-Shirts",
  "handle": "t-shirts",
  "parent_odoo_category_id": null,
  "translations": {}
}
```

Expected response contains `status` = `created` or `updated`, optionally `external_category_id`.

---

## 5. Odoo → Store: Product + Variants

Configured path: instance `product_endpoint`.

```json
{
  "odoo_template_id": 101,
  "title": "Basic T-Shirt",
  "handle": "basic-t-shirt",
  "odoo_category_ids": [15],
  "currency": "IQD",
  "options": [
    {"name": "Color", "values": ["Black", "White"]},
    {"name": "Size", "values": ["S", "M", "L", "XL"]}
  ],
  "variants": [
    {
      "odoo_variant_id": 501,
      "sku": "TSHIRT-BLK-M",
      "title": "Color: Black / Size: M",
      "options": {"Color": "Black", "Size": "M"},
      "price": 25000,
      "quantity": 5
    }
  ],
  "image_url": "https://odoo.example.com/web/image/product.template/101/image_1920"
}
```

Each variant keeps its own SKU, price, and warehouse quantity. A zero quantity affects only that exact variant.

Expected response:

```json
{
  "status": "updated",
  "external_product_id": "remote-product-101",
  "variants": [
    {
      "odoo_variant_id": 501,
      "status": "updated",
      "external_variant_id": "remote-variant-501"
    }
  ]
}
```

---

## 6. Odoo → Store: Inventory

Configured path: instance `stock_endpoint`.

```json
{
  "updates": [
    {"odoo_variant_id": 501, "quantity": 5},
    {"odoo_variant_id": 502, "quantity": 0}
  ]
}
```

Expected response:

```json
{
  "results": [
    {"odoo_variant_id": 501, "status": "updated"},
    {"odoo_variant_id": 502, "status": "updated"}
  ]
}
```

## Category hierarchy is order-independent

The receiver **must not require the parent category to exist before accepting a child**.
Each category payload contains stable Odoo hierarchy references:

```json
{
  "odoo_category_id": 123,
  "name": "Sports Watch",
  "handle": "sports-watch",
  "parent_odoo_category_id": 45,
  "parent_external_id": "gid://shopify/Collection/123456",
  "parent_handle": "watch"
}
```

`parent_external_id` can be empty when the child arrives first. Create/update the child anyway and retain `parent_odoo_category_id`. When the parent later exists, reconcile the hierarchy. Odoo also re-queues direct children after a successful parent sync, so the receiver gets a second update with the resolved parent binding.

## Accounting result on inbound order/status responses

When instance accounting automation is configured, successful order/status responses also include an `accounting` object. Example:

```json
{
  "accounting": {
    "enabled": true,
    "trigger": "fulfilled",
    "trigger_reached": true,
    "invoice_action": "created_and_posted",
    "invoice_names": ["INV/2026/00001"],
    "payment_action": "registered",
    "payment_ids": [15]
  }
}
```

Possible waiting states such as `waiting_trigger`, `waiting_invoiceable_qty`, `waiting_store_payment`, `waiting_invoice_post`, or `missing_online_payment_journal` are non-duplicating states. A later webhook can continue the same order/invoice safely.
