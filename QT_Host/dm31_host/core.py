"""Qt-independent helpers for ports, telemetry, bounded samples, and CSV."""

from __future__ import annotations

import csv
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class PortChoice:
    device: str
    description: str = ""
    hwid: str = ""
    vid: int | None = None
    pid: int | None = None
    serial_number: str | None = None

    def __str__(self) -> str:
        return f"{self.device} — {self.description}" if self.description else self.device


def list_serial_ports(source=None) -> list[PortChoice]:
    if source is None:
        from serial.tools import list_ports

        source = list_ports.comports
    return sorted(
        (
            PortChoice(
                device=item.device,
                description=item.description or "",
                hwid=item.hwid or "",
                vid=item.vid,
                pid=item.pid,
                serial_number=item.serial_number,
            )
            for item in source()
        ),
        key=lambda item: item.device,
    )


def find_matching_port(original: PortChoice, source=None) -> PortChoice | None:
    choices = list_serial_ports(source)
    if original.serial_number:
        matches = [item for item in choices if item.serial_number == original.serial_number]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return None
    if original.vid is not None and original.pid is not None:
        matches = [
            item for item in choices if (item.vid, item.pid) == (original.vid, original.pid)
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return None
    return next((item for item in choices if item.device == original.device), None)


def append_bounded(values: deque, value, limit: int = 600) -> None:
    if limit <= 0:
        raise ValueError("limit must be positive")
    values.append(value)
    while len(values) > limit:
        values.popleft()


@dataclass
class Telemetry:
    sample_seq: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now().astimezone())
    link_ok: bool = False
    gpio_bitmap: int | None = None
    fan_level: int | None = None
    fan1_rpm: int | None = None
    fan2_rpm: int | None = None
    key_bitmap: int | None = None
    ultrasonic_front_mm: int | None = None
    ultrasonic_left_mm: int | None = None
    ultrasonic_right_mm: int | None = None
    ultrasonic_valid_bitmap: int | None = None
    ultrasonic_error_bitmap: int | None = None
    cs1237_raw: int | None = None
    cs1237_channel: int | None = None
    cs1237_valid: bool | None = None
    cs1237_error: int | None = None
    rgb_red: int | None = None
    rgb_green: int | None = None
    rgb_blue: int | None = None
    rgb_brightness: int | None = None
    rgb_mode: int | None = None
    rgb_output_on: bool | None = None
    status_timestamp: datetime | None = None
    gpio_timestamp: datetime | None = None
    ultrasonic_timestamp: datetime | None = None
    cs1237_timestamp: datetime | None = None
    board_io_timestamp: datetime | None = None
    rgb_timestamp: datetime | None = None


class CsvRecorder:
    def __init__(self):
        self._stream = None
        self._writer = None

    @property
    def active(self) -> bool:
        return self._stream is not None

    def start(self, path: str | Path) -> None:
        self.stop()
        self._stream = Path(path).open("w", newline="", encoding="utf-8")
        fieldnames = list(asdict(Telemetry()).keys())
        self._writer = csv.DictWriter(self._stream, fieldnames=fieldnames)
        self._writer.writeheader()
        self._stream.flush()

    def write(self, telemetry: Telemetry) -> None:
        if self._writer is None:
            return
        row = asdict(telemetry)
        row["timestamp"] = telemetry.timestamp.astimezone().isoformat()
        for key in (
            "status_timestamp",
            "gpio_timestamp",
            "ultrasonic_timestamp",
            "cs1237_timestamp",
            "board_io_timestamp",
            "rgb_timestamp",
        ):
            value = row[key]
            row[key] = value.astimezone().isoformat() if value else ""
        self._writer.writerow(row)
        self._stream.flush()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.close()
        self._stream = None
        self._writer = None
