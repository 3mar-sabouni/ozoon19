# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class PosPayment(models.Model):
    _inherit = 'pos.payment'

    selected_currency_rate = fields.Float(
        string='Conversion Rate', help='Conversion rate of currency.'
    )
    selected_currency_symbol = fields.Char(
        string='Currency', help='Currency Symbol.'
    )
    currency_amount_total = fields.Float(
        string='Amount Currency', help='Amount Total in Selected Currency.'
    )
    is_multi_currency = fields.Boolean(
        related='pos_order_id.config_id.multi_currency_payment',
        readonly=False
    )

    def _export_for_ui(self, payment):
        result = super(PosPayment, self)._export_for_ui(payment)
        result['selected_currency_rate'] = payment.selected_currency_rate
        result['selected_currency_symbol'] = payment.selected_currency_symbol
        result['currency_amount_total'] = payment.currency_amount_total
        return result
