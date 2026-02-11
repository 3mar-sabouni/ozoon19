/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { useService } from "@web/core/utils/hooks";

patch(ControlButtons.prototype, {
	setup() {
        super.setup();
        this.report = useService("report");
    },
    
    onClickSessionReport() {
        var self = this.env;
        var pos_session_id = self.services.pos.session.id; //this.pos.session.id for v_18
        this.report.doAction('pos_session_z_report_omax.action_report_session_z', [pos_session_id]);
    },
    
    get omaxSessionZreport() {
        return this.pos.config.omax_session_z_report;
    }
});
