/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { MultiCurrencyPopup } from "../Popups/MultiCurrencyPopup"
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { floatIsZero, roundPrecision } from "@web/core/utils/numbers";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.dialog = useService("dialog");
    },
    async payMultipleCurrency() {
        if (this.pos.multicurrencypayment.length > 0) {
            var payment_method_data = []
            this.payment_methods_from_config.forEach(function (id) {
                payment_method_data.push(id);
            });
            const payload = await makeAwaitable(this.dialog, MultiCurrencyPopup, {
                'payment_method': payment_method_data,
            });

            if (payload) {
                if (document.querySelector('.pay_amount').value) {
                    var payment_method = parseInt(document.querySelector('.payment-method-select').value)
                    var currency_amount = parseFloat(document.querySelector('.pay_amount').value)
                    var get_amount = currency_amount * payload.inverse_rate
                    if (this.pos.config.cash_rounding) {
                        var cash_rounding = this.pos.config.rounding_method.rounding;
                        get_amount = roundPrecision(get_amount, cash_rounding);
                    }
                    let result = this.currentOrder.addPaymentline(this.pos.config.payment_method_ids.filter(l => l.id === payment_method)[0]);
                    this.selectedPaymentLine.setAmount(get_amount);
                    this.selectedPaymentLine.set_selected_currency(payload.currency_name);
                    this.selectedPaymentLine.set_currency_symbol(payload.symbol);
                    this.selectedPaymentLine.set_currency_rate(payload.inverse_rate);
                    this.selectedPaymentLine.set_currency_amount_paid(currency_amount);
                }
                else {
                    this.dialog.add(AlertDialog, {
                        title: _t("Amount Not Added"),
                        body: _t('Please Enter the Amount!!'),
                    });
                }
            }
            else {
                return
            }
        }
        else {
            this.dialog.add(AlertDialog, {
                title: _t("Currency Not Configured"),
                body: _t('Please Configure The Currency For Multi-Currency Payment.'),
            });
            return;
        }
    }
})


