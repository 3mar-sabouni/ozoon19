/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { ConnectionLostError } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

import { ExchangePopup } from "@3s_pos_exchange/js/exchange_popup";

export class ExchangeScreen extends Component {
    static template = "3s_pos_exchange.ExchangeScreen";

    setup() {
        this.pos = usePos();
        this.dialog = useService("dialog");

        this.state = useState({
            orders: [],
            filteredOrders: [],
            selectedOrder: null,
            loading: true,
            searchTerm: "",
        });

        onWillStart(async () => {
            await this.pos.ready;
            this.state.loading = false;
        });
    }


    // =================================================
    // SELECT ORDER
    // =================================================
    selectOrder(order) {
        this.state.selectedOrder = {
            pos_reference: order.pos_reference,
            name: order.name,
            partner: order.getPartnerName(),
            date_order: order.date_order?.toString?.() || "",
            total: order.amount_total,
            lines: order.getOrderlines().map((l) => ({
                product: l.product_id.display_name,
                qty: l.qty,
                price_unit: l.price_unit,
                subtotal: l.price_subtotal,
            })),
            payments: order.payment_ids.map((p) => ({
                method: p.payment_method_id.name,
                amount: p.amount,
            })),
        };
    }

    back() {
        this.pos.navigate("ProductScreen");
    }

    // =================================================
    // CONFIRM EXCHANGE
    // =================================================
    async confirmExchange() {
        if (!this.state.selectedOrder) return;

        const originalOrder = this.pos.models["pos.order"].find(
            (o) => o.pos_reference === this.state.selectedOrder.pos_reference
        );
        if (!originalOrder) return;

        // 1) Popup: choose qty
        const result = await makeAwaitable(
            this.dialog,
            ExchangePopup,
            { order: originalOrder }
        );
        console.log("POPUP RESULT:", result);
        if (!result?.confirmed) return;
        if (!result.lines || !result.lines.length) {
            this.dialog.add(AlertDialog, {
                title: _t("Nothing to exchange"),
                body: _t("Please select at least one item."),
            });
            return;
        }

        // 2) Create refund order and set it as current
        const exchangeOrder = this.pos.addNewOrder();
        this.pos.setOrder(exchangeOrder);

        const discountTemplate = this.pos.config.discount_product_id || null;
        const discountVariant = discountTemplate?.product_variant_ids?.[0] || null;
        const discountVariantId = discountVariant?.id || null;

        // Original base (exclude discount line)
        const originalBase = originalOrder
            .getOrderlines()
            .filter((l) => {
                if (!l.product_id) return false;
                if (l.qty <= 0) return false;
                if (discountVariantId && l.product_id.id === discountVariantId) return false;
                return true;
            })
            .reduce((s, l) => s + (l.price_subtotal || 0), 0);

        // Get original discount amount (positive number)
        let originalDiscountAbs = 0;
        if (discountVariantId) {
            const dline = originalOrder.getOrderlines().find((l) => l.product_id?.id === discountVariantId);
            if (dline) {
                // discount line is usually negative price_unit
                originalDiscountAbs = Math.abs(dline.price_unit || 0);
            }
        }

        const discountRatio = originalBase > 0 ? originalDiscountAbs / originalBase : 0;

        // 3) Create refund lines only for selected qty
        let refundBase = 0;

        for (const sel of result.lines) {
            const originalLine = originalOrder.getOrderlines().find((l) => l.uuid === sel.uuid);
            if (!originalLine) continue;

            const qty = Number(sel.qty || 0);
            if (qty <= 0) continue;

            // IMPORTANT: product_id here MUST be product.product variant
            const variant = originalLine.product_id;
            if (!variant) continue;

            // Create line directly in refund order (variant => no variant popup)
            this.pos.models["pos.order.line"].create({
                qty: -qty,
                price_unit: originalLine.price_unit,
                product_id: variant,
                order_id: exchangeOrder,
                discount: originalLine.discount || 0,
                tax_ids: (originalLine.tax_ids || []).map((t) => ["link", t]),
                price_type: "automatic",
                attribute_value_ids: (originalLine.attribute_value_ids || []).map((a) => ["link", a]),
                refunded_orderline_id: originalLine, // helpful link
            });

            refundBase += (originalLine.price_subtotal || (originalLine.price_unit * qty));
        }

        if (refundBase <= 0) {
            this.dialog.add(AlertDialog, {
                title: _t("Nothing to exchange"),
                body: _t("Please select at least one item."),
            });
            return;
        }


        // 6) Go to Product Screen
        this.pos.navigate("ProductScreen", { orderUuid: exchangeOrder.uuid });
    }

    async searchOrders(reset = true) {
        const term = (this.state.searchTerm || "").trim();
        if (!term) return;

        if (reset) {
            this.state.offset = 0;
            this.state.filteredOrders = [];
            this.state.hasMore = true;
        }

        if (!this.state.hasMore) return;

        this.state.loading = true;

        try {
            const config_id = this.pos.config.id;

            const { ordersInfo } = await this.pos.data.call(
                "pos.order",
                "search_paid_order_ids",
                [],
                {
                    config_id,
                    domain: [["pos_reference", "ilike", term]],
                    limit: this.state.limit,
                    offset: this.state.offset,
                }
            );

            const ids = ordersInfo.map((o) => o[0]);

            if (ids.length) {
                await this.pos.data.loadServerOrders([["id", "in", ids]]);
            }

            const newOrders = this.pos.models["pos.order"].filter((o) =>
                ids.includes(o.id)
            );

            this.state.filteredOrders.push(...newOrders);

            this.state.offset += this.state.limit;

            if (ids.length < this.state.limit) {
                this.state.hasMore = false;
            }

        } catch (err) {
            if (!(err instanceof ConnectionLostError)) {
                throw err;
            }
        }

        this.state.loading = false;
    }

    onInput(ev) {
        this.state.searchTerm = ev.target.value;
    }

    onSearchClick() {
        this.searchOrders();
    }
}

registry.category("pos_pages").add("ExchangeScreen", {
    name: "ExchangeScreen",
    component: ExchangeScreen,
    route: `/pos/ui/${odoo.pos_config_id}/exchange`,
});
