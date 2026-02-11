# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_multi_currency_payment = fields.Boolean(
        related='pos_config_id.multi_currency_payment',
        readonly=False
    )
    main_currency = fields.Many2one('res.currency', string="Main Currency",related="pos_config_id.currency_id")
    pos_payment_currency_ids = fields.Many2many(
        related='pos_config_id.payment_currency_ids',
        readonly=False,
        string="POS Payment Currency",
        domain="[('id','!=',main_currency)]"
    )
