"""Business payload decoders for STM32 USB CDC responses."""

from __future__ import annotations

from dataclasses import dataclass


FRAME_ID_STATUS_QUERY = 0x01
FRAME_ID_GPIO_CONTROL_REQUEST = 0x02
FRAME_ID_GPIO_STATUS_QUERY = 0x03
FRAME_ID_ULTRASONIC_QUERY = 0x04
FRAME_ID_CS1237_QUERY = 0x06
FRAME_ID_CS1237_CHANNEL_REQUEST = 0x07
FRAME_ID_FAN_CONTROL_REQUEST = 0x0A
FRAME_ID_BOARD_IO_QUERY = 0x0B
FRAME_ID_RGB_SET_REQUEST = 0x0C
FRAME_ID_RGB_QUERY = 0x0D
FRAME_ID_STATUS_RESPONSE = 0x81
FRAME_ID_GPIO_CONTROL_RESPONSE = 0x82
FRAME_ID_GPIO_STATUS_RESPONSE = 0x83
FRAME_ID_ULTRASONIC_RESPONSE = 0x84
FRAME_ID_CS1237_RESPONSE = 0x86
FRAME_ID_CS1237_CHANNEL_RESPONSE = 0x87
FRAME_ID_FAN_CONTROL_RESPONSE = 0x8A
FRAME_ID_BOARD_IO_RESPONSE = 0x8B
FRAME_ID_RGB_SET_RESPONSE = 0x8C
FRAME_ID_RGB_STATUS = 0x8D
FRAME_ID_ERROR_RESPONSE = 0xE1


@dataclass(frozen=True)
class SlaveStatus:
    seq: int
    tick: int
    status: int
    gpio_bitmap: int
    usb_busy_retries: int = 0
    usb_queue_overflows: int = 0
    usb_tx_failures: int = 0
    extended: bool = False


@dataclass(frozen=True)
class GpioStatus:
    seq: int
    gpio_bitmap: int


@dataclass(frozen=True)
class GpioControlResult:
    seq: int
    channel_id: int
    result: int


@dataclass(frozen=True)
class UltrasonicStatus:
    seq: int
    front_mm: int
    left_mm: int
    right_mm: int
    valid_bitmap: int
    error_bitmap: int


@dataclass(frozen=True)
class ErrorResponse:
    seq: int
    source_frame_id: int
    error_code: int


@dataclass(frozen=True)
class CS1237Status:
    seq: int
    raw_adc: int
    channel: int
    valid: bool
    error: int


@dataclass(frozen=True)
class CS1237ChannelResult:
    seq: int
    channel: int
    result: int


@dataclass(frozen=True)
class FanControlResult:
    seq: int
    level: int
    result: int


@dataclass(frozen=True)
class BoardIOStatus:
    seq: int
    fan_level: int
    fan1_rpm: int
    fan2_rpm: int
    key_bitmap: int


@dataclass(frozen=True)
class RgbSetResult:
    seq: int
    result: int


@dataclass(frozen=True)
class RgbStatus:
    seq: int
    red: int
    green: int
    blue: int
    brightness: int
    mode: int
    output_on: bool


def _require_len(payload: bytes, expected: int, name: str) -> None:
    if len(payload) != expected:
        raise ValueError(f"{name} payload length must be {expected}, got {len(payload)}")


def decode_slave_status(payload: bytes) -> SlaveStatus:
    if len(payload) not in (7, 19, 29):
        raise ValueError(f"status payload length must be 7, 19 or 29, got {len(payload)}")
    return SlaveStatus(
        seq=payload[0],
        tick=int.from_bytes(payload[1:5], byteorder="little"),
        status=payload[5],
        gpio_bitmap=payload[6],
        usb_busy_retries=int.from_bytes(payload[7:11], "little"),
        usb_queue_overflows=int.from_bytes(payload[11:15], "little"),
        usb_tx_failures=int.from_bytes(payload[15:19], "little"),
        extended=len(payload) >= 19,
    )


def decode_gpio_status(payload: bytes) -> GpioStatus:
    _require_len(payload, 2, "gpio status")
    return GpioStatus(seq=payload[0], gpio_bitmap=payload[1])


def decode_gpio_control_response(payload: bytes) -> GpioControlResult:
    _require_len(payload, 3, "gpio control")
    return GpioControlResult(seq=payload[0], channel_id=payload[1], result=payload[2])


def decode_ultrasonic_status(payload: bytes) -> UltrasonicStatus:
    _require_len(payload, 9, "ultrasonic status")
    return UltrasonicStatus(
        seq=payload[0],
        front_mm=int.from_bytes(payload[1:3], byteorder="little"),
        left_mm=int.from_bytes(payload[3:5], byteorder="little"),
        right_mm=int.from_bytes(payload[5:7], byteorder="little"),
        valid_bitmap=payload[7],
        error_bitmap=payload[8],
    )


def decode_error_response(payload: bytes) -> ErrorResponse:
    _require_len(payload, 3, "error")
    return ErrorResponse(seq=payload[0], source_frame_id=payload[1], error_code=payload[2])


def decode_cs1237_status(payload: bytes) -> CS1237Status:
    _require_len(payload, 8, "CS1237 status")
    return CS1237Status(
        seq=payload[0],
        raw_adc=int.from_bytes(payload[1:5], byteorder="little", signed=True),
        channel=payload[5],
        valid=bool(payload[6]),
        error=payload[7],
    )


def decode_cs1237_channel_response(payload: bytes) -> CS1237ChannelResult:
    _require_len(payload, 3, "CS1237 channel")
    return CS1237ChannelResult(seq=payload[0], channel=payload[1], result=payload[2])


def decode_fan_control_response(payload: bytes) -> FanControlResult:
    _require_len(payload, 3, "fan control")
    return FanControlResult(seq=payload[0], level=payload[1], result=payload[2])


def decode_board_io_status(payload: bytes) -> BoardIOStatus:
    _require_len(payload, 7, "board IO status")
    return BoardIOStatus(
        seq=payload[0],
        fan_level=payload[1],
        fan1_rpm=int.from_bytes(payload[2:4], "little"),
        fan2_rpm=int.from_bytes(payload[4:6], "little"),
        key_bitmap=payload[6],
    )


def decode_rgb_set_response(payload: bytes) -> RgbSetResult:
    _require_len(payload, 2, "RGB set")
    if payload[1] > 2:
        raise ValueError(f"RGB set result must be 0..2, got {payload[1]}")
    return RgbSetResult(seq=payload[0], result=payload[1])


def decode_rgb_status(payload: bytes) -> RgbStatus:
    _require_len(payload, 7, "RGB status")
    if payload[4] > 100:
        raise ValueError(f"RGB brightness must be 0..100, got {payload[4]}")
    if payload[5] > 4:
        raise ValueError(f"RGB mode must be 0..4, got {payload[5]}")
    if payload[6] not in (0, 1):
        raise ValueError(f"RGB output state must be 0 or 1, got {payload[6]}")
    return RgbStatus(
        seq=payload[0],
        red=payload[1],
        green=payload[2],
        blue=payload[3],
        brightness=payload[4],
        mode=payload[5],
        output_on=bool(payload[6]),
    )
