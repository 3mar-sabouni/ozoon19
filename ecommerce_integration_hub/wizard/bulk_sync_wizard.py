from odoo import _, fields, models


class EcommerceIntegrationBulkSyncWizard(models.TransientModel):
    _name = "ecommerce.integration.bulk.sync.wizard"
    _description = "Bulk Ecommerce Synchronization"

    instance_id = fields.Many2one("ecommerce.integration.instance", required=True)
    sync_categories = fields.Boolean(default=True)
    sync_attributes = fields.Boolean(default=True)
    sync_products = fields.Boolean(default=True)
    sync_stock = fields.Boolean(
        default=True,
        help=(
            "Queues a stock reconciliation after product synchronization. "
            "Product creation already contains initial stock."
        ),
    )

    def action_queue_sync(self):
        self.ensure_one()
        instance = self.instance_id
        Queue = self.env["ecommerce.integration.queue"].sudo()

        scope_domain = lambda field: [
            ("ecommerce_integration_publish", "=", True),
            "|",
            (field, "=", False),
            (field, "in", instance.id),
        ]

        categories = self.env["product.category"].search(
            scope_domain("ecommerce_integration_instance_ids")
        )
        # Parent-first order is only a small optimization. Category sync itself is
        # deliberately order-independent and will reconcile hierarchy afterward.
        categories = categories.sorted(
            key=lambda cat: (len((cat.parent_path or "").split("/")), cat.id)
        )

        products = self.env["product.template"].with_company(instance.company_id).search(
            [
                ("active", "=", True),
                ("sale_ok", "=", True),
                ("company_id", "in", [False, instance.company_id.id]),
            ]
            + scope_domain("ecommerce_integration_instance_ids")
        )

        attributes = self.env["product.attribute"].search(
            scope_domain("ecommerce_integration_instance_ids")
        )

        if self.sync_categories:
            for category in categories:
                Queue.enqueue(instance, "category", category, priority=10)

        if self.sync_attributes:
            for attribute in attributes:
                Queue.enqueue(instance, "attribute", attribute, priority=20)

        if self.sync_products:
            for product in products:
                Queue.enqueue(instance, "product", product, priority=30)

        stock_variants = products.product_variant_ids.filtered("is_storable")
        if self.sync_stock:
            for variant in stock_variants:
                Queue.enqueue(instance, "stock", variant, priority=40)

        message = _(
            "Bulk synchronization queued for published records on %(instance)s: %(categories)s categories, "
            "%(attributes)s attributes (including their values), %(products)s products and %(variants)s stock variants.",
            instance=instance.display_name,
            categories=len(categories) if self.sync_categories else 0,
            attributes=len(attributes) if self.sync_attributes else 0,
            products=len(products) if self.sync_products else 0,
            variants=len(stock_variants) if self.sync_stock else 0,
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Bulk Sync Queued"),
                "message": message,
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
