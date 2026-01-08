
from io import BytesIO
from barcode.ean import EAN13
from odoo import models, api,fields, _
from datetime import datetime
import random
import base64
from barcode.writer import ImageWriter


class ProductProduct(models.Model):
    _inherit = "product.product"

    is_barcode = fields.Boolean('Check Barcode Setting')
    image_product = fields.Binary('Barcode Image')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        barcode_generate = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("cap.barcode_generate")
        )
        if not barcode_generate:
            res["is_barcode"] = True
        return res

    @api.model
    def create(self, vals):
        res = super().create(vals)

        barcode_generate = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("cap.barcode_generate")
        )
        option_generated = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("cap.option_generated", default="date")
        )

        if barcode_generate and not res.barcode:
            if option_generated == "date":
                barcode_str = self.env["barcode.nomenclature"].sanitize_ean(
                    "%s%s" % (res.id, datetime.now().strftime("%d%m%y%H%M"))
                )
            else:
                number_random = int("%0.13d" % random.randint(0, 999999999999))
                barcode_str = self.env["barcode.nomenclature"].sanitize_ean(str(number_random))

            ean = EAN13(barcode_str, writer=ImageWriter())
            image = ean.render()

            buffer = BytesIO()
            image.save(buffer, format="PNG")

            res.write({
                "barcode": barcode_str,
                "image_product": base64.b64encode(buffer.getvalue()),
            })

        return res



