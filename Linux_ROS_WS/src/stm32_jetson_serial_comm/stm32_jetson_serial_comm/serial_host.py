"""Host-side command helper built on the serial driver and binary protocol."""

from __future__ import annotations

import time
from collections import deque

from stm32_jetson_serial_comm.messages import (
    FRAME_ID_BOARD_IO_QUERY,
    FRAME_ID_BOARD_IO_RESPONSE,
    FRAME_ID_CS1237_CHANNEL_REQUEST,
    FRAME_ID_CS1237_CHANNEL_RESPONSE,
    FRAME_ID_CS1237_QUERY,
    FRAME_ID_CS1237_RESPONSE,
    FRAME_ID_FAN_CONTROL_REQUEST,
    FRAME_ID_FAN_CONTROL_RESPONSE,
    FRAME_ID_GPIO_CONTROL_REQUEST,
    FRAME_ID_GPIO_CONTROL_RESPONSE,
    FRAME_ID_GPIO_STATUS_QUERY,
    FRAME_ID_GPIO_STATUS_RESPONSE,
    FRAME_ID_RGB_QUERY,
    FRAME_ID_RGB_SET_REQUEST,
    FRAME_ID_RGB_SET_RESPONSE,
    FRAME_ID_RGB_STATUS,
    FRAME_ID_STATUS_QUERY,
    FRAME_ID_STATUS_RESPONSE,
    FRAME_ID_ULTRASONIC_QUERY,
    FRAME_ID_ULTRASONIC_RESPONSE,
    BoardIOStatus,
    GpioControlResult,
    GpioStatus,
    RgbSetResult,
    RgbStatus,
    SlaveStatus,
    UltrasonicStatus,
    CS1237ChannelResult,
    CS1237Status,
    FanControlResult,
    decode_board_io_status,
    decode_cs1237_channel_response,
    decode_cs1237_status,
    decode_fan_control_response,
    decode_gpio_control_response,
    decode_gpio_status,
    decode_rgb_set_response,
    decode_rgb_status,
    decode_slave_status,
    decode_ultrasonic_status,
)
from stm32_jetson_serial_comm.protocol import Frame, FrameParser, pack_frame


class SerialTimeoutError(TimeoutError):
    pass


class UnexpectedFrameError(RuntimeError):
    pass


class SerialHost:
    def __init__(self, driver):
        self._driver = driver
        self._parser = FrameParser()
        self._pending_frames = deque()

    def send_frame(self, command: int, payload: bytes = b"") -> int:
        return self._driver.write(pack_frame(command, payload))

    def read_frame(
        self,
        timeout_seconds: float = 0.5,
        poll_interval: float = 0.01,
        chunk_size: int = 256,
    ) -> Frame:
        if self._pending_frames:
            return self._pending_frames.popleft()

        deadline = time.monotonic() + timeout_seconds

        while time.monotonic() < deadline:
            chunk = self._driver.read(chunk_size)
            if chunk:
                frames = self._parser.feed(chunk)
                if frames:
                    self._pending_frames.extend(frames[1:])
                    return frames[0]
            else:
                time.sleep(poll_interval)

        raise SerialTimeoutError(f"no complete frame received within {timeout_seconds:.3f}s")

    def request(
        self,
        command: int,
        payload: bytes = b"",
        timeout_seconds: float = 0.5,
        poll_interval: float = 0.01,
    ) -> Frame:
        self.send_frame(command, payload)
        return self.read_frame(timeout_seconds=timeout_seconds, poll_interval=poll_interval)

    def _request_expected(
        self,
        request_frame_id: int,
        response_frame_id: int,
        seq: int,
        timeout_seconds: float,
        poll_interval: float,
        decoder,
        payload: bytes | None = None,
    ):
        self.send_frame(
            request_frame_id,
            bytes([seq & 0xFF]) if payload is None else payload,
        )
        deadline = time.monotonic() + timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SerialTimeoutError(
                    f"no matching frame received within {timeout_seconds:.3f}s"
                )
            response = self.read_frame(
                timeout_seconds=remaining,
                poll_interval=poll_interval,
            )
            if response.frame_id != response_frame_id:
                raise UnexpectedFrameError(
                    f"expected frame 0x{response_frame_id:02X}, got 0x{response.frame_id:02X}"
                )
            decoded = decoder(response.payload)
            if decoded.seq == (seq & 0xFF):
                return decoded

    def query_status(
        self,
        seq: int = 0,
        timeout_seconds: float = 0.5,
        poll_interval: float = 0.01,
    ) -> SlaveStatus:
        return self._request_expected(
            FRAME_ID_STATUS_QUERY,
            FRAME_ID_STATUS_RESPONSE,
            seq,
            timeout_seconds,
            poll_interval,
            decode_slave_status,
        )

    def query_gpio(
        self,
        seq: int = 0,
        timeout_seconds: float = 0.5,
        poll_interval: float = 0.01,
    ) -> GpioStatus:
        return self._request_expected(
            FRAME_ID_GPIO_STATUS_QUERY,
            FRAME_ID_GPIO_STATUS_RESPONSE,
            seq,
            timeout_seconds,
            poll_interval,
            decode_gpio_status,
        )

    def control_gpio(
        self,
        channel_id: int,
        level: int,
        seq: int = 0,
        timeout_seconds: float = 0.5,
        poll_interval: float = 0.01,
    ) -> GpioControlResult:
        payload = bytes([seq & 0xFF, channel_id & 0xFF, level & 0xFF])
        return self._request_expected(
            FRAME_ID_GPIO_CONTROL_REQUEST,
            FRAME_ID_GPIO_CONTROL_RESPONSE,
            seq,
            timeout_seconds,
            poll_interval,
            decode_gpio_control_response,
            payload,
        )

    def query_ultrasonic(
        self,
        seq: int = 0,
        timeout_seconds: float = 0.5,
        poll_interval: float = 0.01,
    ) -> UltrasonicStatus:
        return self._request_expected(
            FRAME_ID_ULTRASONIC_QUERY,
            FRAME_ID_ULTRASONIC_RESPONSE,
            seq,
            timeout_seconds,
            poll_interval,
            decode_ultrasonic_status,
        )

    def query_cs1237(
        self,
        seq: int = 0,
        timeout_seconds: float = 0.5,
        poll_interval: float = 0.01,
    ) -> CS1237Status:
        return self._request_expected(
            FRAME_ID_CS1237_QUERY,
            FRAME_ID_CS1237_RESPONSE,
            seq,
            timeout_seconds,
            poll_interval,
            decode_cs1237_status,
        )

    def set_cs1237_channel(
        self,
        channel: int,
        seq: int = 0,
        timeout_seconds: float = 1.0,
        poll_interval: float = 0.01,
    ) -> CS1237ChannelResult:
        return self._request_expected(
            FRAME_ID_CS1237_CHANNEL_REQUEST,
            FRAME_ID_CS1237_CHANNEL_RESPONSE,
            seq,
            timeout_seconds,
            poll_interval,
            decode_cs1237_channel_response,
            bytes([seq & 0xFF, channel & 0xFF]),
        )

    def set_fan_level(
        self,
        level: int,
        seq: int = 0,
        timeout_seconds: float = 0.5,
        poll_interval: float = 0.01,
    ) -> FanControlResult:
        return self._request_expected(
            FRAME_ID_FAN_CONTROL_REQUEST,
            FRAME_ID_FAN_CONTROL_RESPONSE,
            seq,
            timeout_seconds,
            poll_interval,
            decode_fan_control_response,
            bytes([seq & 0xFF, level & 0xFF]),
        )

    def set_rgb(
        self,
        red: int,
        green: int,
        blue: int,
        brightness: int,
        mode: int,
        seq: int = 0,
        timeout_seconds: float = 0.5,
        poll_interval: float = 0.01,
    ) -> RgbSetResult:
        values = ((seq, 0, 255), (red, 0, 255), (green, 0, 255), (blue, 0, 255),
                  (brightness, 0, 100), (mode, 0, 4))
        if any(not isinstance(value, int) or not lower <= value <= upper
               for value, lower, upper in values):
            raise ValueError("RGB command values are out of range")
        return self._request_expected(
            FRAME_ID_RGB_SET_REQUEST,
            FRAME_ID_RGB_SET_RESPONSE,
            seq,
            timeout_seconds,
            poll_interval,
            decode_rgb_set_response,
            bytes((seq, red, green, blue, brightness, mode)),
        )

    def query_rgb(
        self,
        seq: int = 0,
        timeout_seconds: float = 0.5,
        poll_interval: float = 0.01,
    ) -> RgbStatus:
        values = ((seq, 0, 255),)
        if any(not isinstance(value, int) or not lower <= value <= upper
               for value, lower, upper in values):
            raise ValueError("RGB query sequence is out of range")
        return self._request_expected(
            FRAME_ID_RGB_QUERY,
            FRAME_ID_RGB_STATUS,
            seq,
            timeout_seconds,
            poll_interval,
            decode_rgb_status,
        )

    def query_board_io(
        self,
        seq: int = 0,
        timeout_seconds: float = 0.5,
        poll_interval: float = 0.01,
    ) -> BoardIOStatus:
        return self._request_expected(
            FRAME_ID_BOARD_IO_QUERY,
            FRAME_ID_BOARD_IO_RESPONSE,
            seq,
            timeout_seconds,
            poll_interval,
            decode_board_io_status,
        )
