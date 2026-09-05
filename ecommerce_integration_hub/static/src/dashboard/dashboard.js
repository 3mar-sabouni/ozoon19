/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class EcommerceIntegrationDashboard extends Component {
    static template = "ecommerce_integration_hub.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            instances: [],
            instanceId: false,
            dateFrom: "",
            dateTo: "",
            preset: "current_month",
            data: null,
        });
        this._requestSerial = 0;

        onWillStart(async () => {
            const bootstrap = await this.orm.call(
                "ecommerce.integration.instance",
                "get_dashboard_bootstrap",
                []
            );
            this.state.instances = bootstrap.instances;
            this.state.instanceId = bootstrap.default_instance_id;
            this.state.dateFrom = bootstrap.default_date_from;
            this.state.dateTo = bootstrap.default_date_to;
            if (this.state.instanceId) {
                await this.loadDashboard();
            } else {
                this.state.loading = false;
            }
        });
    }

    async loadDashboard() {
        if (!this.state.instanceId || !this.state.dateFrom || !this.state.dateTo) {
            return;
        }
        const serial = ++this._requestSerial;
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "ecommerce.integration.instance",
                "get_dashboard_data",
                [this.state.instanceId, this.state.dateFrom, this.state.dateTo]
            );
            if (serial === this._requestSerial) {
                this.state.data = data;
            }
        } catch (error) {
            this.notification.add(
                error?.data?.message || error?.message || "Could not load ecommerce dashboard.",
                { type: "danger", title: "Dashboard" }
            );
        } finally {
            if (serial === this._requestSerial) {
                this.state.loading = false;
            }
        }
    }

    async onInstanceChange(ev) {
        this.state.instanceId = Number(ev.target.value) || false;
        await this.loadDashboard();
    }

    async onDateFromChange(ev) {
        this.state.dateFrom = ev.target.value;
        this.state.preset = "custom";
        if (this._dateRangeIsValid()) {
            await this.loadDashboard();
        }
    }

    async onDateToChange(ev) {
        this.state.dateTo = ev.target.value;
        this.state.preset = "custom";
        if (this._dateRangeIsValid()) {
            await this.loadDashboard();
        }
    }

    async onPresetChange(ev) {
        const preset = ev.target.value;
        this.state.preset = preset;
        if (preset === "custom") {
            return;
        }
        const today = this._todayLocal();
        let from = new Date(today);
        let to = new Date(today);
        if (preset === "today") {
            // no-op
        } else if (preset === "last_7") {
            from.setDate(from.getDate() - 6);
        } else if (preset === "last_30") {
            from.setDate(from.getDate() - 29);
        } else if (preset === "current_month") {
            from = new Date(today.getFullYear(), today.getMonth(), 1);
        } else if (preset === "previous_month") {
            from = new Date(today.getFullYear(), today.getMonth() - 1, 1);
            to = new Date(today.getFullYear(), today.getMonth(), 0);
        }
        this.state.dateFrom = this._dateToInput(from);
        this.state.dateTo = this._dateToInput(to);
        await this.loadDashboard();
    }

    _todayLocal() {
        const now = new Date();
        return new Date(now.getFullYear(), now.getMonth(), now.getDate());
    }

    _dateToInput(date) {
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, "0");
        const d = String(date.getDate()).padStart(2, "0");
        return `${y}-${m}-${d}`;
    }

    _dateRangeIsValid() {
        return this.state.dateFrom && this.state.dateTo && this.state.dateFrom <= this.state.dateTo;
    }

    get hasInstances() {
        return this.state.instances.length > 0;
    }

    get healthLabel() {
        const value = this.state.data?.instance?.health;
        return { ok: "Healthy", warning: "Attention", disabled: "Disabled" }[value] || value || "—";
    }

    get statusDonutStyle() {
        const logs = this.state.data?.logs;
        if (!logs || !logs.total) {
            return "background: conic-gradient(#e5e7eb 0 100%);";
        }
        const success = (logs.success / logs.total) * 100;
        const warning = (logs.warning / logs.total) * 100;
        const warningEnd = success + warning;
        return `background: conic-gradient(#16a34a 0 ${success}%, #f59e0b ${success}% ${warningEnd}%, #dc2626 ${warningEnd}% 100%);`;
    }

    get queueDonutStyle() {
        const queue = this.state.data?.queue;
        if (!queue || !queue.total) {
            return "background: conic-gradient(#e5e7eb 0 100%);";
        }
        const pending = (queue.pending / queue.total) * 100;
        const processing = (queue.processing / queue.total) * 100;
        const retry = (queue.retry / queue.total) * 100;
        const failed = (queue.failed / queue.total) * 100;
        const p2 = pending + processing;
        const p3 = p2 + retry;
        const p4 = p3 + failed;
        return `background: conic-gradient(#2563eb 0 ${pending}%, #7c3aed ${pending}% ${p2}%, #f59e0b ${p2}% ${p3}%, #dc2626 ${p3}% ${p4}%, #d1d5db ${p4}% 100%);`;
    }

    get trendChart() {
        const rows = this.state.data?.logs?.trend || [];
        const width = 1000;
        const height = 250;
        const left = 34;
        const right = 18;
        const top = 18;
        const bottom = 34;
        const innerWidth = width - left - right;
        const innerHeight = height - top - bottom;
        const max = Math.max(1, ...rows.map((row) => Math.max(row.total, row.success, row.failure)));

        const points = (key) => rows.map((row, index) => {
            const x = rows.length <= 1 ? left + innerWidth / 2 : left + (index / (rows.length - 1)) * innerWidth;
            const y = top + innerHeight - (row[key] / max) * innerHeight;
            return { x, y, value: row[key], date: row.date };
        });
        const asString = (items) => items.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
        const totalPoints = points("total");
        const successPoints = points("success");
        const failurePoints = points("failure");
        const labelStep = Math.max(1, Math.ceil(rows.length / 8));
        const labels = totalPoints.filter((_, index) => index % labelStep === 0 || index === rows.length - 1);

        return {
            width,
            height,
            max,
            total: asString(totalPoints),
            success: asString(successPoints),
            failure: asString(failurePoints),
            labels,
            successPoints,
            failurePoints,
        };
    }

    formatNumber(value) {
        return new Intl.NumberFormat().format(value || 0);
    }

    formatDate(value) {
        if (!value) {
            return "—";
        }
        const date = new Date(value.includes("T") ? value : value.replace(" ", "T") + "Z");
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return new Intl.DateTimeFormat(undefined, {
            month: "short",
            day: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        }).format(date);
    }

    formatDay(value) {
        if (!value) {
            return "";
        }
        const [year, month, day] = value.split("-").map(Number);
        const date = new Date(year, month - 1, day);
        return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
    }

    barWidth(value, total) {
        return `width:${total ? Math.max(0, (value / total) * 100) : 0}%;`;
    }

    queueAgeLabel(minutes) {
        if (!minutes) {
            return "No waiting jobs";
        }
        if (minutes < 60) {
            return `${minutes}m`;
        }
        const hours = Math.floor(minutes / 60);
        const mins = minutes % 60;
        if (hours < 24) {
            return `${hours}h ${mins}m`;
        }
        return `${Math.floor(hours / 24)}d ${hours % 24}h`;
    }

    statusClass(status) {
        return `eih-status eih-status--${status || "neutral"}`;
    }

    async openInstance() {
        if (!this.state.instanceId) {
            return;
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Ecommerce Instance",
            res_model: "ecommerce.integration.instance",
            res_id: this.state.instanceId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    _logDomain(extra = []) {
        const period = this.state.data?.period;
        return [
            ["instance_id", "=", this.state.instanceId],
            ["create_date", ">=", period?.utc_from || `${this.state.dateFrom} 00:00:00`],
            ["create_date", "<", period?.utc_to || `${this.state.dateTo} 23:59:59`],
            ...extra,
        ];
    }

    async openLogs(status = false, syncType = false) {
        const extra = [];
        if (status) {
            extra.push(["status", "=", status]);
        }
        if (syncType) {
            extra.push(["sync_type", "=", syncType]);
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Sync Logs",
            res_model: "ecommerce.integration.log",
            views: [[false, "list"], [false, "graph"], [false, "pivot"], [false, "form"]],
            domain: this._logDomain(extra),
            target: "current",
        });
    }

    async openLog(logId) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Sync Log",
            res_model: "ecommerce.integration.log",
            res_id: logId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openQueue(state = false) {
        const domain = [["instance_id", "=", this.state.instanceId]];
        if (state === "active") {
            domain.push(["state", "in", ["pending", "processing", "retry"]]);
        } else if (state) {
            domain.push(["state", "=", state]);
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Sync Queue",
            res_model: "ecommerce.integration.queue",
            views: [[false, "list"], [false, "form"]],
            domain,
            target: "current",
        });
    }

    async openBindings() {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Bindings",
            res_model: "ecommerce.integration.binding",
            views: [[false, "list"], [false, "form"]],
            domain: [["instance_id", "=", this.state.instanceId]],
            target: "current",
        });
    }

    async openBulkSync() {
        await this.action.doAction("ecommerce_integration_hub.action_ecommerce_integration_bulk_sync_wizard", {
            additionalContext: { default_instance_id: this.state.instanceId },
        });
    }
}

registry.category("actions").add("ecommerce_integration.dashboard", EcommerceIntegrationDashboard);
