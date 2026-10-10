# Solar Monitor — SAKO SUNON V

[English](#english) | [Русский](#русский)

A self-hosted solar inverter monitoring system with a Telegram bot, web dashboard, InfluxDB time-series storage, energy reports, event tracking, and alerts.

Система локального мониторинга солнечного инвертора с Telegram-ботом, веб-панелью, хранением телеметрии в InfluxDB, отчётами об энергопотреблении, журналом событий и аварийными уведомлениями.

---

# English

## Overview

Solar Monitor collects telemetry from a SAKO SUNON V / Voltronic-compatible inverter, stores measurements in InfluxDB, and makes the data available through Telegram and a web dashboard.

The application is designed to run on a Linux server using Docker Compose.

## Features

### Live monitoring

The system collects inverter telemetry, including:

- PV power, voltage, and current.
- Household load power, apparent power, and load percentage.
- Grid voltage, frequency, and calculated grid power.
- Battery voltage, state of charge (SOC), charging and discharging current.
- Inverter output voltage and frequency.
- Inverter temperature and DC bus voltage.

The polling interval is configurable with `POLL_SECONDS` (default: 10 seconds).

### Telegram bot

The bot provides a keyboard for quick access to monitoring and reports.

Available commands:

| Command | Description |
| --- | --- |
| `/start` | Open the bot menu |
| `/status` | Show current inverter status |
| `/day` | Report for today |
| `/week` | Report for the current week |
| `/month` | Report for the current month |
| `/year` | Report for the current year |
| `/errors` | Show the in-memory error journal |

The keyboard also provides access to current status, daily and longer-period reports, custom date ranges, inverter events, error history, and an alert test message.

Reports can include energy generation, consumption, grid import, battery charging and discharging, peak power, and consumption coverage, depending on the data available.

A daily report for the previous day is scheduled for 09:00 in the configured local time zone.

### Web dashboard

The dashboard displays:

- Current PV, load, grid, battery, and inverter values.
- Recent power measurements.
- Daily energy generation, consumption, and grid import.
- Monthly energy summaries.
- Estimated savings based on configured electricity tariffs.
- Inverter mode and recent events.

The dashboard refreshes its data periodically and uses the bot's HTTP API.

### Alerts and events

The application can notify Telegram chats about abnormal conditions, including:

- Missing or low grid voltage.
- Low and critically low battery charge.
- High inverter temperature.
- Excessive load.
- Missing telemetry.
- Inverter mode changes and reported warning/fault flags.

Alert thresholds and notification behavior can be configured through environment variables. Events are stored in InfluxDB; recent events are available through Telegram and the API.

### HTTP API

The bot exposes a JSON API on port `8090` inside the application container. In the supplied Compose configuration, the API is bound to localhost on the host.

| Endpoint | Description |
| --- | --- |
| `GET /api/health` | API health check |
| `GET /api/status` | Latest telemetry and sample age |
| `GET /api/events` | Current inverter state and recent events |
| `GET /api/current/today` | Current-day report |
| `GET /api/current/week` | Current-week report |
| `GET /api/current/month` | Current-month report |
| `GET /api/current/year` | Current-year report |
| `GET /api/report/yesterday` | Completed report for yesterday |
| `GET /api/report/previous-week` | Completed report for the previous week |
| `GET /api/report/previous-month` | Completed report for the previous month |
| `GET /api/report/previous-year` | Completed report for the previous year |

Example health check on the server:

```bash
curl http://127.0.0.1:8090/api/health
{ _ble_edit_exec_gexec__save_lastarg "$@"; } 4>&1 5>&2 &>/dev/null
