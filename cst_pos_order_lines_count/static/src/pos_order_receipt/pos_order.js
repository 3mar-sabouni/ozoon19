/** @odoo-module */
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";

patch(PosOrder.prototype, {
    get itemCount(){
       return this.lines?.length
    },

    get totalQuantity(){
       return this.lines?.reduce((sum, line) => sum + line.getQuantity(), 0);
    },


});