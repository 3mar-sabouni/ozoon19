from odoo import models, fields

class PosConfig(models.Model):
    _inherit = "pos.config"

    exchange_order_days = fields.Integer(
        string="Exchange Order History (Days)",
        default=14,
        help="Number of past days to load paid POS orders for exchange/refund."
    )
