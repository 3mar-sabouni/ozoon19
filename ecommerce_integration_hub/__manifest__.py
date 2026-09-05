{
    "name": "Ecommerce Integration Hub",
    "summary": (
        "Generic multi-instance Odoo 19 ecommerce connector with publication scope, "
        "queued catalog/inventory synchronization, inbound store orders, and monitoring"
    ),
    "version": "19.0.1.0.9",
    "category": "Sales/E-Commerce",
    "license": "LGPL-3",
    "depends": [
        "web",
        "mail",
        "sale_management",
        "stock",
        "account",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "data/ir_cron.xml",
        "data/publishing_actions.xml",
        "views/instance_views.xml",
        "views/dashboard_views.xml",
        "views/publishing_views.xml",
        "views/queue_views.xml",
        "views/log_views.xml",
        "views/binding_views.xml",
        "views/bulk_sync_wizard_views.xml",
        "views/clear_logs_wizard_views.xml",
        "views/sale_order_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ecommerce_integration_hub/static/src/dashboard/dashboard.js",
            "ecommerce_integration_hub/static/src/dashboard/dashboard.xml",
            "ecommerce_integration_hub/static/src/dashboard/dashboard.css",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
