import { Component, onWillStart, proxy } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

const STATE_VARIANTS = {
    draft: "secondary",
    confirmed: "info",
    ongoing: "warning",
    done: "success",
    cancel: "danger",
};

export class AppointmentDashboard extends Component {
    static template = "om_hospital.AppointmentDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ period: "today", data: null, loading: true });
        onWillStart(() => this.load(this.state.period));
    }

    get periods() {
        return [
            { key: "today", label: _t("Today") },
            { key: "week", label: _t("This Week") },
            { key: "month", label: _t("This Month") },
        ];
    }

    get stateLabels() {
        return {
            draft: _t("Draft"),
            confirmed: _t("Confirmed"),
            ongoing: _t("Ongoing"),
            done: _t("Done"),
            cancel: _t("Cancelled"),
        };
    }

    get cards() {
        const { data } = this.state;
        if (!data) {
            return [];
        }
        const stateCards = Object.entries(data.counts).map(([key, value]) => ({
            key,
            label: this.stateLabels[key] || key,
            value,
            variant: STATE_VARIANTS[key] || "secondary",
            domain: [["state", "=", key]],
        }));
        return [
            { key: "total", label: _t("All"), value: data.total, variant: "primary", domain: [] },
            ...stateCards,
            {
                key: "urgent",
                label: _t("Urgent"),
                value: data.urgent,
                variant: "danger",
                domain: data.urgent_domain,
            },
        ];
    }

    async load(period) {
        this.state.loading = true;
        const data = await this.orm.call("hospital.appointment", "get_dashboard_data", [], {
            period,
        });
        // Ignore the answer of a period the user has already left.
        if (period === this.state.period) {
            this.state.data = data;
        }
        this.state.loading = false;
    }

    setPeriod(period) {
        this.state.period = period;
        return this.load(period);
    }

    percent(count, rows) {
        const max = Math.max(...rows.map((row) => row.count), 1);
        return Math.round((count / max) * 100);
    }

    openAppointments(title, extraDomain = []) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: title,
            res_model: "hospital.appointment",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: [...this.state.data.domain, ...extraDomain],
        });
    }
}

registry.category("actions").add("om_hospital.appointment_dashboard", AppointmentDashboard);
