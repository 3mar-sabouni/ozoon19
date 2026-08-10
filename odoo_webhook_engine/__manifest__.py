# -*- coding: utf-8 -*-
{
    'name': 'Webhook Event Engine',
    'version': '19.0.1.0.0',
    'category': 'Technical/Automation',
    'summary': 'Real-time outgoing & incoming webhooks with retry engine, payload builder, HMAC signatures & analytics dashboard',
    'description': """
        🚀 Webhook Event Engine - Odoo 19
        ====================================

        Replace Zapier — push data from Odoo to any external system in real time.

        Odoo Event → Webhook Engine → External App

        🔥 Key Features:
        ----------------
        ✅ Event-driven outgoing webhooks (create / write / unlink / state change)
        ✅ Powerful rule builder — model, event type, domain filter
        ✅ Flexible payload builder — pick fields, nested relations, custom JSON
        ✅ Jinja2 template support for advanced payload transformation
        ✅ HMAC-SHA256 request signing (X-Odoo-Signature header)
        ✅ Exponential-backoff retry engine with dead-letter queue
        ✅ Comprehensive request/response logging with execution time
        ✅ Incoming webhook endpoints with API-key & IP-restriction security
        ✅ OWL 2 analytics dashboard — success rate, top endpoints, response times
        ✅ Cron-based automatic retries & log cleanup
        ✅ Multi-company isolation
        ✅ Event simulation / test mode

        💡 Perfect for:
        - CRM → Slack / Teams notifications
        - Sales → Warehouse / Shipping API triggers
        - Inventory → Supplier reorder alerts
        - HR → Payroll system sync
        - Payments → Accounting system sync
        - Any model → Any external HTTP endpoint

        🛠️ Technical:
        - Hooks into Odoo ORM create/write/unlink at model level
        - Async-safe HTTP dispatch via requests library
        - HMAC-SHA256 payload signing
        - Jinja2 template engine for payloads
        - OWL 2 dashboard components
    """,
    'author': 'Aura Odoo Tech',
    'website': 'https://www.auraodoo.tech/',
    'license': 'LGPL-3',
 
    'depends': [
        'base',
        'web',
        'mail',
    ],
    'data': [
        'security/webhook_security.xml',
        'security/ir.model.access.csv',
        'data/cron.xml',
        'data/webhook_event_data.xml',
        'views/webhook_rule_views.xml',
        'views/webhook_log_views.xml',
        'views/webhook_event_views.xml',
        'views/webhook_incoming_views.xml',
        'views/dashboard_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'odoo_webhook_engine/static/src/scss/dashboard.scss',
            'odoo_webhook_engine/static/src/js/dashboard/webhook_dashboard.js',
            'odoo_webhook_engine/static/src/js/dashboard/webhook_dashboard.xml',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'external_dependencies': {
        'python': ['jinja2', 'requests'],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
