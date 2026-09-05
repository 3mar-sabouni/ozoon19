from odoo import api, fields, models

from ..utils.text import stable_slug


class EcommerceIntegrationBinding(models.Model):
    _name = "ecommerce.integration.binding"
    _description = "Ecommerce External Binding"
    _order = "write_date desc, id desc"

    instance_id = fields.Many2one(
        "ecommerce.integration.instance",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        related="instance_id.company_id",
        store=True,
        index=True,
    )
    model_name = fields.Selection(
        [
            ("product.category", "Product Category"),
            ("product.template", "Product Template"),
            ("product.product", "Product Variant"),
            ("product.attribute", "Product Attribute"),
            ("sale.order", "Sales Order"),
        ],
        required=True,
        index=True,
    )
    res_id = fields.Integer(required=True, index=True)
    record_name = fields.Char(compute="_compute_record_name", store=False)
    external_id = fields.Char(index=True, copy=False)
    handle = fields.Char(copy=False)
    sync_state = fields.Selection(
        [
            ("new", "New"),
            ("synced", "Synced"),
            ("error", "Error"),
        ],
        default="new",
        required=True,
        index=True,
    )
    last_sync_at = fields.Datetime(copy=False, index=True)
    last_error = fields.Text(copy=False)

    _sql_constraints = [
        (
            "instance_model_res_unique",
            "unique(instance_id, model_name, res_id)",
            "A record can only have one binding per ecommerce instance.",
        ),
    ]

    @api.depends("model_name", "res_id")
    def _compute_record_name(self):
        for binding in self:
            name = False
            if binding.model_name and binding.res_id and binding.model_name in self.env:
                record = self.env[binding.model_name].browse(binding.res_id).exists()
                name = record.display_name if record else False
            binding.record_name = name or f"{binding.model_name or 'record'}:{binding.res_id or 0}"

    @api.model
    def get_or_create(self, instance, record, *, handle_seed=None):
        binding = self.search(
            [
                ("instance_id", "=", instance.id),
                ("model_name", "=", record._name),
                ("res_id", "=", record.id),
            ],
            limit=1,
        )
        if binding:
            if handle_seed and not binding.handle:
                binding.handle = stable_slug(handle_seed, f"odoo-{record._name.replace('.', '-')}-{record.id}")
            return binding

        vals = {
            "instance_id": instance.id,
            "model_name": record._name,
            "res_id": record.id,
        }
        if handle_seed:
            vals["handle"] = stable_slug(
                handle_seed,
                f"odoo-{record._name.replace('.', '-')}-{record.id}",
            )
        return self.create(vals)
