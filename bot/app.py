import asyncio
from collections import deque
import os
import random
import re

from voltronic import get_qpigs

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from aiohttp import web

from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import (
    ErrorEvent,
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    ""
)

ALLOWED_CHAT_IDS = [
    chat_id.strip()
    for chat_id in os.getenv(
        "TELEGRAM_CHAT_ID",
        ""
    ).split(",")
    if chat_id.strip()
]

INFLUX_URL = os.getenv(
    "INFLUX_URL",
    "http://influxdb:8086"
)

INFLUX_TOKEN = os.getenv(
    "INFLUX_TOKEN",
    "change-me-token"
)

INFLUX_ORG = os.getenv(
    "INFLUX_ORG",
    "solar"
)

INFLUX_BUCKET = os.getenv(
    "INFLUX_BUCKET",
    "telemetry"
)

POLL_SECONDS = int(
    os.getenv(
        "POLL_SECONDS",
        "10"
    )
)

TIMEZONE_NAME = os.getenv(
    "TIMEZONE",
    "Europe/Chisinau"
)

LOCAL_TZ = ZoneInfo(
    TIMEZONE_NAME
)
DATA_VALID_FROM = datetime(
    2026,
    10,
    2,
    9,
    0,
    tzinfo=LOCAL_TZ
)

API_HOST = os.getenv(
    "API_HOST",
    "0.0.0.0"
)

API_PORT = int(
    os.getenv(
        "API_PORT",
        "8090"
    )
)

TARIFF_NORMAL = float(
    os.getenv(
        "TARIFF_NORMAL",
        "1.45"
    )
)

TARIFF_DISCOUNT = float(
    os.getenv(
        "TARIFF_DISCOUNT",
        "1.09"
    )
)

TARIFF_DISCOUNT_KWH = float(
    os.getenv(
        "TARIFF_DISCOUNT_KWH",
        "45"
    )
)

ALERTS_ENABLED = (
    os.getenv(
        "ALERTS_ENABLED",
        "true"
    ).lower()
    == "true"
)

ALERT_CHECK_SECONDS = int(
    os.getenv(
        "ALERT_CHECK_SECONDS",
        "30"
    )
)

ALERT_REPEAT_MINUTES = int(
    os.getenv(
        "ALERT_REPEAT_MINUTES",
        "30"
    )
)

BATTERY_LOW_SOC = float(
    os.getenv(
        "BATTERY_LOW_SOC",
        "25"
    )
)

BATTERY_CRITICAL_SOC = float(
    os.getenv(
        "BATTERY_CRITICAL_SOC",
        "15"
    )
)

GRID_LOW_VOLTAGE = float(
    os.getenv(
        "GRID_LOW_VOLTAGE",
        "180"
    )
)

INVERTER_HIGH_TEMP = float(
    os.getenv(
        "INVERTER_HIGH_TEMP",
        "75"
    )
)

INVERTER_CRITICAL_TEMP = float(
    os.getenv(
        "INVERTER_CRITICAL_TEMP",
        "85"
    )
)

MAX_LOAD_POWER = float(
    os.getenv(
        "MAX_LOAD_POWER",
        "4500"
    )
)



# ============================================================
# ERROR JOURNAL
# ============================================================

ERROR_JOURNAL_MAX = 100

error_journal = deque(
    maxlen=ERROR_JOURNAL_MAX
)


def record_error(
    source,
    exc,
    context=""
):
    now = datetime.now(
        LOCAL_TZ
    )

    error_journal.append(
        {
            "time": now,
            "source": str(source),
            "error": f"{type(exc).__name__}: {exc}",
            "context": str(context or ""),
        }
    )

    print(
        f"ERROR [{source}] "
        f"{type(exc).__name__}: {exc}"
        + (
            f" | {context}"
            if context
            else ""
        ),
        flush=True
    )


def error_count():
    return len(
        error_journal
    )


def errors_text():
    count = error_count()

    if count == 0:
        return (
            "✅ <b>Журнал ошибок</b>\n\n"
            "Ошибок не зарегистрировано."
        )

    lines = [
        "⚠️ <b>Журнал ошибок</b>",
        "",
        f"Всего: <b>{count}</b>",
        f"Храним максимум: {ERROR_JOURNAL_MAX}",
        "━━━━━━━━━━━━━━━━━━",
        "",
    ]

    for item in reversed(
        list(error_journal)
    ):
        lines.append(
            f"🔴 <b>{item['time']:%d.%m %H:%M:%S}</b>"
        )
        lines.append(
            f"<b>{item['source']}</b>"
        )
        lines.append(
            item["error"]
        )

        if item["context"]:
            lines.append(
                f"ℹ️ {item['context']}"
            )

        lines.append(
            "━━━━━━━━━━━━━━━━━━"
        )

    return "\n".join(
        lines
    )


def errors_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="🔄 Обновить"
                ),
                KeyboardButton(
                    text="⚠️ Ошибки"
                ),
            ],
            [
                KeyboardButton(
                    text="🗑 Очистить ошибки"
                ),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# ============================================================
# ROUTER
# ============================================================

router = Router()


# ============================================================
# TELEGRAM KEYBOARD
# ============================================================

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="☀️ Сейчас"),
            KeyboardButton(text="📅 Сегодня"),
            KeyboardButton(text="📊 Неделя"),
        ],
        [
            KeyboardButton(text="📈 Месяц"),
            KeyboardButton(text="📆 Год"),
            KeyboardButton(text="🗓 Период"),
        ],
        [
            KeyboardButton(text="🔄 Обновить"),
            KeyboardButton(text="⚠️ События"),
            KeyboardButton(text="🧪 Тест"),
        ],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


# ============================================================
# DATA MODEL
# ============================================================

@dataclass
class Telemetry:

    ts: datetime

    pv_power_w: float
    pv_voltage_v: float
    pv_current_a: float

    load_power_w: float
    load_va: float
    load_percent: float

    grid_voltage_v: float
    grid_frequency_hz: float

    output_voltage_v: float
    output_frequency_hz: float

    battery_voltage_v: float
    battery_charge_current_a: float
    battery_discharge_current_a: float
    battery_soc_pct: float

    dc_bus_voltage_v: float

    inverter_temp_c: float

# ============================================================
# VoltronicProvider
# ============================================================
class VoltronicProvider:

    async def read(self):

        values = await asyncio.to_thread(
            get_qpigs
        )

        now = datetime.now(
            timezone.utc
        )

        battery_voltage = float(
            values["battery_voltage_v"]
        )

        battery_charge_current = float(
            values["battery_charge_current_a"]
        )

        battery_discharge_current = float(
            values["battery_discharge_current_a"]
        )

        load_power = float(
            values["load_power_w"]
        )

        pv_power = float(
            values["pv_power_w"]
        )

        grid_voltage = float(
            values["grid_voltage_v"]
        )

        grid_frequency = float(
            values["grid_frequency_hz"]
        )

        return Telemetry(

            ts=now,

            pv_power_w=pv_power,

            pv_voltage_v=float(
                values["pv_voltage_v"]
            ),

            pv_current_a=float(
                values["pv_current_a"]
            ),

            load_power_w=load_power,

            load_va=float(
                values["load_va"]
            ),

            load_percent=float(
                values["load_percent"]
            ),

            grid_voltage_v=float(
                values["grid_voltage_v"]
            ),

            grid_frequency_hz=float(
                values["grid_frequency_hz"]
            ),

            output_voltage_v=float(
                values["output_voltage_v"]
            ),

            output_frequency_hz=float(
                values["output_frequency_hz"]
            ),

            battery_voltage_v=battery_voltage,

            battery_charge_current_a=battery_charge_current,

            battery_discharge_current_a=battery_discharge_current,

            battery_soc_pct=float(
                values["battery_soc_pct"]
            ),

            dc_bus_voltage_v=float(
                values["dc_bus_voltage_v"]
            ),

            inverter_temp_c=float(
                values["inverter_temp_c"]
            ),
        )
# ============================================================
# GLOBAL STATE
# ============================================================

last_telemetry = None

last_successful_sample = None

alert_states = {}

alert_last_notification = {}

# Время фактического начала каждого аварийного состояния.
# Не используется для повторных уведомлений.
alert_started_at = {}


# ============================================================
# ACCESS
# ============================================================

def allowed(
    message: Message
):

    if not ALLOWED_CHAT_IDS:
        return True

    return (
        str(message.chat.id)
        in ALLOWED_CHAT_IDS
    )

# ============================================================
# INFLUX
# ============================================================

def influx():

    return InfluxDBClient(
        url=INFLUX_URL,
        token=INFLUX_TOKEN,
        org=INFLUX_ORG,
    )


async def write_sample(
    t: Telemetry
):

    # Расчёт мощности, реально потребляемой из сети.
    # Положительный результат = импорт из сети.
    # Отрицательный результат = избыток PV/заряд АКБ,
    # поэтому для тарифа ограничиваем минимумом 0 W.
    grid_power_w = max(
        0.0,
        float(t.load_power_w)
        - float(t.pv_power_w)
        - (
            float(t.battery_discharge_current_a)
            * float(t.battery_voltage_v)
        )
        + (
            float(t.battery_charge_current_a)
            * float(t.battery_voltage_v)
        )
    )

    point = (

        Point("inverter")

        .time(t.ts)

        .field(
            "pv_power_w",
           float(t.pv_power_w)
        )

        .field(
            "load_power_w",
           float(t.load_power_w)
        )

        .field(
            "grid_power_w",
            float(grid_power_w)
        )

        .field(
            "grid_voltage_v",
            float(t.grid_voltage_v)
        )
            .field(
            "pv_voltage_v",
            float(t.pv_voltage_v)
        )

        .field(
            "pv_current_a",
            float(t.pv_current_a)
        )

        .field(
            "load_va",
            float(t.load_va)
        )

        .field(
            "load_percent",
            float(t.load_percent)
        )

        .field(
            "grid_frequency_hz",
            float(t.grid_frequency_hz)
        )

        .field(
            "output_voltage_v",
            float(t.output_voltage_v)
        )

        .field(
            "output_frequency_hz",
            float(t.output_frequency_hz)
        )

        .field(
            "battery_charge_current_a",
            float(t.battery_charge_current_a)
        )

        .field(
            "battery_discharge_current_a",
            float(t.battery_discharge_current_a)
        )

        .field(
            "dc_bus_voltage_v",
            float(t.dc_bus_voltage_v)
        )

        .field(
            "battery_voltage_v",
            float(t.battery_voltage_v)
        )

        .field(
            "battery_soc_pct",
            float(t.battery_soc_pct)
        )

        .field(
            "inverter_temp_c",
            float(t.inverter_temp_c)
        )
    )

    with influx() as client:

        client.write_api(
            write_options=SYNCHRONOUS
        ).write(

            bucket=INFLUX_BUCKET,

            org=INFLUX_ORG,

            record=point,
        )


# ============================================================
# ALERT EVENT STORAGE
# ============================================================

async def write_alert_event(
    event_name,
    state,
    message_text,
    value=None
):

    point = (
        Point("alert_event")
        .time(
            datetime.now(
                timezone.utc
            )
        )
        .tag(
            "event",
            event_name
        )
        .tag(
            "state",
            state
        )
        .field(
            "message",
            message_text
        )
    )

    if value is not None:

        point = point.field(
            "value",
            float(value)
        )

    try:

        with influx() as client:

            client.write_api(
                write_options=SYNCHRONOUS
            ).write(
                bucket=INFLUX_BUCKET,
                org=INFLUX_ORG,
                record=point,
            )

    except Exception as exc:

        record_error(
            "Influx alert event",
            exc
        )


# ============================================================
# TELEGRAM ALERT
# ============================================================

async def send_alert(
    bot,
    text
):

    if not ALLOWED_CHAT_IDS:
        return

    for chat_id in ALLOWED_CHAT_IDS:

        try:

            await bot.send_message(
                chat_id=int(
                    chat_id
                ),
                text=text,
            )

        except Exception as exc:

            print(
                "Telegram alert error:",
                repr(exc),
                flush=True
            )

# ============================================================
# ALERT STATE MACHINE
# ============================================================

def _grid_outage_seconds_sync(threshold):
    query = (
        'from(bucket: "' + INFLUX_BUCKET + '")\n'
        '  |> range(start: -3d)\n'
        '  |> filter(fn: (r) => r._measurement == "inverter" and r._field == "grid_voltage_v")\n'
        '  |> keep(columns: ["_time", "_value"])\n'
        '  |> sort(columns: ["_time"])\n'
    )
    with influx() as client:
        tables = client.query_api().query(query, org=INFLUX_ORG)

    pts = []
    for table in tables:
        for rec in table.records:
            pts.append((rec.get_time(), float(rec.get_value())))
    pts.sort(key=lambda x: x[0])

    i = len(pts) - 1
    while i >= 0 and pts[i][1] >= threshold:
        i -= 1
    if i < 0:
        return None

    end = pts[i + 1][0] if i + 1 < len(pts) else datetime.now(timezone.utc)

    while i >= 0 and pts[i][1] < threshold:
        i -= 1
    start = pts[i + 1][0]

    return (end - start).total_seconds()


def format_outage(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{max(seconds, 1)} с"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} мин"
    return f"{minutes // 60} ч {minutes % 60} мин"


async def process_alert(
    bot,
    name,
    condition,
    alert_text,
    recovery_text,
    value=None
):

    now = datetime.now(
        timezone.utc
    )

    previous = alert_states.get(
        name,
        False
    )

    if condition:

        if not previous:

            alert_states[name] = True

            # Фиксируем реальное время начала аварии.
            # Это значение не изменяется повторными уведомлениями.
            alert_started_at[name] = now

            # Отдельно запоминаем время последнего уведомления.
            alert_last_notification[name] = now

            await send_alert(
                bot,
                alert_text
            )

            await write_alert_event(
                name,
                "active",
                alert_text,
                value
            )

        else:

            last_notice = (
                alert_last_notification.get(
                    name
                )
            )

            if last_notice is None:

                last_notice = now

            elapsed = (
                now - last_notice
            ).total_seconds()

            if (
                elapsed
                >=
                ALERT_REPEAT_MINUTES
                * 60
            ):

                alert_last_notification[
                    name
                ] = now

                await send_alert(
                    bot,
                    alert_text
                    +
                    "\n\n"
                    "⚠️ Состояние всё ещё активно."
                )

    else:

        if previous:

            alert_states[name] = False

            # Берём именно время начала аварии,
            # а не время последнего уведомления.
            started = (
                alert_started_at.get(
                    name
                )
            )

            duration_text = ""

            if started:

                duration = (
                    now - started
                )

                total_seconds = int(
                    duration.total_seconds()
                )

                if total_seconds > 0:

                    hours = (
                        total_seconds
                        // 3600
                    )

                    minutes = (
                        total_seconds
                        % 3600
                    ) // 60

                    if hours > 0:

                        duration_text = (
                            f"\n⏱ Длительность: "
                            f"{hours} ч. "
                            f"{minutes} мин."
                        )

                    elif minutes > 0:

                        duration_text = (
                            f"\n⏱ Длительность: "
                            f"{minutes} мин."
                        )

                    else:

                        duration_text = (
                            "\n⏱ Длительность: "
                            "менее 1 мин."
                        )

            if name == "grid":
                try:
                    secs = await asyncio.to_thread(
                        _grid_outage_seconds_sync,
                        GRID_LOW_VOLTAGE
                    )
                    if secs is not None:
                        duration_text = (
                            "\n⏱ Без сети: "
                            + format_outage(secs)
                        )
                except Exception as exc:
                    print("Outage duration error:", repr(exc), flush=True)

            await send_alert(
                bot,
                recovery_text
                +
                duration_text
            )

            await write_alert_event(
                name,
                "recovered",
                recovery_text,
                value
            )

            # Авария завершена — очищаем её состояние времени.
            alert_started_at.pop(
                name,
                None
            )

            alert_last_notification.pop(
                name,
                None
            )


# ============================================================
# ALERT CHECK
# ============================================================

async def check_alerts(
    bot,
    t: Telemetry
):

    if not ALERTS_ENABLED:
        return

    # --------------------------------------------------------
    # GRID
    # --------------------------------------------------------

    grid_problem = (
        t.grid_voltage_v
        <
        GRID_LOW_VOLTAGE
    )

    await process_alert(

        bot,

        "grid",

        grid_problem,

        (
            "🔴 АВАРИЯ\n\n"
            "Сеть инвертора отсутствует "
            "или напряжение слишком низкое.\n\n"
            f"⚡ Напряжение: "
            f"{t.grid_voltage_v:.1f} V\n"
            f"⚠️ Порог: "
            f"{GRID_LOW_VOLTAGE:.0f} V"
        ),

        (
            "✅ Сеть восстановлена\n\n"
            f"⚡ Напряжение: "
            f"{t.grid_voltage_v:.1f} V"
        ),

        t.grid_voltage_v
    )

    # --------------------------------------------------------
    # BATTERY CRITICAL
    # --------------------------------------------------------

    critical_battery = (
        t.battery_soc_pct
        <=
        BATTERY_CRITICAL_SOC
    )

    await process_alert(

        bot,

        "battery_critical",

        critical_battery,

        (
            "🔴 КРИТИЧЕСКИЙ ЗАРЯД АКБ\n\n"
            f"🔋 SOC: "
            f"{t.battery_soc_pct:.1f}%\n"
            f"⚠️ Критический порог: "
            f"{BATTERY_CRITICAL_SOC:.0f}%"
        ),

        (
            "✅ Заряд АКБ восстановился\n\n"
            f"🔋 SOC: "
            f"{t.battery_soc_pct:.1f}%"
        ),

        t.battery_soc_pct
    )

    # --------------------------------------------------------
    # BATTERY LOW
    # --------------------------------------------------------

    low_battery = (
        t.battery_soc_pct
        <=
        BATTERY_LOW_SOC
        and
        t.battery_soc_pct
        >
        BATTERY_CRITICAL_SOC
    )

    await process_alert(

        bot,

        "battery_low",

        low_battery,

        (
            "⚠️ НИЗКИЙ ЗАРЯД АКБ\n\n"
            f"🔋 SOC: "
            f"{t.battery_soc_pct:.1f}%\n"
            f"⚠️ Порог: "
            f"{BATTERY_LOW_SOC:.0f}%"
        ),

        (
            "✅ Заряд АКБ выше "
            "предупредительного порога\n\n"
            f"🔋 SOC: "
            f"{t.battery_soc_pct:.1f}%"
        ),

        t.battery_soc_pct
    )

    # --------------------------------------------------------
    # TEMPERATURE
    # --------------------------------------------------------

    critical_temp = (
        t.inverter_temp_c
        >=
        INVERTER_CRITICAL_TEMP
    )

    await process_alert(

        bot,

        "temperature_critical",

        critical_temp,

        (
            "🔴 КРИТИЧЕСКАЯ ТЕМПЕРАТУРА\n\n"
            f"🌡 Температура: "
            f"{t.inverter_temp_c:.1f} °C\n"
            f"⚠️ Порог: "
            f"{INVERTER_CRITICAL_TEMP:.0f} °C"
        ),

        (
            "✅ Температура инвертора "
            "вернулась в норму\n\n"
            f"🌡 Температура: "
            f"{t.inverter_temp_c:.1f} °C"
        ),

        t.inverter_temp_c
    )

    high_temp = (
        t.inverter_temp_c
        >=
        INVERTER_HIGH_TEMP
        and
        t.inverter_temp_c
        <
        INVERTER_CRITICAL_TEMP
    )

    await process_alert(

        bot,

        "temperature_high",

        high_temp,

        (
            "⚠️ ВЫСОКАЯ ТЕМПЕРАТУРА\n\n"
            f"🌡 Температура: "
            f"{t.inverter_temp_c:.1f} °C\n"
            f"⚠️ Порог: "
            f"{INVERTER_HIGH_TEMP:.0f} °C"
        ),

        (
            "✅ Температура инвертора "
            "нормализовалась\n\n"
            f"🌡 Температура: "
            f"{t.inverter_temp_c:.1f} °C"
        ),

        t.inverter_temp_c
    )

    # --------------------------------------------------------
    # OVERLOAD
    # --------------------------------------------------------

    overload = (
        t.load_power_w
        >
        MAX_LOAD_POWER
    )

    await process_alert(

        bot,

        "overload",

        overload,

        (
            "🔴 ПЕРЕГРУЗКА\n\n"
            f"🏠 Нагрузка: "
            f"{t.load_power_w:.0f} W\n"
            f"⚠️ Максимум: "
            f"{MAX_LOAD_POWER:.0f} W"
        ),

        (
            "✅ Перегрузка снята\n\n"
            f"🏠 Нагрузка: "
            f"{t.load_power_w:.0f} W"
        ),

        t.load_power_w
    )


# ============================================================
# LATEST
# ============================================================

async def latest():

    query = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -30d)
  |> filter(fn: (r) =>
      r._measurement == "inverter"
  )
  |> last()
'''

    with influx() as client:

        tables = (
            client
            .query_api()
            .query(
                query,
                org=INFLUX_ORG
            )
        )

    result = {}

    for table in tables:

        for record in table.records:

            result[
                record.get_field()
            ] = record.get_value()

    return result


# ============================================================
# PERIODS
# ============================================================

def period_range(
    period
):

    now_local = datetime.now(
        LOCAL_TZ
    )

    if period == "day":

        start_local = now_local.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

    elif period == "week":

        start_local = (
            now_local
            -
            timedelta(
                days=now_local.weekday()
            )
        ).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

    elif period == "month":

        start_local = now_local.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

    elif period == "year":

        start_local = now_local.replace(
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

    else:

        start_local = (
            now_local
            -
            timedelta(
                days=1
            )
        )

    return (
        start_local.astimezone(
            timezone.utc
        ),
        now_local.astimezone(
            timezone.utc
        )
    )


def completed_period_range(
    period
):

    now_local = datetime.now(
        LOCAL_TZ
    )

    today = now_local.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    if period == "yesterday":

        end_local = today

        start_local = (
            today
            -
            timedelta(
                days=1
            )
        )

    elif period == "previous_week":

        monday = (
            today
            -
            timedelta(
                days=today.weekday()
            )
        )

        end_local = monday

        start_local = (
            monday
            -
            timedelta(
                days=7
            )
        )

    elif period == "previous_month":

        end_local = today.replace(
            day=1
        )

        previous_month_last_day = (
            end_local
            -
            timedelta(
                days=1
            )
        )

        start_local = (
            previous_month_last_day
            .replace(
                day=1
            )
        )

    elif period == "previous_year":

        end_local = today.replace(
            month=1,
            day=1
        )

        start_local = end_local.replace(
            year=end_local.year - 1
        )

    else:

        return period_range(
            "day"
        )

    return (
        start_local.astimezone(
            timezone.utc
        ),
        end_local.astimezone(
            timezone.utc
        )
    )


# ============================================================
# QUERY DATA
# ============================================================

async def get_period_data(
    start,
    end
):
    # Не учитываем данные до момента,
    # когда телеметрия стала достоверной.
    if start < DATA_VALID_FROM:
        start = DATA_VALID_FROM

    if end <= start:
        return {}

    query = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(
      start: time(v: "{start.isoformat()}"),
      stop: time(v: "{end.isoformat()}")
  )
  |> filter(fn: (r) =>
      r._measurement == "inverter"
  )
'''

    with influx() as client:

        tables = (
            client
            .query_api()
            .query(
                query,
                org=INFLUX_ORG
            )
        )

    data = {}

    for table in tables:

        for record in table.records:

            field = (
                record.get_field()
            )

            data.setdefault(
                field,
                []
            ).append(

                (
                    record.get_time(),
                    float(
                        record.get_value()
                    )
                )
            )

    return data


# ============================================================
# ENERGY
# ============================================================

def calculate_grid_cost(
    kwh
):
    kwh = max(
        0.0,
        float(kwh)
    )

    discount_kwh = min(
        kwh,
        TARIFF_DISCOUNT_KWH
    )

    normal_kwh = max(
        0.0,
        kwh - TARIFF_DISCOUNT_KWH
    )

    discount_cost = (
        discount_kwh
        * TARIFF_DISCOUNT
    )

    normal_cost = (
        normal_kwh
        * TARIFF_NORMAL
    )

    return (
        discount_cost
        + normal_cost
    )

def integrate(
    points
):

    if len(points) < 2:
        return 0.0

    points.sort(
        key=lambda x: x[0]
    )

    total_wh = 0.0

    for i in range(
        1,
        len(points)
    ):

        t1, p1 = points[
            i - 1
        ]

        t2, p2 = points[i]

        seconds = (
            t2 - t1
        ).total_seconds()

        if seconds <= 0:
            continue

        if seconds > 300:
            continue

        average_power = (
            p1 + p2
        ) / 2

        total_wh += (
            average_power
            * seconds
            / 3600
        )

    return (
        total_wh
        / 1000
    )


def max_power(
    points
):

    if not points:
        return 0.0

    return max(
        value
        for _, value in points
    )


def average_power(
    points
):

    if not points:
        return 0.0

    return (
        sum(
            value
            for _, value in points
        )
        /
        len(points)
    )


def battery_energy(
    points
):

    charge = 0.0
    discharge = 0.0

    if len(points) < 2:

        return (
            charge,
            discharge
        )

    points.sort(
        key=lambda x: x[0]
    )

    for i in range(
        1,
        len(points)
    ):

        t1, p1 = points[
            i - 1
        ]

        t2, p2 = points[i]

        seconds = (
            t2 - t1
        ).total_seconds()

        if (
            seconds <= 0
            or seconds > 300
        ):
            continue

        power = (
            p1 + p2
        ) / 2

        energy = (
            abs(power)
            * seconds
            / 3600
            / 1000
        )

        if power >= 0:

            charge += energy

        else:

            discharge += energy

    return (
        charge,
        discharge
    )


def data_quality(
    points,
    start,
    end
):

    if len(points) < 2:
        return 0.0

    points.sort(
        key=lambda x: x[0]
    )

    expected = (
        end - start
    ).total_seconds()

    if expected <= 0:
        return 0.0

    covered = 0.0

    for i in range(
        1,
        len(points)
    ):

        diff = (
            points[i][0]
            -
            points[i - 1][0]
        ).total_seconds()

        if (
            diff > 0
            and diff <= 30
        ):
            covered += diff

    return max(
        0.0,
        min(
            100.0,
            covered
            /
            expected
            * 100
        )
    )


# ============================================================
# REPORT DATA
# ============================================================

def build_grid_points(data):
    """Мощность из сети = нагрузка + заряд АКБ - PV, только когда сеть есть."""
    gv = dict(data.get("grid_voltage_v", []))
    ch = dict(data.get("battery_charge_current_a", []))
    bv = dict(data.get("battery_voltage_v", []))
    pv = dict(data.get("pv_power_w", []))

    points = []
    for t, load_w in data.get("load_power_w", []):
        if gv.get(t, 0.0) > 100:
            p = load_w + ch.get(t, 0.0) * bv.get(t, 0.0) - pv.get(t, 0.0)
            points.append((t, max(0.0, p)))
        else:
            points.append((t, 0.0))
    return points


def build_battery_points(data, field):
    """Мощность АКБ (Вт) = ток * напряжение."""
    bv = dict(data.get("battery_voltage_v", []))
    return [
        (t, max(0.0, a) * bv.get(t, 0.0))
        for t, a in data.get(field, [])
    ]


async def calculate_report(
    start,
    end
):

    data = await get_period_data(
        start,
        end
    )

    pv_points = data.get(
        "pv_power_w",
        []
    )

    load_points = data.get(
        "load_power_w",
        []
    )

    grid_points = build_grid_points(data)

    pv = integrate(
        pv_points
    )

    load = integrate(
        load_points
    )

    grid = integrate(
        grid_points
    )

    pv_max = max_power(
        pv_points
    )

    load_max = max_power(
        load_points
    )

    load_avg = average_power(
        load_points
    )

    samples = len(
        pv_points
    )

    quality = data_quality(
        pv_points,
        start,
        end
    )

    grid_kwh = max(0.0, grid)  # integrate уже возвращает kWh

    grid_cost_rub = calculate_grid_cost(grid_kwh)

    # во сколько обошлась бы вся нагрузка без солнца и АКБ
    full_grid_cost_rub = calculate_grid_cost(load)

    savings_rub = max(
        0.0,
        full_grid_cost_rub - grid_cost_rub
    )

    battery_charge_kwh = integrate(
        build_battery_points(data, "battery_charge_current_a")
    )
    battery_discharge_kwh = integrate(
        build_battery_points(data, "battery_discharge_current_a")
    )

    if load > 0:
        solar_coverage = (
            (load - grid_kwh - battery_discharge_kwh) / load * 100
        )
        solar_coverage = min(100.0, max(0.0, solar_coverage))
    else:
        solar_coverage = 0.0

    return {
        "solar_coverage_percent": round(solar_coverage, 1),
        "battery_charge_kwh": round(battery_charge_kwh, 2),
        "battery_discharge_kwh": round(battery_discharge_kwh, 2),
        "generation_kwh": round(
            pv,
            2
        ),
        "consumption_kwh": round(
            load,
            2
        ),
        "grid_kwh": round(
            grid_kwh,
            2
        ),
        "grid_cost_rub": round(
            grid_cost_rub,
            2
        ),
        "full_grid_cost_rub": round(
            full_grid_cost_rub,
            2
        ),
        "savings_rub": round(
            savings_rub,
            2
        ),
        "pv_max_kw": round(
            pv_max / 1000,
            2
        ),
        "load_max_kw": round(
            load_max / 1000,
            2
        ),
        "load_average_kw": round(
            load_avg / 1000,
            2
        ),
        "samples": samples,
        "data_quality_percent": round(
            quality,
            1
        ),
    }

# ============================================================
# REPORT TEXT
# ============================================================

def format_report(
    title,
    start,
    end,
    report
):

    start_local = start.astimezone(LOCAL_TZ)
    end_local = end.astimezone(LOCAL_TZ)

    if (end_local - start_local).days <= 1:
        date_text = start_local.strftime("%d.%m.%Y")
    else:
        date_text = (
            f"{start_local:%d.%m.%Y}"
            f" – "
            f"{(end_local - timedelta(seconds=1)):%d.%m.%Y}"
        )

    return (
        f"☀️ <b>{title}</b>\n"
        f"📅 {date_text}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"

        f"☀️ <b>Солнечная энергия</b>\n"
        f"• Генерация: <b>{report['generation_kwh']:.2f} kWh</b>\n"
        f"• Максимум PV: <b>{report['pv_max_kw']:.2f} kW</b>\n\n"

        f"🏠 <b>Потребление</b>\n"
        f"• Энергия: <b>{report['consumption_kwh']:.2f} kWh</b>\n"
        f"• Максимальная нагрузка: <b>{report['load_max_kw']:.2f} kW</b>\n"
        f"• Средняя нагрузка: <b>{report['load_average_kw']:.2f} kW</b>\n"
        f"• ☀️ PV покрыл: <b>{report['solar_coverage_percent']:.0f}%</b> потребления\n\n"

        f"🔋 <b>АКБ</b>\n"
        f"• Заряд: <b>{report['battery_charge_kwh']:.2f} kWh</b>\n"
        f"• Разряд: <b>{report['battery_discharge_kwh']:.2f} kWh</b>\n\n"

        f"🔌 <b>Сеть</b>\n"
        f"• Из сети: <b>{report['grid_kwh']:.2f} kWh</b>\n"
        f"• Стоимость: <b>{report['grid_cost_rub']:.2f} ₽</b>\n"
        f"• Без солнца и АКБ: <b>{report['full_grid_cost_rub']:.2f} ₽</b>\n"
        f"• Экономия: <b>{report['savings_rub']:.2f} ₽</b>\n\n"

        f"📊 <b>Данные</b>\n"
        f"• Измерений: {report['samples']}\n"
        f"• Качество: <b>{report['data_quality_percent']:.1f}%</b>"
    )


# ============================================================
# CURRENT REPORT
# ============================================================

async def make_report(
    period,
    title
):

    start, end = (
        period_range(
            period
        )
    )

    report = (
        await calculate_report(
            start,
            end
        )
    )

    return format_report(
        title,
        start,
        end,
        report
    )


# ============================================================
# PREVIOUS PERIOD REPORT
# ============================================================

async def make_completed_report(
    period
):

    start, end = (
        completed_period_range(
            period
        )
    )

    report = (
        await calculate_report(
            start,
            end
        )
    )

    if period == "yesterday":

        title = "Отчёт за вчера"

    elif period == "previous_week":

        title = "Отчёт за предыдущую неделю"

    elif period == "previous_month":

        title = "Отчёт за предыдущий месяц"

    elif period == "previous_year":

        title = "Отчёт за предыдущий год"

    else:

        title = "Отчёт"

    return format_report(
        title,
        start,
        end,
        report
    ), report


# ============================================================
# STATUS
# ============================================================

async def status_text():

    values = await latest()

    if not values:
        return "Нет данных."

    return (

        "☀️ ТЕКУЩЕЕ СОСТОЯНИЕ\n\n"

        "☀️ PV\n"
        f"• Мощность: "
        f"{values.get('pv_power_w', 0):.0f} W\n"
        f"• Напряжение: "
        f"{values.get('pv_voltage_v', 0):.1f} V\n"
        f"• Ток: "
        f"{values.get('pv_current_a', 0):.2f} A\n\n"

        "🏠 НАГРУЗКА\n"
        f"• Мощность: "
        f"{values.get('load_power_w', 0):.0f} W\n"
        f"• VA: "
        f"{values.get('load_va', 0):.0f} VA\n"
        f"• Нагрузка: "
        f"{values.get('load_percent', 0):.0f} %\n\n"

        "⚡ СЕТЬ\n"
        f"• Напряжение: "
        f"{values.get('grid_voltage_v', 0):.1f} V\n"
        f"• Частота: "
        f"{values.get('grid_frequency_hz', 0):.1f} Hz\n"
        "\n"

        "🔋 АКБ\n"
        f"• Напряжение: "
        f"{values.get('battery_voltage_v', 0):.2f} V\n"
        f"• Зарядный ток: "
        f"{values.get('battery_charge_current_a', 0):+.2f} A\n"
        f"• Ток разряда: "
        f"{values.get('battery_discharge_current_a', 0):.2f} A\n"
        f"• SOC: "
        f"{values.get('battery_soc_pct', 0):.0f} %\n\n"

        "🔌 ИНВЕРТОР\n"
        f"• Выход: "
        f"{values.get('output_voltage_v', 0):.1f} V\n"
        f"• Частота: "
        f"{values.get('output_frequency_hz', 0):.1f} Hz\n"
        f"• DC Bus: "
        f"{values.get('dc_bus_voltage_v', 0):.0f} V\n"
        f"• Температура: "
        f"{values.get('inverter_temp_c', 0):.1f} °C"
    )

# ============================================================
# TELEGRAM COMMANDS
# ============================================================

@router.message(
    Command("start")
)
async def start(
    message: Message
):
    print(
        f"TELEGRAM CHAT ID: {message.chat.id}",
        flush=True
    )

    if not allowed(message):
        return

    await message.answer(
        "☀️ Solar Monitor Sunon V\n\n"
        "Выберите действие:",
        reply_markup=main_keyboard
    )


@router.message(
    Command("status")
)
async def status(
    message: Message
):

    if not allowed(message):
        return

    await message.answer(
        await status_text(),
        reply_markup=main_keyboard
    )


@router.message(
    Command("day")
)
async def day(
    message: Message
):

    if not allowed(message):
        return

    await message.answer(
        await make_report(
            "day",
            "Сегодня"
        ),
        reply_markup=main_keyboard
    )


@router.message(
    Command("week")
)
async def week(
    message: Message
):

    if not allowed(message):
        return

    await message.answer(
        await make_report(
            "week",
            "Текущая неделя"
        ),
        reply_markup=main_keyboard
    )


@router.message(
    Command("month")
)
async def month(
    message: Message
):

    if not allowed(message):
        return

    await message.answer(
        await make_report(
            "month",
            "Текущий месяц"
        ),
        reply_markup=main_keyboard
    )


@router.message(
    Command("year")
)
async def year(
    message: Message
):

    if not allowed(message):
        return

    await message.answer(
        await make_report(
            "year",
            "Текущий год"
        ),
        reply_markup=main_keyboard
    )



# ============================================================
# GLOBAL TELEGRAM ERROR HANDLER
# ============================================================

@router.error()
async def global_error_handler(
    event: ErrorEvent
):

    exc = event.exception

    record_error(
        "Telegram handler",
        exc
    )

    return True


# ============================================================
# BUTTONS
# ============================================================

@router.message(
    lambda m:
        m.text == "☀️ Сейчас"
)
async def button_status(
    message: Message
):

    if not allowed(message):
        return

    await message.answer(
        await status_text(),
        reply_markup=main_keyboard
    )


@router.message(
    lambda m:
        m.text == "📅 Сегодня"
)
async def button_day(
    message: Message
):

    if not allowed(message):
        return

    await message.answer(
        await make_report(
            "day",
            "Сегодня"
        ),
        reply_markup=main_keyboard
    )


@router.message(
    lambda m:
        m.text == "📊 Неделя"
)
async def button_week(
    message: Message
):

    if not allowed(message):
        return

    await message.answer(
        await make_report(
            "week",
            "Текущая неделя"
        ),
        reply_markup=main_keyboard
    )


@router.message(
    lambda m:
        m.text == "📈 Месяц"
)
async def button_month(
    message: Message
):

    if not allowed(message):
        return

    await message.answer(
        await make_report(
            "month",
            "Текущий месяц"
        ),
        reply_markup=main_keyboard
    )


@router.message(
    lambda m:
        m.text == "📆 Год"
)
async def button_year(
    message: Message
):

    if not allowed(message):
        return

    await message.answer(
        await make_report(
            "year",
            "Текущий год"
        ),
        reply_markup=main_keyboard
    )

@router.message(
    lambda m:
        m.text == "🗓 Период"
)
async def button_period(
    message: Message
):

    if not allowed(message):
        return

    await message.answer(
        "🗓 ПРОИЗВОЛЬНЫЙ ПЕРИОД\n\n"
        "Введите дату начала и дату окончания:\n\n"
        "Например:\n"
        "25.09.2026 - 01.10.2026"
    )


@router.message(
    lambda m:
        m.text
        and re.match(
            r"^\s*\d{1,2}[.]\d{1,2}[.]\d{4}\s*-\s*\d{1,2}[.]\d{1,2}[.]\d{4}\s*$",
            m.text
        )
)
async def custom_period(
    message: Message
):

    if not allowed(message):
        return

    try:

        parts = re.split(
            r"\s*-\s*",
            message.text.strip()
        )

        start_local = datetime.strptime(
            parts[0],
            "%d.%m.%Y"
        ).replace(
            tzinfo=LOCAL_TZ
        )

        end_local = datetime.strptime(
            parts[1],
            "%d.%m.%Y"
        ).replace(
            tzinfo=LOCAL_TZ
        )

        if end_local < start_local:
            await message.answer(
                "❌ Дата окончания раньше даты начала."
            )
            return

        # Для диапазона по датам включаем весь день окончания.
        end_local = end_local + timedelta(days=1)

        start = start_local.astimezone(timezone.utc)
        end = end_local.astimezone(timezone.utc)

        report = await calculate_report(
            start,
            end
        )

        text = format_report(
            "Указанный период",
            start,
            end,
            report
        )

        await message.answer(
            text,
            reply_markup=main_keyboard
        )

    except Exception as e:

        print(
            f"CUSTOM PERIOD ERROR: {e}",
            flush=True
        )

        await message.answer(
            "❌ Не удалось обработать период.\n\n"
            "Используйте формат:\n"
            "25.09.2026 - 01.10.2026"
        )


@router.message(
    lambda m:
        m.text == "🔄 Обновить"
)
async def button_refresh(
    message: Message
):

    if not allowed(message):
        return

    await message.answer(
        await status_text(),
        reply_markup=main_keyboard
    )
@router.message(
    lambda m:
        m.text == "📅 Вчера"
)
async def button_yesterday(
    message: Message
):

    if not allowed(message):
        return

    text, report = await make_completed_report(
        "yesterday"
    )

    await message.answer(
        text,
        reply_markup=main_keyboard
    )


@router.message(
    lambda m:
        m.text == "📊 Прошлая неделя"
)
async def button_previous_week(
    message: Message
):

    if not allowed(message):
        return

    text, report = await make_completed_report(
        "previous_week"
    )

    await message.answer(
        text,
        reply_markup=main_keyboard
    )


@router.message(
    lambda m:
        m.text == "📈 Прошлый месяц"
)
async def button_previous_month(
    message: Message
):

    if not allowed(message):
        return

    text, report = await make_completed_report(
        "previous_month"
    )

    await message.answer(
        text,
        reply_markup=main_keyboard
    )


@router.message(
    lambda m:
        m.text == "📆 Прошлый год"
)
async def button_previous_year(
    message: Message
):

    if not allowed(message):
        return

    text, report = await make_completed_report(
        "previous_year"
    )

    await message.answer(
        text,
        reply_markup=main_keyboard
    )


@router.message(
    lambda m:
        m.text == "⚠️ События"
)
async def button_events(
    message: Message
):

    if not allowed(message):
        return

    import html as _html

    events = await asyncio.to_thread(_read_events_sync, 10)

    mode_text = events_state.get("mode_text") or "нет данных"
    active = events_state.get("active") or []

    lines = ["⚠️ <b>События</b>", f"Режим: <b>{_html.escape(mode_text)}</b>"]

    if active:
        lines.append("🔴 Активно: " + ", ".join(
            _html.escape(a["name"]) for a in active))
    else:
        lines.append("✅ Ошибок инвертора нет")

    lines.append("")

    if not events:
        lines.append("Событий пока нет")
    else:
        icons = {"fault": "🔴", "warning": "🟠"}
        for e in events:
            t = datetime.fromisoformat(e["time"]).astimezone(LOCAL_TZ)
            icon = icons.get(e["severity"], "ℹ️")
            lines.append(
                f"{icon} {t:%d.%m %H:%M} — {_html.escape(e['text'])}")

    await message.answer(
        "\n".join(lines),
        reply_markup=main_keyboard
    )


@router.message(
    lambda m:
        m.text == "🧪 Тест"
)
async def button_test(
    message: Message
):

    if not allowed(message):
        return

    await message.answer(
        "🧪 ТЕСТ АВАРИЙНЫХ ОПОВЕЩЕНИЙ\n\n"
        "Проверяем канал уведомлений.\n\n"
        "🔴 Тестовое аварийное сообщение\n"
        "⚡ Система оповещений работает.\n\n"
        "Это тест — реальные параметры инвертора "
        "не изменяются.",
        reply_markup=main_keyboard
    )



@router.message(
    lambda m:
        m.text == "⚠️ Ошибки"
)
async def button_errors(
    message: Message
):

    if not allowed(message):
        return

    await message.answer(
        errors_text(),
        reply_markup=main_keyboard
    )


@router.message(
    lambda m:
        m.text == "🗑 Очистить ошибки"
)
async def button_clear_errors(
    message: Message
):

    if not allowed(message):
        return

    error_journal.clear()

    await message.answer(
        "✅ <b>Журнал ошибок очищен.</b>",
        reply_markup=main_keyboard
    )


@router.message(
    Command("errors")
)
async def command_errors(
    message: Message
):

    if not allowed(message):
        return

    await message.answer(
        errors_text(),
        reply_markup=main_keyboard
    )


# ============================================================
# HTTP API
# ============================================================

async def api_health(
    request
):

    return web.json_response(
        {
            "status": "ok",
            "service": "solar-bot",
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
        }
    )


async def latest_sample_time():
    query = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -7d)
  |> filter(fn: (r) =>
      r._measurement == "inverter" and r._field == "pv_power_w"
  )
  |> last()
'''
    with influx() as client:
        tables = client.query_api().query(query, org=INFLUX_ORG)

    for table in tables:
        for record in table.records:
            return record.get_time()
    return None


async def api_events(request):
    events = await asyncio.to_thread(_read_events_sync, 10)
    return web.json_response({
        "mode": events_state.get("mode"),
        "mode_text": events_state.get("mode_text"),
        "active": events_state.get("active") or [],
        "events": events,
    })


async def api_status(
    request
):

    values = await latest()

    t = await latest_sample_time()
    if t is not None:
        values["ts"] = t.isoformat()
        values["age_s"] = round(
            (datetime.now(t.tzinfo) - t).total_seconds(), 1
        )
    else:
        values["ts"] = None
        values["age_s"] = None

    return web.json_response(
        values
    )



async def api_current_report(request):
    period = request.match_info.get("period", "today")
    now = datetime.now(LOCAL_TZ)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if period == "today":
        start = day
    elif period == "week":
        start = day - timedelta(days=day.weekday())
    elif period == "month":
        start = day.replace(day=1)
    elif period == "year":
        start = day.replace(month=1, day=1)
    else:
        return web.json_response({"error": "unknown period"}, status=404)

    report = await calculate_report(start, now)
    return web.json_response({"period": period, "report": report})


async def api_yesterday(
    request
):

    text, report = (
        await make_completed_report(
            "yesterday"
        )
    )

    return web.json_response(
        {
            "period": "yesterday",
            "report": report,
            "report_text": text,
        }
    )


async def api_previous_week(
    request
):

    text, report = (
        await make_completed_report(
            "previous_week"
        )
    )

    return web.json_response(
        {
            "period": "previous_week",
            "report": report,
            "report_text": text,
        }
    )


async def api_previous_month(
    request
):

    text, report = (
        await make_completed_report(
            "previous_month"
        )
    )

    return web.json_response(
        {
            "period": "previous_month",
            "report": report,
            "report_text": text,
        }
    )


async def api_previous_year(
    request
):

    text, report = (
        await make_completed_report(
            "previous_year"
        )
    )

    return web.json_response(
        {
            "period": "previous_year",
            "report": report,
            "report_text": text,
        }
    )


def create_web_app():

    app = web.Application()

    app.router.add_get(
        "/api/health",
        api_health
    )

    app.router.add_get(
        "/api/status",
        api_status
    )

    app.router.add_get(
        "/api/events",
        api_events
    )

    app.router.add_get(
        "/api/current/{period}",
        api_current_report
    )

    app.router.add_get(
        "/api/report/yesterday",
        api_yesterday
    )

    app.router.add_get(
        "/api/report/previous-week",
        api_previous_week
    )

    app.router.add_get(
        "/api/report/previous-month",
        api_previous_month
    )

    app.router.add_get(
        "/api/report/previous-year",
        api_previous_year
    )

    return app


async def start_http_server():

    app = create_web_app()

    runner = web.AppRunner(
        app
    )

    await runner.setup()

    site = web.TCPSite(
        runner,
        API_HOST,
        API_PORT
    )

    await site.start()

    print(
        f"HTTP API started on "
        f"{API_HOST}:{API_PORT}",
        flush=True
    )

    return runner


# ============================================================
# COLLECTOR
# ============================================================

async def collector_loop(
    bot
):

    global last_telemetry
    global last_successful_sample

    provider = VoltronicProvider()

    while True:

        try:

            telemetry = (
                await provider.read()
            )

            await write_sample(
                telemetry
            )

            last_telemetry = (
                telemetry
            )

            last_successful_sample = (
                datetime.now(
                    timezone.utc
                )
            )

            await check_alerts(
                bot,
                telemetry
            )

        except Exception as exc:

            print(
                "Collector error:",
                repr(exc),
                flush=True
            )

        await asyncio.sleep(
            POLL_SECONDS
        )


# ============================================================
# DATA WATCHDOG
# ============================================================

EVENTS_POLL_SECONDS = 30

events_state = {
    "mode": None,
    "mode_text": None,
    "active": [],
    "updated": None,
}


def _write_event_sync(kind, severity, text):
    from influxdb_client import Point
    from influxdb_client.client.write_api import SYNCHRONOUS

    with influx() as client:
        client.write_api(write_options=SYNCHRONOUS).write(
            bucket=INFLUX_BUCKET,
            org=INFLUX_ORG,
            record=(
                Point("events")
                .tag("severity", severity)
                .tag("kind", kind)
                .field("text", text)
            ),
        )


def _read_events_sync(limit=10):
    query = (
        'from(bucket: "' + INFLUX_BUCKET + '")\n'
        '  |> range(start: -30d)\n'
        '  |> filter(fn: (r) => r._measurement == "events" and r._field == "text")\n'
        '  |> group()\n'
        '  |> sort(columns: ["_time"], desc: true)\n'
        '  |> limit(n: ' + str(int(limit)) + ')\n'
    )
    with influx() as client:
        tables = client.query_api().query(query, org=INFLUX_ORG)

    result = []
    for table in tables:
        for rec in table.records:
            result.append({
                "time": rec.get_time().isoformat(),
                "severity": rec.values.get("severity", "info"),
                "kind": rec.values.get("kind", ""),
                "text": rec.get_value(),
            })
    return result


async def record_event(bot, kind, severity, text, notify=False):
    print(f"Event [{severity}] {text}", flush=True)

    try:
        await asyncio.to_thread(_write_event_sync, kind, severity, text)
    except Exception as exc:
        print("Event write error:", repr(exc), flush=True)

    if not notify:
        return

    icon = {"fault": "🔴", "warning": "🟠"}.get(severity, "ℹ️")
    for chat_id in ALLOWED_CHAT_IDS:
        try:
            await bot.send_message(chat_id=int(chat_id), text=f"{icon} {text}")
        except Exception as exc:
            print(f"Event push failed for {chat_id}: {exc!r}", flush=True)


async def events_loop(bot):
    import voltronic as vt

    prev_mode = None
    prev_bits = None

    while True:
        try:
            q = await asyncio.to_thread(vt.get_qmod)
            w = await asyncio.to_thread(vt.get_qpiws)

            unknown = [
                item for item in w["active"]
                if item["name"].startswith("Неизвестный флаг #")
            ]
            if unknown:
                print(
                    "QPIWS diagnostic:",
                    f"raw={w['raw']}",
                    f"mode={q['mode']} ({q['mode_text']})",
                    f"unknown={unknown}",
                    flush=True,
                )

            mode = q["mode"]
            if prev_mode is not None and mode != prev_mode:
                if prev_mode == "L" and mode == "B":
                    await record_event(
                        bot, "mode", "warning",
                        "Сеть пропала, работа от АКБ / PV", notify=False)
                elif prev_mode == "B" and mode == "L":
                    await record_event(
                        bot, "mode", "info",
                        "Сеть вернулась, работа от сети", notify=False)
                else:
                    old = vt.MODES.get(prev_mode, prev_mode)
                    new = vt.MODES.get(mode, mode)
                    await record_event(
                        bot, "mode",
                        "fault" if mode == "F" else "info",
                        f"Режим: {old} → {new}",
                        notify=(mode == "F"))
            prev_mode = mode

            bits = {a["bit"]: a for a in w["active"] if a["bit"] != 5}
            if prev_bits is not None:
                for b, a in bits.items():
                    if b not in prev_bits:
                        await record_event(
                            bot, "flag", a["severity"],
                            "Инвертор: " + a["name"], notify=True)
                for b, a in prev_bits.items():
                    if b not in bits:
                        await record_event(
                            bot, "flag", "info",
                            "Снято: " + a["name"], notify=False)
            prev_bits = bits

            events_state.update({
                "mode": mode,
                "mode_text": q["mode_text"],
                "active": list(bits.values()),
                "updated": datetime.now(timezone.utc).isoformat(),
            })

        except Exception as exc:
            print("Events loop error:", repr(exc), flush=True)

        await asyncio.sleep(EVENTS_POLL_SECONDS)


async def data_watchdog(
    bot
):

    global last_successful_sample

    while True:

        await asyncio.sleep(
            ALERT_CHECK_SECONDS
        )

        if not ALERTS_ENABLED:
            continue

        if last_successful_sample is None:
            continue

        elapsed = (
            datetime.now(
                timezone.utc
            )
            -
            last_successful_sample
        ).total_seconds()

        no_data = (
            elapsed
            >
            max(
                90,
                POLL_SECONDS * 6
            )
        )

        await process_alert(

            bot,

            "data_missing",

            no_data,

            (
                "🔴 НЕТ ДАННЫХ\n\n"
                "Solar Bot не получает "
                "телеметрию от источника.\n\n"
                f"⏱ Последние данные: "
                f"{int(elapsed)} сек. назад"
            ),

            (
                "✅ Передача данных "
                "восстановлена"
            ),

            elapsed
        )

# ============================================================
# DAILY REPORT
# ============================================================

async def daily_report_loop(
    bot
):

    while True:

        now = datetime.now(
            LOCAL_TZ
        )

        # Следующая отправка в 09:00
        next_run = now.replace(
            hour=9,
            minute=0,
            second=0,
            microsecond=0
        )

        if next_run <= now:
            next_run += timedelta(
                days=1
            )

        wait_seconds = (
            next_run - now
        ).total_seconds()

        await asyncio.sleep(
            wait_seconds
        )

        try:

            print(
                "Daily report: generating yesterday report",
                flush=True
            )

            text, report = (
                await make_completed_report(
                    "yesterday"
                )
            )

            if not ALLOWED_CHAT_IDS:
                print(
                    "Daily report: ALLOWED_CHAT_IDS is empty",
                    flush=True
                )
                continue

            for chat_id in ALLOWED_CHAT_IDS:
                try:
                    await bot.send_message(
                        chat_id=int(chat_id),
                        text=text
                    )
                    print(f"Daily report: sent to {chat_id}", flush=True)
                except Exception as exc:
                    print(f"Daily report: send failed for {chat_id}: {exc!r}", flush=True)

        except Exception as exc:

            record_error(
                "Daily report",
                exc
            )

# ============================================================
# MAIN
# ============================================================

async def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN "
            "is not configured"
        )

    bot = Bot(
        BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML
        )
    )

    dispatcher = Dispatcher()

    dispatcher.include_router(
        router
    )

    http_runner = (
        await start_http_server()
    )

    collector_task = (
        asyncio.create_task(
            collector_loop(
                bot
            )
        )
    )

    watchdog_task = (
        asyncio.create_task(
            data_watchdog(
                bot
            )
        )
    )
    daily_report_task = (
        asyncio.create_task(
            daily_report_loop(
                bot
            )
        )
    )

    events_task = asyncio.create_task(
        events_loop(bot)
    )

    try:

        await dispatcher.start_polling(
            bot
        )

    finally:

        collector_task.cancel()

        watchdog_task.cancel()

        await http_runner.cleanup()


if __name__ == "__main__":

    asyncio.run(
        main()
    )
