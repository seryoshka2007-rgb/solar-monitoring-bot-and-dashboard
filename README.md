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

# Русский

## Обзор

Solar Monitor собирает телеметрию инвертора SAKO SUNON V / совместимого с Voltronic, сохраняет измерения в InfluxDB и предоставляет данные через Telegram-бота и веб-панель.

Приложение предназначено для работы на Linux-сервере с использованием Docker Compose.

## Возможности

### Мониторинг в реальном времени

Система получает и отображает текущие показатели солнечных панелей, нагрузки, электросети, аккумулятора и инвертора. Исторические измерения сохраняются в InfluxDB для анализа энергопотребления.

### Telegram-бот

Бот предоставляет текущие показатели, отчёты за различные периоды, информацию о событиях инвертора и журнал ошибок.

| Команда | Описание |
| --- | --- |
| `/week` | Отчёт за текущую неделю |
| `/month` | Отчёт за текущий месяц |
| `/year` | Отчёт за текущий год |
| `/errors` | Показать журнал ошибок в памяти |

Клавиатура бота также позволяет просматривать текущее состояние системы, отчёты за день и более длительные периоды, выбирать произвольный диапазон дат, смотреть события инвертора и проверять уведомления.

Отчёты могут содержать генерацию энергии, потребление, импорт электроэнергии из сети, заряд и разряд аккумулятора, пиковую мощность и покрытие потребления — в зависимости от доступных данных.

Ежедневный отчёт за предыдущий день отправляется в 09:00 согласно настроенному часовому поясу.

### Веб-панель

Веб-панель отображает:

- Текущие показатели солнечных панелей, нагрузки, сети, аккумулятора и инвертора.
- Последние измерения мощности.
- Суточную генерацию энергии, потребление и импорт из сети.
- Месячную статистику энергопотребления.
- Расчётную экономию с учётом настроенных тарифов на электроэнергию.
- Режим работы инвертора и последние события.

Панель периодически обновляет данные и использует HTTP API приложения.

### Уведомления и события

Приложение может отправлять в Telegram уведомления о нештатных ситуациях, включая:

- Отсутствие или низкое напряжение электросети.
- Низкий и критически низкий заряд аккумулятора.
- Высокую температуру инвертора.
- Чрезмерную нагрузку.
- Отсутствие телеметрии.
- Изменение режима инвертора и сигналы предупреждений или неисправностей.

Пороговые значения и поведение уведомлений настраиваются через переменные окружения. События сохраняются в InfluxDB; последние события доступны через Telegram и API.

## HTTP API

Приложение предоставляет JSON API на порту `8090`
{ _ble_edit_exec_gexec__save_lastarg "$@"; } 4>&1 5>&2 &>/dev/null


API возвращает данные в формате JSON и доступен на порту `8090` внутри контейнера. В конфигурации Docker Compose порт на хосте привязан к localhost.

| Endpoint | Описание |
| --- | --- |
| `GET /api/health` | Проверка API |
| `GET /api/status` | Последние показания |
| `GET /api/events` | Состояние инвертора и события |
| `GET /api/current/today` | Отчёт за текущий день |
| `GET /api/current/week` | Отчёт за текущую неделю |
| `GET /api/current/month` | Отчёт за текущий месяц |
| `GET /api/current/year` | Отчёт за текущий год |
| `GET /api/report/yesterday` | Отчёт за вчера |
| `GET /api/report/previous-week` | Отчёт за прошлую неделю |
| `GET /api/report/previous-month` | Отчёт за прошлый месяц |
| `GET /api/report/previous-year` | Отчёт за прошлый год |

Проверка API на сервере:

    curl http://127.0.0.1:8090/api/health

## Установка и настройка

1. Установите Docker и Docker Compose на Linux-сервер.
2. Получите репозиторий проекта.
3. Настройте переменные окружения для приложения и сервисов.
4. Запустите сервисы через Docker Compose.
5. Проверьте состояние контейнеров, API и журналы приложения.

Точные переменные и команды запуска сверяйте с конфигурационными файлами проекта.

## Устранение неполадок

- **Нет данных:** проверьте подключение инвертора и поступление телеметрии.
- **Пустые отчёты:** проверьте записи и диапазоны времени в InfluxDB.
- **Нет уведомлений:** проверьте настройки Telegram и переменные окружения.
- **Ошибки InfluxDB:** изучите журнал приложения и сообщения о несовпадении типов полей.
