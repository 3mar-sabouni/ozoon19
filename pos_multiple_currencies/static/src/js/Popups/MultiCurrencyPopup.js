/** @odoo-module **/
import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { floatIsZero, roundPrecision } from "@web/core/utils/numbers";


export class MultiCurrencyPopup extends Component {
    static template = "pos_multiple_currencies.MultiCurrencyPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        payment_method: { type: Object, optional: false },
        getPayload: { type: Function },
    };

    setup() {
        super.setup();
        this.pos = usePos();
        
        const baseCurrencyName = this.pos.currency?.name;

        this.values = (this.pos.multicurrencypayment || []).filter(c => c.name !== baseCurrencyName);
        this.payment_methods = (this.props.payment_method || []).filter(pm => !pm.name.toUpperCase().includes("AED"));
        const order = this.pos.getOrder();
        console.log("POS ORDER OBJECT:", order);
        this.AmountTotal = order ? order.remainingDue : 0;

        this.default_currency = this.pos.currency || { name: "" };

        if (!this.values.length) {
            this.selected_curr_name = "";
            this.selected_rate = 1;
            this.inverse_rate = 1;
            this.symbol = "";
            this.amount_total_currency = "0.00";
            return;
        }

        const currency = this.values[0];
        this.selected_curr_name = currency.name;
        this.selected_rate = currency.rate;
        this.inverse_rate = currency.inverse_rate || 1;
        this.symbol = currency.symbol;

        this.amount_total_currency = (this.AmountTotal / this.inverse_rate).toFixed(4);
    }



    getValues(event) {
        this.selected_value = this.values.find(
            val => val.id === Number(event.target.value)
        );

        if (!this.selected_value) return;

        this.selected_curr_name = this.selected_value.name;
        this.selected_rate = this.selected_value.rate;
        this.inverse_rate = this.selected_value.inverse_rate || 1;
        this.symbol = this.selected_value.symbol;

        this.amount_total_currency =
            (this.AmountTotal / this.inverse_rate).toFixed(4);

        this.render();
    }

    //    getPayload() {
    //        return {
    //            currency_name: this.selected_curr_name,
    //            selected_rate: this.selected_rate,
    //            inverse_rate: this.inverse_rate,
    //            symbol: this.symbol,
    //        }
    //    }

    confirm(ev) {
        this.props.getPayload({
            currency_name: this.selected_curr_name,
            selected_rate: this.selected_rate,
            inverse_rate: this.inverse_rate,
            symbol: this.symbol,
        })
        this.props.close()
    }
}
