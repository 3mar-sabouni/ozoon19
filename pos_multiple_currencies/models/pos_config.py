# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    multi_currency_payment = fields.Boolean(
        'Multi Currency', help='To enable multi currency payment in pos'
    )
    payment_currency_ids = fields.Many2many(
        'res.currency', string="Currencies"
    )
class POSOrderLoad(models.Model):
    _inherit = 'pos.session'

    def get_closing_control_data(self):
        data = super().get_closing_control_data()

        orders = self._get_closed_orders()
        payments = orders.payment_ids.filtered(lambda p: p.payment_method_id.type != "pay_later")

        def group_payments_by_employee_and_currency(payment_records):
            employee_grouped = {}
            currency_grouped = {}

            for payment in payment_records:
                if (payment.selected_currency_symbol and
                        payment.selected_currency_symbol != '0' and
                        payment.selected_currency_symbol != False):

                    currency_symbol = payment.selected_currency_symbol
                    if (payment.currency_amount_total and
                            payment.currency_amount_total != 0.0 and
                            payment.currency_amount_total != False):
                        amount_to_use = payment.currency_amount_total
                    else:
                        amount_to_use = payment.amount
                else:
                    currency_symbol = self.currency_id.symbol
                    amount_to_use = payment.amount

                currency = self.env['res.currency'].search([('symbol', '=', currency_symbol)], limit=1)
                currency_name = currency.name if currency else currency_symbol

                employee_id = payment.employee_id.id if hasattr(payment, 'employee_id') else False
                employee_name = payment.employee_id.name if hasattr(payment, 'employee_id') else None

                if hasattr(payment, 'employee_id'):
                    if payment.employee_id:
                        key = (employee_id, employee_name, currency_symbol)
                        if key not in employee_grouped:
                            employee_grouped[key] = {
                                'employee_id': employee_id,
                                'employee_name': employee_name,
                                'currency_symbol': currency_symbol,
                                'currency_name': currency_name,
                                'display_name': f"{employee_name} - {currency_symbol}",
                                'amount': 0.0,
                                'base_amount': 0.0,
                                'count': 0,
                                'uses_foreign_currency': currency_symbol != self.currency_id.symbol,
                                'group_type': 'employee_currency'
                            }
                        employee_grouped[key]['amount'] += amount_to_use
                        employee_grouped[key]['base_amount'] += payment.amount
                        employee_grouped[key]['count'] += 1
                    else:
                        key = (currency_symbol, currency_name)
                        if key not in currency_grouped:
                            currency_grouped[key] = {
                                'employee_id': False,
                                'employee_name': None,
                                'currency_symbol': currency_symbol,
                                'currency_name': currency_name,
                                'display_name': f"{currency_name}",
                                'amount': 0.0,
                                'base_amount': 0.0,
                                'count': 0,
                                'uses_foreign_currency': currency_symbol != self.currency_id.symbol,
                                'group_type': 'currency_only'
                            }
                        currency_grouped[key]['amount'] += amount_to_use
                        currency_grouped[key]['base_amount'] += payment.amount
                        currency_grouped[key]['count'] += 1
                else:
                    key = (currency_symbol, currency_name)
                    if key not in currency_grouped:
                        currency_grouped[key] = {
                            'employee_id': False,
                            'employee_name': None,
                            'currency_symbol': currency_symbol,
                            'currency_name': currency_name,
                            'display_name': f"{currency_name}",
                            'amount': 0.0,
                            'base_amount': 0.0,
                            'count': 0,
                            'uses_foreign_currency': currency_symbol != self.currency_id.symbol,
                            'group_type': 'currency_only'
                        }
                    currency_grouped[key]['amount'] += amount_to_use
                    currency_grouped[key]['base_amount'] += payment.amount
                    currency_grouped[key]['count'] += 1

            employee_result = list(employee_grouped.values())
            currency_result = list(currency_grouped.values())

            employee_result.sort(key=lambda x: (x['employee_name'], x['currency_symbol']))
            currency_result.sort(key=lambda x: x['currency_name'])

            return employee_result + currency_result

        cash_payment_method_ids = self.payment_method_ids.filtered(lambda pm: pm.type == 'cash')
        default_cash_payment_method_id = cash_payment_method_ids[0] if cash_payment_method_ids else None
        default_cash_payments = payments.filtered(
            lambda p: p.payment_method_id == default_cash_payment_method_id) if default_cash_payment_method_id else \
            self.env['pos.payment']

        non_cash_payment_method_ids = self.payment_method_ids - default_cash_payment_method_id if default_cash_payment_method_id else self.payment_method_ids
        non_cash_payments_grouped_by_method_id = {pm.id: orders.payment_ids.filtered(lambda p: p.payment_method_id == pm)
                                                  for pm in non_cash_payment_method_ids}

        if default_cash_payment_method_id:
            data['default_cash_details']['employee_currency_breakdown'] = group_payments_by_employee_and_currency(
                default_cash_payments)

        for payment_method in data['non_cash_payment_methods']:
            pm_payments = non_cash_payments_grouped_by_method_id.get(payment_method['id'], self.env['pos.payment'])
            payment_method['employee_currency_breakdown'] = group_payments_by_employee_and_currency(pm_payments)
        return data