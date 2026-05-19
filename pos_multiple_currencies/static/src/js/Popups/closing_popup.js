/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";
import { onMounted } from "@odoo/owl";

const _original_setup = ClosePosPopup.prototype.setup;

patch(ClosePosPopup.prototype, {
    setup() {
        // ✅ keep original behavior
        if (_original_setup) {
            _original_setup.apply(this, arguments);
        }

        const defaultCash = this.props?.default_cash_details;
        const nonCash = this.props?.non_cash_payment_methods;

        if (defaultCash && Array.isArray(nonCash)) {
            let extraAmount = 0;

            // ensure breakdown exists
            defaultCash.employee_currency_breakdown =
                defaultCash.employee_currency_breakdown || [];

            nonCash.forEach(pm => {
                if (pm.name?.includes("$")) {
                    // 🔹 merge into AED totals
                    extraAmount += pm.amount || 0;

                    // 🔹 add $ as reference line in payments breakdown
                    if (pm.employee_currency_breakdown) {
                        pm.employee_currency_breakdown.forEach(b => {
                            defaultCash.employee_currency_breakdown.push({
                                employee_id: b.employee_id,
                                display_name: b.display_name,
                                currency_symbol: b.currency_symbol || "$",
                                amount: b.amount,
                            });
                        });
                    }
                }
            });

            if (extraAmount) {
                defaultCash.amount += extraAmount;
                defaultCash.payment_amount += extraAmount;

                // 🔹 remove $ payment method so it doesn't affect difference
                this.props.non_cash_payment_methods =
                    nonCash.filter(pm => !pm.name?.includes("$")|| pm.type === "bank" || pm.type === "card");
            }
        }

        // ✅ KEEP your old DOM logic untouched
        onMounted(() => {
            const root = document.querySelector(".close-pos-popup");
            if (!root) return;

            const repeatedBlocks = root.querySelectorAll(".w-100.mb-3.repeated");
            if (!repeatedBlocks.length) return;

            root.querySelectorAll(".w-100.mb-3").forEach(block => {
                if (!block.classList.contains("repeated")) {
                    block.style.display = "none";
                }
            });
        });
    },
});
