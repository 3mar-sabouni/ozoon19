/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";

export class ExchangePopup extends Component {
    static template = "3s_pos_exchange.ExchangePopup";

    // ✅ REQUIRED IN OWL v2
    static components = { Dialog };

    // ✅ REQUIRED PROPS
    static props = {
        order: Object,
        close: Function,
        getPayload: Function, // injected by makeAwaitable
    };

    setup() {
        this.pos = usePos();
        const order = this.props.order;

        const discountProductId = this.pos.config.discount_product_id?.id;

        const lines = order.getOrderlines().filter((l) => {
            if (!l.product_id) return false;
            if (discountProductId && l.product_id.id === discountProductId) return false;
            if (l.qty <= 0) return false;
            return true;
        });

        this.state = useState({
            lines: lines.map((l) => ({
                uuid: l.uuid,
                product: l.product_id.display_name,
                maxQty: l.qty,
                qty: l.qty,
            })),
        });
    }

    confirm() {
        const lines = this.state.lines
            .filter((l) => l.qty > 0)
            .map((l) => ({
                uuid: l.uuid,
                qty: l.qty,
            }));

        this.props.getPayload({
            confirmed: true,
            lines,
        });
        this.props.close();
    }

    cancel() {
        this.props.getPayload({ confirmed: false });
        this.props.close();
    }

}
