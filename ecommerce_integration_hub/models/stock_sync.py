from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_done(self, cancel_backorder=False):
        done_moves = super()._action_done(cancel_backorder=cancel_backorder)
        if self.env.context.get("ecommerce_skip_enqueue"):
            return done_moves

        Queue = self.env["ecommerce.integration.queue"].sudo()
        for company in done_moves.mapped("company_id"):
            products = (
                done_moves.filtered(lambda move: move.company_id == company)
                .mapped("product_id")
                .filtered("is_storable")
            )
            if not products:
                continue
            instances = self.env["ecommerce.integration.instance"].sudo().search(
                [
                    ("active", "=", True),
                    ("auto_sync_stock", "=", True),
                    ("company_id", "=", company.id),
                ]
            )
            for instance in instances:
                for product in products:
                    if instance._template_should_sync(product.product_tmpl_id):
                        Queue.enqueue(instance, "stock", product, priority=40)
        return done_moves
