# 🔗 Webhook Event Engine — Odoo 19

**Replace Zapier for Odoo. Push data from Odoo to any external system in real time.**

```
Odoo Model Event → Event Listener → Webhook Rule Engine → Payload Builder → HTTP Dispatcher → Retry + Logging
```

---

## 🔥 Key Features

### Outgoing Webhooks

- **Event-driven triggers** — On Create, On Update, On Delete, On State Change
- **Domain filters** — Only fire for matching records (e.g., only confirmed orders, high-value deals)
- **Watched fields** — Trigger only when specific fields change
- **State change detection** — Fire when status transitions to a target value

### Payload Builder (3 Modes)

| Mode                | Description                                                                            |
| ------------------- | -------------------------------------------------------------------------------------- |
| **Field Picker**    | Select specific fields, rename JSON keys, include nested relations                     |
| **Jinja2 Template** | Full control with Jinja2 templating — variables: `record`, `event`, `env`, `timestamp` |
| **Full Record**     | Send all readable fields automatically                                                 |

### Security

- **HMAC-SHA256 signing** — `X-Odoo-Signature` header for payload integrity verification
- **Custom headers** — Add Authorization, API keys, or any custom headers
- **Multi-company isolation** — Record rules ensure data separation

### Retry Engine

- **Exponential backoff** — Automatic retries with increasing delays (60s → 120s → 240s…)
- **Dead-letter queue** — Failed deliveries after max retries move to DLQ for manual review
- **Manual retry** — One-click retry from log or DLQ
- **Cron-based processing** — Pending retries processed every 5 minutes

### Incoming Webhooks

- **Custom endpoints** — `/webhook/incoming/<slug>` with unique slugs
- **Authentication** — API key header, Bearer token, or no auth
- **IP restriction** — Whitelist allowed IP addresses
- **Actions** — Create records, run server actions, or execute custom Python code
- **Field mapping** — Map incoming JSON keys to Odoo fields

### Analytics Dashboard (OWL 2)

- Total webhooks sent / success / failed
- Success rate with color-coded indicators
- Average response time
- Daily traffic chart (30-day bar graph)
- Top endpoints table
- Events per model (horizontal bar chart)
- Events by type breakdown
- Dead-letter queue alert

---

## 📂 Module Structure

```
odoo_webhook_engine/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── webhook_event.py        # Event type definitions
│   ├── webhook_rule.py         # Rule configuration (model + event + URL + payload)
│   ├── webhook_payload_field.py # Field picker for payload builder
│   ├── webhook_log.py          # Full request/response logging
│   ├── webhook_retry.py        # Dead-letter queue
│   ├── webhook_incoming.py     # Incoming webhook endpoints
│   └── ir_model_hook.py        # ORM create/write/unlink monkey-patching
├── services/
│   ├── dispatcher.py           # HTTP dispatch + retry logic
│   ├── payload_builder.py      # Payload construction (fields / template / full)
│   └── signature.py            # HMAC-SHA256 signing & verification
├── controllers/
│   ├── incoming_webhook.py     # Incoming webhook HTTP handler
│   └── dashboard.py            # Dashboard data API
├── views/
│   ├── webhook_rule_views.xml
│   ├── webhook_log_views.xml
│   ├── webhook_incoming_views.xml
│   ├── webhook_event_views.xml
│   ├── dashboard_views.xml
│   └── menus.xml
├── data/
│   ├── webhook_event_data.xml   # Default event types
│   └── cron.xml                 # Scheduled jobs
├── security/
│   ├── webhook_security.xml     # Groups + record rules
│   └── ir.model.access.csv
└── static/
    ├── src/
    │   ├── js/dashboard/
    │   │   ├── webhook_dashboard.js
    │   │   └── webhook_dashboard.xml
    │   └── scss/
    │       └── dashboard.scss
    └── description/
        └── icon.png
```

---

## ⚙️ Installation

1. Copy `odoo_webhook_engine` to your custom addons directory
2. Update the addons path in your Odoo config
3. Restart Odoo and update the apps list
4. Install **Webhook Event Engine** from the Apps menu

### Python Dependencies

```bash
pip install jinja2 requests
```

---

## 🚀 Quick Start

### 1. Create a Webhook Rule

- Go to **Webhooks → Outgoing Webhooks → Webhook Rules**
- Click **Create**
- Select a model (e.g., `sale.order`)
- Choose an event (e.g., _On State Change_)
- Set the target URL (e.g., `https://hooks.slack.com/services/...`)
- Configure the payload (pick fields or write a Jinja2 template)
- Save & activate

### 2. Test It

- Click **🧪 Test Webhook** to send a sample payload
- Check **📋 Delivery Logs** for the request/response

### 3. Set Up Incoming Webhooks

- Go to **Webhooks → Incoming Webhooks → Endpoints**
- Create an endpoint with a unique slug
- Configure authentication & action
- External systems can now POST to `/webhook/incoming/<slug>`

---

## 🔐 HMAC Signature Verification

When a secret key is configured, every outgoing request includes:

```
X-Odoo-Signature: <HMAC-SHA256 hex digest>
```

**Verify in your receiving server (Python example):**

```python
import hmac, hashlib

def verify(payload_bytes, secret, signature):
    expected = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

---

## 📊 Example Payload (Field Picker Mode)

```json
{
  "event": "on_state_change",
  "model": "sale.order",
  "record_id": 45,
  "data": {
    "order_id": 45,
    "customer": {
      "id": 12,
      "name": "John Doe",
      "email": "john@example.com"
    },
    "total": 1200.0,
    "items": [
      { "id": 1, "display_name": "Product A" },
      { "id": 2, "display_name": "Product B" }
    ]
  },
  "timestamp": "2026-02-12T10:30:00.000000"
}
```

---

## 🎯 Use Cases

| Trigger               | Action                    |
| --------------------- | ------------------------- |
| New CRM lead          | Notify Slack channel      |
| Order confirmed       | Trigger shipping API      |
| Payment received      | Sync to accounting system |
| Stock below threshold | Alert supplier via API    |
| Employee created      | Sync to payroll system    |
| Invoice validated     | Push to external ERP      |

---

## 📋 Cron Jobs

| Job               | Interval  | Purpose                                 |
| ----------------- | --------- | --------------------------------------- |
| Install ORM Hooks | Daily     | Patches model CRUD for active rules     |
| Process Retries   | 5 minutes | Retries pending failed deliveries       |
| Cleanup Old Logs  | Daily     | Removes success logs older than 30 days |

---

## 🏢 Multi-Company

- Rules, logs, and incoming endpoints are company-isolated
- Record rules enforce `company_id` filtering
- Each company can have independent webhook configurations

---

## 📝 License

LGPL-3 — Odoo Proprietary License v1.0

**Author:** Aura Odoo Tech  
**Website:** [auraodoo.tech](https://www.auraodoo.tech/)
