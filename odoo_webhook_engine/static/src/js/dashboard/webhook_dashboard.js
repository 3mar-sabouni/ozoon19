/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class WebhookDashboard extends Component {
      static template = "odoo_webhook_engine.WebhookDashboard";

      setup() {
            this.action = useService("action");
            this.state = useState({
                  loading: true,
                  summary: {},
                  topEndpoints: [],
                  eventsPerModel: [],
                  eventsByType: [],
                  dailyStats: [],
            });

            onWillStart(async () => {
                  await this.loadData();
            });
      }

      async loadData() {
            this.state.loading = true;
            try {
                  const response = await fetch("/webhook/dashboard/data", {
                        method: "GET",
                        headers: { "Content-Type": "application/json" },
                  });
                  const data = await response.json();
                  this.state.summary = data.summary || {};
                  this.state.topEndpoints = data.top_endpoints || [];
                  this.state.eventsPerModel = data.events_per_model || [];
                  this.state.eventsByType = data.events_by_type || [];
                  this.state.dailyStats = data.daily_stats || [];
            } catch (e) {
                  console.error("Failed to load webhook dashboard data", e);
            }
            this.state.loading = false;
      }

      async onRefresh() {
            await this.loadData();
      }

      onOpenRules() {
            this.action.doAction("odoo_webhook_engine.webhook_rule_action");
      }

      onOpenLogs() {
            this.action.doAction("odoo_webhook_engine.webhook_log_action");
      }

      onOpenDLQ() {
            this.action.doAction("odoo_webhook_engine.webhook_retry_action");
      }

      onOpenIncoming() {
            this.action.doAction("odoo_webhook_engine.webhook_incoming_action");
      }

      formatNumber(n) {
            if (!n && n !== 0) return "—";
            return Number(n).toLocaleString();
      }

      formatMs(n) {
            if (!n && n !== 0) return "—";
            return `${Number(n).toFixed(1)} ms`;
      }

      formatPercent(n) {
            if (!n && n !== 0) return "—";
            return `${Number(n).toFixed(1)}%`;
      }

      getSuccessRate() {
            const s = this.state.summary;
            if (!s.total_sent) return "0%";
            return `${Number(s.success_rate).toFixed(1)}%`;
      }

      getSuccessRateColor() {
            const rate = this.state.summary.success_rate || 0;
            if (rate >= 95) return "text-success";
            if (rate >= 80) return "text-warning";
            return "text-danger";
      }

      getMaxCalls() {
            if (!this.state.dailyStats.length) return 1;
            return Math.max(...this.state.dailyStats.map((d) => d.calls || 0), 1);
      }

      getBarHeight(calls) {
            const max = this.getMaxCalls();
            return Math.max(((calls || 0) / max) * 100, 2);
      }

      getBarColor(day) {
            if (!day.calls) return "bg-secondary";
            const rate = day.calls > 0 ? (day.success / day.calls) * 100 : 0;
            if (rate >= 95) return "bg-success";
            if (rate >= 80) return "bg-warning";
            return "bg-danger";
      }

      getModelMax() {
            if (!this.state.eventsPerModel.length) return 1;
            return Math.max(...this.state.eventsPerModel.map((m) => m.count || 0), 1);
      }

      getModelBarWidth(count) {
            const max = this.getModelMax();
            return Math.max((count / max) * 100, 2);
      }
}

registry.category("actions").add("webhook_dashboard", WebhookDashboard);
