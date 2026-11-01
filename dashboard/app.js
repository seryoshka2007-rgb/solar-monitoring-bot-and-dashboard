const API = "/api/status";

function setText(id, value, decimals = 0) {
    const el = document.getElementById(id);
    if (!el) return;

    if (value === undefined || value === null || Number.isNaN(Number(value))) {
        el.textContent = "—";
        return;
    }

    el.textContent = Number(value).toFixed(decimals);
}


function updateEnergyFlow(data) {
    setText("flow-pv-power", data.pv_power_w);
    setText("flow-pv-voltage", data.pv_voltage_v, 1);
    setText("flow-inverter-voltage", data.output_voltage_v, 1);
    setText("flow-inverter-temp", data.inverter_temp_c, 1);
    setText("flow-load-power", data.load_power_w);
    setText("flow-load-percent", data.load_percent);
    setText("flow-grid-power", data.grid_power_w);
    setText("flow-grid-voltage", data.grid_voltage_v, 1);
    setText("flow-battery-soc", data.battery_soc_pct);
    setText("flow-battery-voltage", data.battery_voltage_v, 2);

    const charge = Math.max(0, Number(data.battery_charge_current_a) || 0);
    const discharge = Math.max(0, Number(data.battery_discharge_current_a) || 0);
    const current = charge - discharge;
    document.getElementById("flow-battery-current").textContent =
        (current > 0 ? "+" : "") + current.toFixed(2);

    const pvActive = Number(data.pv_power_w) > 1;
    const loadActive = Number(data.load_power_w) > 1;
    const gridActive = Math.abs(Number(data.grid_power_w) || 0) > 1;
    const batteryActive = charge > 0.05 || discharge > 0.05;

    const states = [
        ["flow-pv-link", pvActive, pvActive ? "→" : "·"],
        ["flow-load-link", loadActive, loadActive ? "→" : "·"],
        ["flow-grid-link", gridActive, gridActive ? "↔" : "·"],
        ["flow-battery-link", batteryActive, charge > 0.05 ? "←" : discharge > 0.05 ? "→" : "·"]
    ];
    for (const [id, active, arrow] of states) {
        const el = document.getElementById(id);
        el.classList.toggle("active", active);
        el.querySelector("b").textContent = arrow;
    }
    document.getElementById("flow-battery-direction").textContent =
        charge > 0.05 ? "Заряд" : discharge > 0.05 ? "Разряд" : "Нет тока";
}

function setBar(id, value, max = 5000) {
    const el = document.getElementById(id);
    if (!el) return;

    const number = Number(value);
    if (!Number.isFinite(number) || number <= 0) {
        el.style.width = "0%";
        return;
    }

    el.style.width = Math.min((number / max) * 100, 100) + "%";
}

function setOnline(online) {
    const dot = document.getElementById("status-dot");
    const status = document.getElementById("system-status");

    if (online) {
        dot.style.background = "#35d399";
        dot.style.color = "#35d399";
        status.textContent = "Система онлайн";
    } else {
        dot.style.background = "#ef6262";
        dot.style.color = "#ef6262";
        status.textContent = "Нет связи";
    }
}

function setFreshness(age, ts) {
    const dot = document.getElementById("status-dot");
    const status = document.getElementById("system-status");
    const upd = document.getElementById("last-update");

    if (age === undefined || age === null || !Number.isFinite(Number(age))) {
        setOnline(false);
        upd.textContent = "Нет данных";
        return;
    }

    let color, text;
    if (age < 60) {
        color = "#35d399"; text = "Система онлайн";
    } else if (age < 300) {
        color = "#f6c453"; text = "Данные запаздывают";
    } else {
        color = "#ef6262"; text = "Нет данных от инвертора";
    }

    dot.style.background = color;
    dot.style.color = color;
    status.textContent = text;

    const when = ts ? new Date(ts).toLocaleTimeString() : "—";
    const ago = age < 120
        ? Math.round(age) + " с назад"
        : Math.round(age / 60) + " мин назад";
    upd.textContent = "Замер: " + when + " (" + ago + ")";
}

async function loadStatus() {
    try {
        const response = await fetch(API, { cache: "no-store" });
        if (!response.ok) throw new Error("HTTP " + response.status);

        const data = await response.json();

        setText("pv-power", data.pv_power_w);
        setText("pv-voltage", data.pv_voltage_v, 1);
        setText("pv-current", data.pv_current_a, 2);

        setText("load-power", data.load_power_w);
        setText("load-va", data.load_va);
        setText("load-percent", data.load_percent);

        setText("grid-power", data.grid_power_w);
        setText("grid-voltage", data.grid_voltage_v, 1);
        setText("grid-frequency", data.grid_frequency_hz, 1);

        setText("battery-soc", data.battery_soc_pct, 0);
        setText("battery-voltage", data.battery_voltage_v, 2);
        const batCur = (Number(data.battery_charge_current_a) || 0)
            - (Number(data.battery_discharge_current_a) || 0);
        document.getElementById("battery-current").textContent =
            (batCur > 0 ? "+" : "") + batCur.toFixed(2);

        setText("inverter-temp", data.inverter_temp_c, 1);
        setText("output-voltage", data.output_voltage_v, 1);
        setText("output-frequency", data.output_frequency_hz, 1);

        setText("pv-chart-value", data.pv_power_w);
        setText("load-chart-value", data.load_power_w);
        setText("grid-chart-value", data.grid_power_w);

        setBar("pv-bar", data.pv_power_w);
        setBar("load-bar", data.load_power_w);
        setBar("grid-bar", data.grid_power_w);

        setFreshness(data.age_s, data.ts);
        updateEnergyFlow(data);
    } catch (error) {
        console.error("Dashboard API:", error);
        setOnline(false);
    }
}

async function loadSummary(period) {
    try {
        const response = await fetch("/api/current/" + period, { cache: "no-store" });
        if (!response.ok) throw new Error("HTTP " + response.status);
        const r = (await response.json()).report;

        setText(period + "-generation", r.generation_kwh, 2);
        setText(period + "-consumption", r.consumption_kwh, 2);
        setText(period + "-grid", r.grid_kwh, 2);
        setText(period + "-savings", r.savings_rub, 2);
    } catch (error) {
        console.error("Summary API (" + period + "):", error);
    }
}

let summaryCycleRunning = false;

async function loadSummariesSequentially() {
    if (summaryCycleRunning) return;
    summaryCycleRunning = true;

    try {
        await loadSummary("today");
        await loadSummary("month");
    } finally {
        summaryCycleRunning = false;
        setTimeout(loadSummariesSequentially, 3600000);
    }
}

async function loadEvents() {
    try {
        const response = await fetch("/api/events", { cache: "no-store" });
        if (!response.ok) throw new Error("HTTP " + response.status);
        const d = await response.json();

        const badge = document.getElementById("mode-badge");
        const active = d.active || [];
        if (active.length) {
            badge.textContent = "⚠ " + active.map(a => a.name).join(", ");
            badge.className = "badge bad";
        } else {
            badge.textContent = d.mode_text || "";
            badge.className = "badge";
        }

        const list = document.getElementById("events-list");
        list.textContent = "";
        if (!d.events || !d.events.length) {
            list.textContent = "Событий пока нет";
            return;
        }
        for (const e of d.events) {
            const row = document.createElement("div");
            row.className = "event " + e.severity;
            const t = document.createElement("span");
            t.textContent = new Date(e.time).toLocaleString();
            const m = document.createElement("b");
            m.textContent = e.text;
            row.append(t, m);
            list.append(row);
        }
    } catch (error) {
        console.error("Events API:", error);
    }
}

loadStatus();
loadSummariesSequentially();
setInterval(loadStatus, 15000);
loadEvents();
setInterval(loadEvents, 15000);
