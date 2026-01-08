
from odoo import fields, models, api, _


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    barcode_generate = fields.Boolean(
        "Generate Barcode EAN13 From Product",
        config_parameter="cap.barcode_generate",
    )

    option_generated = fields.Selection(
        [
            ("date", "Generate Barcode EAN13 through Current Date"),
            ("random", "Generate Barcode EAN13 through Random Number"),
        ],
        string="Generate Barcode Option",
        default="date",
        config_parameter="cap.option_generated",
    )
