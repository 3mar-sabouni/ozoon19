from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    ecommerce_integration_instance_id = fields.Many2one(
        "ecommerce.integration.instance",
        string="Ecommerce Instance",
        check_company=True,
        copy=False,
        index=True,
        groups="ecommerce_integration_hub.group_ecommerce_connector_user",
        help="Store/channel instance that created this sales order.",
    )
    ecommerce_external_order_id = fields.Char(string="External Order ID", copy=False, index=True)
    ecommerce_external_order_number = fields.Char(string="Store Order Number", copy=False, index=True)
    ecommerce_store_status = fields.Char(string="Store Order Status", copy=False, tracking=True)
    ecommerce_payment_status = fields.Char(string="Store Payment Status", copy=False, tracking=True)
    ecommerce_fulfillment_status = fields.Char(string="Store Fulfillment Status", copy=False, tracking=True)
    ecommerce_payment_method = fields.Char(string="Store Payment Method", copy=False)
    ecommerce_is_cod = fields.Boolean(string="Cash on Delivery", copy=False)
    ecommerce_last_event_id = fields.Char(string="Last Store Event ID", copy=False, index=True)
    ecommerce_last_status_at = fields.Datetime(string="Last Store Update", copy=False)
    ecommerce_return_status = fields.Char(string="Store Return Status", copy=False, tracking=True)
    ecommerce_return_reason = fields.Char(string="Return Reason", copy=False)
    ecommerce_return_sellable = fields.Boolean(string="Returned Item Sellable", copy=False)
    ecommerce_raw_status_json = fields.Text(string="Last Store Payload", copy=False)

    _sql_constraints = [
        (
            "ecommerce_instance_external_order_unique",
            "unique(ecommerce_integration_instance_id, ecommerce_external_order_id)",
            "The external order ID must be unique per ecommerce instance.",
        ),
    ]
