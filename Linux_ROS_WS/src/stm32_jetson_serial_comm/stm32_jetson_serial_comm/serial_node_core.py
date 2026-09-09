"""ROS-independent polling core for the STM32 serial node."""

from __future__ import annotations

from dataclasses import dataclass

from stm32_jetson_serial_comm.cs1237 import (
    force_newtons,
    load_calibration,
    temperature_celsius,
)

GPIO_CHANNEL_NAMES = (
    "flash_ctr",
    "led",
    "bee",
    "motor",
    "flash",
    "sound",
)

ULTRASONIC_SENSOR_NAMES = ("front", "left", "right")
ULTRASONIC_ERROR_LABELS = {
    0x00: "OK",
    0x01: "TIMEOUT",
    0x02: "INTERFERENCE",
    0x03: "NO_TARGET",
}


@dataclass(frozen=True)
class SerialPollResult:
    link_ok: bool
    status_text: str | None = None
    gpio_text: str | None = None
    gpio_bitmap: int | None = None
    ultrasonic_text: str | None = None
    ultrasonic_mm: list[int] | None = None
    cs1237_text: str | None = None
    cs1237_raw: int | None = None
    board_io_text: str | None = None
    fan_rpm: list[int] | None = None
    fan_level: int | None = None
    key_bitmap: int | None = None
    error_text: str | None = None


class SerialNodeCore:
    def __init__(
        self,
        host,
        timeout_seconds: float = 0.2,
        query_gpio: bool = True,
        query_ultrasonic: bool = True,
    ):
        self._host = host
        self._timeout_seconds = timeout_seconds
        self._query_gpio = query_gpio
        self._query_ultrasonic = query_ultrasonic
        self.next_seq = 0
        self.success_count = 0
        self.timeout_count = 0

    def _allocate_seq(self) -> int:
        seq = self.next_seq & 0xFF
        self.next_seq = (self.next_seq + 1) & 0xFF
        return seq

    @staticmethod
    def _format_status_text(status) -> str:
        status_label = "OK" if status.status == 0 else "ERROR"
        text = (
            f"STM32 status: seq=0x{status.seq:02X} tick={status.tick} "
            f"status={status_label}(0x{status.status:02X}) "
            f"app_gpio=0x{status.gpio_bitmap:02X}"
        )
        if status.extended:
            text += (
                f" usb_busy={status.usb_busy_retries}"
                f" usb_overflow={status.usb_queue_overflows}"
                f" usb_fail={status.usb_tx_failures}"
                f" rtk_overflow={status.rtk_overflow_bytes}"
                f" rtk_errors={status.rtk_uart_errors}"
                f" rtk_high_water={status.rtk_rx_high_water}"
            )
        return text

    @staticmethod
    def _format_gpio_text(gpio) -> str:
        states = []
        for index, name in enumerate(GPIO_CHANNEL_NAMES):
            level = "ON" if gpio.gpio_bitmap & (1 << index) else "OFF"
            states.append(f"{name}={level}")
        return (
            f"STM32 GPIO: seq=0x{gpio.seq:02X} bitmap=0x{gpio.gpio_bitmap:02X} "
            f"outputs=[{', '.join(states)}]"
        )

    @staticmethod
    def _ultrasonic_error(error_bitmap: int, index: int) -> int:
        return (error_bitmap >> (index * 2)) & 0x03

    @classmethod
    def _format_ultrasonic_sensor(cls, name: str, value: int, valid_bitmap: int, error_bitmap: int, index: int) -> str:
        error = cls._ultrasonic_error(error_bitmap, index)
        label = ULTRASONIC_ERROR_LABELS.get(error, "UNKNOWN")
        if ((valid_bitmap & (1 << index)) == 0) and error == 0x00:
            label = "INVALID"

        distance = value if label == "OK" else 0
        return f"{name}={distance}mm({label})"

    @classmethod
    def _format_ultrasonic_text(cls, ultrasonic) -> str:
        sensor_text = [
            cls._format_ultrasonic_sensor(
                name,
                value,
                ultrasonic.valid_bitmap,
                ultrasonic.error_bitmap,
                index,
            )
            for index, (name, value) in enumerate(
                (
                    (ULTRASONIC_SENSOR_NAMES[0], ultrasonic.front_mm),
                    (ULTRASONIC_SENSOR_NAMES[1], ultrasonic.left_mm),
                    (ULTRASONIC_SENSOR_NAMES[2], ultrasonic.right_mm),
                )
            )
        ]
        return (
            f"STM32 ultrasonic: seq=0x{ultrasonic.seq:02X} "
            f"{' '.join(sensor_text)}"
        )

    def _link_down(self, exc: Exception) -> SerialPollResult:
        self.timeout_count += 1
        return SerialPollResult(link_ok=False, error_text=str(exc))

    def poll_status(self) -> SerialPollResult:
        try:
            status = self._host.query_status(
                seq=self._allocate_seq(),
                timeout_seconds=self._timeout_seconds,
            )
        except Exception as exc:
            return self._link_down(exc)

        self.success_count += 1
        return SerialPollResult(
            link_ok=True,
            status_text=self._format_status_text(status),
        )

    def poll_gpio(self) -> SerialPollResult:
        if not self._query_gpio:
            return SerialPollResult(link_ok=True)

        try:
            gpio = self._host.query_gpio(
                seq=self._allocate_seq(),
                timeout_seconds=self._timeout_seconds,
            )
        except Exception as exc:
            return self._link_down(exc)

        self.success_count += 1
        return SerialPollResult(
            link_ok=True,
            gpio_text=self._format_gpio_text(gpio),
            gpio_bitmap=gpio.gpio_bitmap,
        )

    def poll_ultrasonic(self) -> SerialPollResult:
        if not self._query_ultrasonic:
            return SerialPollResult(link_ok=True)

        try:
            ultrasonic = self._host.query_ultrasonic(
                seq=self._allocate_seq(),
                timeout_seconds=self._timeout_seconds,
            )
        except Exception as exc:
            return self._link_down(exc)

        self.success_count += 1
        return SerialPollResult(
            link_ok=True,
            ultrasonic_text=self._format_ultrasonic_text(ultrasonic),
            ultrasonic_mm=[
                ultrasonic.front_mm,
                ultrasonic.left_mm,
                ultrasonic.right_mm,
                ultrasonic.valid_bitmap,
                ultrasonic.error_bitmap,
            ],
        )

    def poll_cs1237(self) -> SerialPollResult:
        try:
            status = self._host.query_cs1237(
                seq=self._allocate_seq(),
                timeout_seconds=self._timeout_seconds,
            )
        except Exception as exc:
            return self._link_down(exc)

        text = (
            f"CS1237 channel={status.channel} raw={status.raw_adc} "
            f"valid={'yes' if status.valid else 'no'} error={status.error}"
        )
        if status.valid:
            calibration = load_calibration()
            if status.channel == 2:
                text += f" temperature={temperature_celsius(status.raw_adc, calibration):.2f} C"
            elif status.channel == 0:
                try:
                    text += f" force={force_newtons(status.raw_adc, calibration):.3f} N"
                except ValueError:
                    text += " force=UNCALIBRATED"
        self.success_count += 1
        return SerialPollResult(link_ok=True, cs1237_text=text, cs1237_raw=status.raw_adc)

    def poll_board_io(self) -> SerialPollResult:
        try:
            status = self._host.query_board_io(
                seq=self._allocate_seq(),
                timeout_seconds=self._timeout_seconds,
            )
        except Exception as exc:
            return self._link_down(exc)

        self.success_count += 1
        return SerialPollResult(
            link_ok=True,
            board_io_text=(
                f"STM32 board IO: seq=0x{status.seq:02X} fan_level={status.fan_level} "
                f"fan1={status.fan1_rpm}rpm fan2={status.fan2_rpm}rpm "
                f"keys=0x{status.key_bitmap:02X}"
            ),
            fan_rpm=[status.fan1_rpm, status.fan2_rpm],
            fan_level=status.fan_level,
            key_bitmap=status.key_bitmap,
        )

    def poll_once(self) -> SerialPollResult:
        status_result = self.poll_status()
        if not status_result.link_ok:
            return status_result

        gpio_result = self.poll_gpio()
        if not gpio_result.link_ok:
            return gpio_result

        ultrasonic_result = self.poll_ultrasonic()
        if not ultrasonic_result.link_ok:
            return ultrasonic_result

        return SerialPollResult(
            link_ok=True,
            status_text=status_result.status_text,
            gpio_text=gpio_result.gpio_text,
            gpio_bitmap=gpio_result.gpio_bitmap,
            ultrasonic_text=ultrasonic_result.ultrasonic_text,
            ultrasonic_mm=ultrasonic_result.ultrasonic_mm,
        )
