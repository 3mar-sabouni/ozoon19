/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";

patch(ControlButtons.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
    },

    onExchangeClick() {
        this.pos.navigate("ExchangeScreen");
    },
});
