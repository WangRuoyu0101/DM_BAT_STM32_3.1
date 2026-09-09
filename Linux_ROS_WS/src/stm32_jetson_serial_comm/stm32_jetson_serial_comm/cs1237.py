"""CS1237 physical-unit conversion and Jetson-side calibration storage."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path


DEFAULT_CALIBRATION_PATH = (
    Path.home() / ".config" / "stm32_jetson_serial_comm" / "cs1237_calibration.json"
)


@dataclass(frozen=True)
class CS1237Calibration:
    temperature_reference_c: float = 23.0
    temperature_reference_adc: int = 4100000
    force_zero_adc: int | None = None
    force_span_adc: int | None = None
    force_span_newtons: float | None = None


def temperature_celsius(raw_adc: int, calibration: CS1237Calibration | None = None) -> float:
    calibration = calibration or CS1237Calibration()
    if calibration.temperature_reference_adc == 0:
        raise ValueError("temperature reference ADC must not be zero")
    return (
        raw_adc
        * (273.15 + calibration.temperature_reference_c)
        / calibration.temperature_reference_adc
        - 273.15
    )


def force_newtons(raw_adc: int, calibration: CS1237Calibration) -> float:
    if (
        calibration.force_zero_adc is None
        or calibration.force_span_adc is None
        or calibration.force_span_newtons is None
        or calibration.force_span_adc == calibration.force_zero_adc
    ):
        raise ValueError("force calibration is incomplete or has zero span")
    return (
        (raw_adc - calibration.force_zero_adc)
        * calibration.force_span_newtons
        / (calibration.force_span_adc - calibration.force_zero_adc)
    )


def load_calibration(path: Path = DEFAULT_CALIBRATION_PATH) -> CS1237Calibration:
    path = Path(path)
    if not path.exists():
        return CS1237Calibration()
    return CS1237Calibration(**json.loads(path.read_text(encoding="utf-8")))


def save_calibration(
    calibration: CS1237Calibration,
    path: Path = DEFAULT_CALIBRATION_PATH,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(asdict(calibration), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
