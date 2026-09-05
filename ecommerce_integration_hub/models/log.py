from odoo import fields, models


class EcommerceIntegrationLog(models.Model):
    _name = "ecommerce.integration.log"
    _description = "Ecommerce Sync Log"
    _order = "create_date desc, id desc"
    _rec_name = "summary"

    instance_id = fields.Many2one(
        "ecommerce.integration.instance",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="instance_id.company_id", store=True, index=True)
    queue_id = fields.Many2one("ecommerce.integration.queue", ondelete="set null", index=True)
    sync_type = fields.Selection(
        [
            ("category", "Category"),
            ("attribute", "Attribute"),
            ("product", "Product"),
            ("stock", "Stock"),
            ("order", "Store Order"),
            ("order_status", "Store Order Status"),
        ],
        required=True,
        index=True,
    )
    direction = fields.Selection(
        [("out", "Odoo → Store"), ("in", "Store → Odoo")],
        default="out",
        required=True,
        index=True,
    )
    status = fields.Selection(
        [("success", "Success"), ("warning", "Warning"), ("failure", "Failure")],
        required=True,
        index=True,
    )
    model_name = fields.Char(index=True)
    res_id = fields.Integer(index=True)
    summary = fields.Char(required=True)
    http_status = fields.Integer()
    attempt = fields.Integer(default=1)
    duration_ms = fields.Integer()
    request_json = fields.Text()
    response_json = fields.Text()
    error_message = fields.Text()
