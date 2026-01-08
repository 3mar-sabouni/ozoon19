# Copyright 2016 Tecnativa - Sergio Teruel
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import api, fields, models
from odoo.tools import config


class ProductProduct(models.Model):
    _inherit = "product.product"

    lst_price = fields.Float(
        compute="_compute_lst_price",
        inverse="_inverse_product_lst_price",
    )
    list_price = fields.Float(
        compute="_compute_list_price",
    )
    fix_price = fields.Float()

    @api.depends("fix_price")
    def _compute_lst_price(self):
        uom_model = self.env["uom.uom"]
        for product in self:
            price = product.fix_price or product.list_price
            if self.env.context.get("uom"):
                context_uom = uom_model.browse(self.env.context["uom"])
                price = product.uom_id._compute_price(price, context_uom)
            product.lst_price = price

    def _compute_list_price(self):
        uom_model = self.env["uom.uom"]
        for product in self:
            price = product.fix_price or product.product_tmpl_id.list_price
            if self.env.context.get("uom"):
                context_uom = uom_model.browse(self.env.context["uom"])
                price = product.uom_id._compute_price(price, context_uom)
            product.list_price = price

    def _inverse_product_lst_price(self):
        uom_model = self.env["uom.uom"]
        for product in self:
            if self.env.context.get("uom"):
                fix_price = product.uom_id._compute_price(
                    product.lst_price,
                    uom_model.browse(self.env.context["uom"]),
                )
            else:
                fix_price = product.lst_price

            # ONLY update the variant
            product.fix_price = fix_price

    def _compute_product_price_extra(self):
        """the sale.order.line module calculates the price_unit by adding
        the value of price_extra and this can generate inconsistencies
        if the field has old data stored."""
        res = super()._compute_product_price_extra()
        test_condition = not config["test_enable"] or (
            config["test_enable"]
            and self.env.context.get("test_product_variant_sale_price")
        )
        if test_condition:
            self.price_extra = 0.0
        return res
