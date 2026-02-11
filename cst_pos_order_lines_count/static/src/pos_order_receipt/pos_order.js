/** @odoo-module */

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    get itemCount() {
        const discountVariantId =
            this.config?.discount_product_id
                ?.product_variant_ids?.[0]?.id || null;

        const filteredLines = this.lines?.filter((line) =>
            !(discountVariantId && line.product_id?.id === discountVariantId)
        ) || [];

        return filteredLines.length;
    },

    get totalQuantity() {
        const discountVariantId =
            this.config?.discount_product_id
                ?.product_variant_ids?.[0]?.id || null;

        const filteredLines = this.lines?.filter((line) =>
            !(discountVariantId && line.product_id?.id === discountVariantId)
        ) || [];

        return filteredLines.reduce(
            (sum, line) => sum + line.getQuantity(),
            0
        );
    },
});
