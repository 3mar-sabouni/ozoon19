/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";

function recomputeDiscount(order, pos) {
    if (!order || !pos) return;

    const discountProduct = pos.config.discount_product_id;
    if (!discountProduct) return;

    const discountProductId = discountProduct.id || discountProduct;

    const lines = order.getOrderlines();

    const discountLine = lines.find(
        (l) => l.product_id?.id === discountProductId
    );

    if (!discountLine) return;

    const base = lines
        .filter((l) => l !== discountLine && l.product_id && l.qty > 0)
        .reduce((sum, l) => sum + (l.price_subtotal || 0), 0);

    if (!base || base <= 0) {
        discountLine.setUnitPrice(0);
        return;
    }

    const currentDiscount = Math.abs(Number(discountLine.price_unit) || 0);

    const ratio = currentDiscount / base;

    const newDiscount = base * ratio;

    if (!Number.isFinite(newDiscount)) return;

    discountLine.setUnitPrice(-Number(newDiscount.toFixed(2)));
}

patch(OrderSummary.prototype, {
    _setValue(val) {
        const res = super._setValue(val);

        const order = this.pos.getOrder();

        // Delay recalculation until order update is finished
        setTimeout(() => {
            recomputeDiscount(order, this.pos);
        }, 0);

        return res;
    },
});