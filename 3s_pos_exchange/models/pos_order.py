from odoo import models, fields, api
from datetime import timedelta

class PosOrder(models.Model):
    _inherit = "pos.order"

    @api.model
    def search_paid_order_ids(self, config_id, domain=None, limit=100, offset=0):
        domain = domain or []

        date_from = fields.Datetime.now() - timedelta(days=14)

        domain.append(("date_order", ">=", date_from))

        return super().search_paid_order_ids(
            config_id=config_id,
            domain=domain,
            limit=limit,
            offset=offset,
        )
