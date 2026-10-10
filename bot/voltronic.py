import os
import re
import threading
import time


DEVICE = "/dev/hidraw0"


def checksum(command: bytes) -> bytes:
    total = sum(command) & 0xFFFF
    return command + bytes([
        (total >> 8) & 0xFF,
        total & 0xFF,
    ]) + b"\r"


def read_response(fd, timeout=2.0):
    """
    Читает HID-пакеты до завершающего \\r.
    Устройство отдаёт данные кусками по 8 байт.
    """
    data = bytearray()
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            chunk = os.read(fd, 8)

            if chunk:
                data.extend(chunk)

                if b"\r" in data:
                    return bytes(data)

        except BlockingIOError:
            time.sleep(0.01)

    return bytes(data)


def _query_unlocked(command: bytes) -> bytes:
    fd = os.open(DEVICE, os.O_RDWR | os.O_NONBLOCK)

    try:
        try:
            while os.read(fd, 8):
                pass
        except BlockingIOError:
            pass

        packet = checksum(command)

        os.write(fd, packet)

        return read_response(fd)

    finally:
        os.close(fd)


_lock = threading.Lock()


def query(command: bytes) -> bytes:
    with _lock:
        return _query_unlocked(command)


def parse_qpigs(data: bytes):
    """
    Разбор QPIGS Voltronic / Axpert.

    Для текущей прошивки:

      0  grid voltage              V
      1  grid frequency            Hz
      2  output voltage            V
      3  output frequency          Hz
      4  load apparent power       VA
      5  load active power         W
      6  load percentage           %
      7  DC bus voltage            V
      8  battery voltage           V
      9  battery charge current    A
      10 battery SOC               %
      11 inverter temperature      C
      12 PV current                A
      13 PV voltage                V
      14 battery SCC voltage       V
      15 battery discharge current A
      16 status flags
      17 reserved
      18 reserved
      19 PV power                 W
      20 PV daily energy          Wh
    """

    text = data.decode(
        "ascii",
        errors="ignore"
    ).strip()

    if not text.startswith("("):
        raise ValueError(
            f"Неожиданный ответ инвертора: {text!r}"
        )

    text = text[1:].strip()

    # Реальный CR
    if "\r" in text:
        text = text.split("\r", 1)[0]

    parts = text.split()

    if len(parts) < 21:
        raise ValueError(
            f"Недостаточно полей QPIGS: "
            f"{len(parts)}: {parts!r}"
        )

    return {
        "grid_voltage_v": float(parts[0]),
        "grid_frequency_hz": float(parts[1]),

        "output_voltage_v": float(parts[2]),
        "output_frequency_hz": float(parts[3]),

        "load_va": float(parts[4]),
        "load_power_w": float(parts[5]),
        "load_percent": float(parts[6]),

        "dc_bus_voltage_v": float(parts[7]),

        "battery_voltage_v": float(parts[8]),
        "battery_charge_current_a": float(parts[9]),
        "battery_soc_pct": float(parts[10]),

        "inverter_temp_c": float(parts[11]),

        "pv_current_a": float(parts[12]),
        "pv_voltage_v": float(parts[13]),

        "battery_scc_voltage_v": float(parts[14]),
        "battery_discharge_current_a": float(parts[15]),

        "qpigs_status": parts[16],

        "pv_power_w": float(parts[19]),
        "pv_daily_energy_wh": float(parts[20]),

        "qpigs_fields": parts,
    }

def get_qpigs():
    data = query(b"QPIGS")

    if not data:
        raise TimeoutError("Инвертор не ответил на QPIGS")

    return parse_qpigs(data)


# Позиции битов QPIWS по стандартному протоколу Axpert/Voltronic.
# Для вашей модели сверить при первом отключении сети: бит 5 должен стать 1.
WARNING_BITS = {
    1: ("Неисправность инвертора", "fault"),
    2: ("Перенапряжение шины DC", "fault"),
    3: ("Пониженное напряжение шины DC", "fault"),
    4: ("Сбой плавного пуска шины", "fault"),
    5: ("Сеть пропала", "info"),
    6: ("Короткое замыкание на выходе", "fault"),
    7: ("Выходное напряжение слишком низкое", "fault"),
    8: ("Выходное напряжение слишком высокое", "fault"),
    9: ("Перегрев", "warning"),
    10: ("Вентилятор заблокирован", "warning"),
    11: ("Высокое напряжение АКБ", "warning"),
    12: ("Низкий заряд АКБ", "warning"),
    14: ("АКБ разряжена до отключения", "warning"),
    16: ("Перегрузка", "warning"),
    17: ("Ошибка EEPROM", "fault"),
    18: ("Перегрузка по току инвертора", "fault"),
    19: ("Сбой плавного пуска инвертора", "fault"),
    20: ("Ошибка самотеста", "fault"),
    21: ("Перенапряжение DC на выходе", "fault"),
    22: ("АКБ не подключена", "fault"),
    23: ("Отказ датчика тока", "fault"),
    24: ("Короткое замыкание АКБ", "fault"),
    25: ("Ограничение мощности", "warning"),
    26: ("Высокое напряжение PV", "warning"),
    27: ("Перегрузка MPPT (авария)", "fault"),
    28: ("Перегрузка MPPT (предупреждение)", "warning"),
    29: ("АКБ слишком разряжена для заряда", "warning"),
}

MODES = {
    "P": "Включение",
    "S": "Ожидание",
    "L": "От сети",
    "B": "От АКБ / PV",
    "F": "Авария",
    "H": "Экономия",
}


def _query_retry(command, pattern, tries=3):
    last = b""
    for _ in range(tries):
        last = query(command)
        if re.match(pattern, last):
            return last
        time.sleep(0.3)
    return last


def get_qpiws():
    data = _query_retry(b"QPIWS", rb"\([01]{32,36}")

    m = re.match(rb"\(([01]{32,36})", data)
    if not m:
        raise ValueError(f"Неожиданный ответ QPIWS: {data!r}")

    bits = m.group(1).decode()
    active = []

    for i, ch in enumerate(bits):
        if ch == "1":
            name, severity = WARNING_BITS.get(
                i, (f"Неизвестный флаг #{i}", "warning")
            )
            active.append({"bit": i, "name": name, "severity": severity})

    return {"raw": bits, "active": active}


def get_qmod():
    data = _query_retry(b"QMOD", rb"\([A-Z]")

    m = re.match(rb"\(([A-Z])", data)
    if not m:
        raise ValueError(f"Неожиданный ответ QMOD: {data!r}")

    letter = m.group(1).decode()
    return {"mode": letter, "mode_text": MODES.get(letter, letter)}


if __name__ == "__main__":
    print(f"Подключение к {DEVICE}")

    values = get_qpigs()

    print()
    print(f"Сеть:        {values['grid_voltage_v']:.1f} V")
    print(f"Частота:     {values['grid_frequency_hz']:.1f} Hz")
    print(f"Выход:       {values['output_voltage_v']:.1f} V")
    print(f"Нагрузка:    {values['load_power_w']:.0f} W")
    print(f"Нагрузка VA: {values['load_va']:.0f} VA")
    print(f"АКБ:         {values['battery_voltage_v']:.2f} V")
    print(
        f"АКБ заряд:   "
        f"{values['battery_charge_current_a']:.2f} A"
    )
    print(
        f"АКБ разряд:  "
        f"{values['battery_discharge_current_a']:.2f} A"
    )
    print(f"Заряд АКБ:   {values['battery_soc_pct']:.0f} %")
    print(f"PV voltage:  {values['pv_voltage_v']:.1f} V")
    print(f"PV current:  {values['pv_current_a']:.2f} A")
    print(f"PV power:    {values['pv_power_w']:.1f} W")
