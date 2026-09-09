"""Host-side STM32 bootloader updater."""

from __future__ import annotations

import binascii
import time
from dataclasses import dataclass
from typing import Callable, Iterable

from stm32_jetson_serial_comm.protocol import Frame, pack_frame
from stm32_jetson_serial_comm.serial_host import SerialHost, SerialTimeoutError, UnexpectedFrameError


APP_FRAME_ID_BOOTLOADER_REQUEST = 0x05
APP_FRAME_ID_BOOTLOADER_RESPONSE = 0x85
APP_FRAME_ID_ERROR_RESPONSE = 0xE1
APP_BOOTLOADER_PASSWORD = b"wb88"

BOOTLOADER_FRAME_ID_HELLO = 0x10
BOOTLOADER_FRAME_ID_START = 0x11
BOOTLOADER_FRAME_ID_ERASE = 0x12
BOOTLOADER_FRAME_ID_WRITE = 0x13
BOOTLOADER_FRAME_ID_VERIFY = 0x14
BOOTLOADER_FRAME_ID_JUMP = 0x15
BOOTLOADER_FRAME_ID_RESET = 0x16
BOOTLOADER_FRAME_ID_INFO = 0x90
BOOTLOADER_FRAME_ID_ACK = 0x91
BOOTLOADER_FRAME_ID_STATUS = 0x92
BOOTLOADER_FRAME_ID_ERROR = 0xE2

BOOTLOADER_STATUS_OK = 0x00
BOOTLOADER_WRITE_DATA_MAX = 245


class BootloaderProtocolError(RuntimeError):
    pass


@dataclass(frozen=True)
class BootloaderInfo:
    seq: int
    app_base: int
    app_size: int
    write_data_max: int
    version: int


@dataclass(frozen=True)
class BootloaderAck:
    seq: int
    command: int
    status: int


@dataclass(frozen=True)
class BootloaderError:
    seq: int
    command: int
    error_code: int


@dataclass(frozen=True)
class BootloaderStatus:
    state: int
    app_valid: bool
    last_error: int
    received_bytes: int


def crc32(data: bytes) -> int:
    """CRC32 matching the STM32 bootloader reflected CRC implementation."""
    return binascii.crc32(data) & 0xFFFFFFFF


def _le32(value: int) -> bytes:
    return int(value).to_bytes(4, byteorder="little", signed=False)


def build_start_payload(seq: int, image: bytes) -> bytes:
    return bytes([seq & 0xFF]) + _le32(len(image)) + _le32(crc32(image))


def build_write_payload(seq: int, offset: int, data: bytes) -> bytes:
    return bytes([seq & 0xFF]) + _le32(offset) + data


def split_write_chunks(
    image: bytes,
    chunk_size: int = BOOTLOADER_WRITE_DATA_MAX,
) -> Iterable[tuple[int, bytes]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    for offset in range(0, len(image), chunk_size):
        yield offset, image[offset : offset + chunk_size]


class BootloaderClient:
    def __init__(
        self,
        driver,
        status_callback: Callable[[BootloaderStatus], None] | None = None,
    ):
        self._host = SerialHost(driver)
        self._status_callback = status_callback

    @staticmethod
    def decode_info(payload: bytes) -> BootloaderInfo:
        if len(payload) != 17:
            raise BootloaderProtocolError(f"INFO payload length must be 17, got {len(payload)}")
        return BootloaderInfo(
            seq=payload[0],
            app_base=int.from_bytes(payload[1:5], byteorder="little"),
            app_size=int.from_bytes(payload[5:9], byteorder="little"),
            write_data_max=int.from_bytes(payload[9:13], byteorder="little"),
            version=int.from_bytes(payload[13:17], byteorder="little"),
        )

    @staticmethod
    def decode_ack(payload: bytes) -> BootloaderAck:
        if len(payload) != 3:
            raise BootloaderProtocolError(f"ACK payload length must be 3, got {len(payload)}")
        return BootloaderAck(seq=payload[0], command=payload[1], status=payload[2])

    @staticmethod
    def decode_error(payload: bytes) -> BootloaderError:
        if len(payload) != 3:
            raise BootloaderProtocolError(f"ERROR payload length must be 3, got {len(payload)}")
        return BootloaderError(seq=payload[0], command=payload[1], error_code=payload[2])

    @staticmethod
    def decode_status(payload: bytes) -> BootloaderStatus:
        if len(payload) != 8:
            raise BootloaderProtocolError(f"STATUS payload length must be 8, got {len(payload)}")
        if payload[0] > 3 or payload[1] > 1 or payload[3] != 0:
            raise BootloaderProtocolError(f"invalid STATUS payload: {payload.hex(' ')}")
        return BootloaderStatus(
            state=payload[0],
            app_valid=bool(payload[1]),
            last_error=payload[2],
            received_bytes=int.from_bytes(payload[4:8], byteorder="little"),
        )

    def _dispatch_status(self, frame: Frame) -> BootloaderStatus:
        status = self.decode_status(frame.payload)
        if self._status_callback is not None:
            self._status_callback(status)
        return status

    def request_app_bootloader(
        self,
        seq: int = 0,
        timeout_seconds: float = 0.5,
        poll_interval: float = 0.01,
        reset_wait_seconds: float = 0.0,
    ) -> None:
        response = self._host.request(
            APP_FRAME_ID_BOOTLOADER_REQUEST,
            bytes([seq & 0xFF]) + APP_BOOTLOADER_PASSWORD,
            timeout_seconds=timeout_seconds,
            poll_interval=poll_interval,
        )
        if response.frame_id == APP_FRAME_ID_ERROR_RESPONSE:
            raise BootloaderProtocolError(f"application rejected bootloader request: {response.payload.hex(' ')}")
        if response.frame_id == BOOTLOADER_FRAME_ID_ERROR:
            return
        if response.frame_id != APP_FRAME_ID_BOOTLOADER_RESPONSE:
            raise UnexpectedFrameError(
                f"expected frame 0x{APP_FRAME_ID_BOOTLOADER_RESPONSE:02X}, got 0x{response.frame_id:02X}"
            )
        if response.payload != bytes([seq & 0xFF, BOOTLOADER_STATUS_OK]):
            raise BootloaderProtocolError(f"unexpected bootloader response payload: {response.payload.hex(' ')}")
        if reset_wait_seconds > 0.0:
            time.sleep(reset_wait_seconds)

    def _send_and_read(
        self,
        frame_id: int,
        payload: bytes,
        timeout_seconds: float,
        poll_interval: float,
    ) -> Frame:
        self._host.send_frame(frame_id, payload)
        deadline = time.monotonic() + timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SerialTimeoutError(f"no bootloader response within {timeout_seconds:.3f}s")
            response = self._host.read_frame(
                timeout_seconds=remaining,
                poll_interval=poll_interval,
            )
            if response.frame_id == BOOTLOADER_FRAME_ID_STATUS:
                self._dispatch_status(response)
                continue
            if response.frame_id == BOOTLOADER_FRAME_ID_ERROR:
                error = self.decode_error(response.payload)
                raise BootloaderProtocolError(
                    f"bootloader error: seq=0x{error.seq:02X} "
                    f"command=0x{error.command:02X} error=0x{error.error_code:02X}"
                )
            return response

    def _request_info(
        self,
        seq: int,
        timeout_seconds: float,
        poll_interval: float,
    ) -> BootloaderInfo:
        deadline = time.monotonic() + timeout_seconds
        last_timeout: SerialTimeoutError | None = None
        response: Frame | None = None

        while time.monotonic() < deadline:
            try:
                response = self._send_and_read(
                    BOOTLOADER_FRAME_ID_HELLO,
                    bytes([seq & 0xFF]),
                    min(0.5, max(0.05, deadline - time.monotonic())),
                    poll_interval,
                )
                break
            except SerialTimeoutError as exc:
                last_timeout = exc

        if response is None:
            raise last_timeout or SerialTimeoutError(f"no bootloader HELLO response within {timeout_seconds:.3f}s")

        if response.frame_id != BOOTLOADER_FRAME_ID_INFO:
            raise UnexpectedFrameError(
                f"expected frame 0x{BOOTLOADER_FRAME_ID_INFO:02X}, got 0x{response.frame_id:02X}"
            )
        info = self.decode_info(response.payload)
        if info.seq != (seq & 0xFF):
            raise BootloaderProtocolError(f"INFO seq mismatch: expected 0x{seq & 0xFF:02X}, got 0x{info.seq:02X}")
        return info

    def hello(
        self,
        seq: int = 0,
        timeout_seconds: float = 1.0,
        poll_interval: float = 0.01,
    ) -> BootloaderInfo:
        return self._request_info(seq, timeout_seconds, poll_interval)

    def read_status(
        self,
        timeout_seconds: float = 0.1,
        poll_interval: float = 0.01,
    ) -> BootloaderStatus:
        response = self._host.read_frame(
            timeout_seconds=timeout_seconds,
            poll_interval=poll_interval,
        )
        if response.frame_id != BOOTLOADER_FRAME_ID_STATUS:
            raise UnexpectedFrameError(
                f"expected frame 0x{BOOTLOADER_FRAME_ID_STATUS:02X}, got 0x{response.frame_id:02X}"
            )
        return self._dispatch_status(response)

    def _request_ack(
        self,
        frame_id: int,
        seq: int,
        payload: bytes,
        timeout_seconds: float,
        poll_interval: float,
    ) -> BootloaderAck:
        response = self._send_and_read(frame_id, payload, timeout_seconds, poll_interval)
        if response.frame_id != BOOTLOADER_FRAME_ID_ACK:
            raise UnexpectedFrameError(
                f"expected frame 0x{BOOTLOADER_FRAME_ID_ACK:02X}, got 0x{response.frame_id:02X}"
            )
        ack = self.decode_ack(response.payload)
        if ack.seq != (seq & 0xFF) or ack.command != frame_id or ack.status != BOOTLOADER_STATUS_OK:
            raise BootloaderProtocolError(
                f"unexpected ACK: seq=0x{ack.seq:02X} command=0x{ack.command:02X} status=0x{ack.status:02X}"
            )
        return ack

    def program_image(
        self,
        image: bytes,
        seq_start: int = 0,
        jump: bool = True,
        reset: bool = False,
        timeout_seconds: float = 1.0,
        erase_timeout_seconds: float = 10.0,
        poll_interval: float = 0.01,
        progress: Callable[[str], None] | None = None,
    ) -> BootloaderInfo:
        if not image:
            raise ValueError("image must not be empty")
        if jump and reset:
            raise ValueError("jump and reset cannot both be true")

        def emit(message: str) -> None:
            if progress is not None:
                progress(message)

        seq = seq_start & 0xFF
        emit("HELLO")
        info = self._request_info(seq, timeout_seconds, poll_interval)
        if len(image) > info.app_size:
            raise ValueError(f"image size {len(image)} exceeds application area {info.app_size}")
        chunk_size = min(info.write_data_max, BOOTLOADER_WRITE_DATA_MAX)

        seq = (seq + 1) & 0xFF
        emit(f"START size={len(image)} crc32=0x{crc32(image):08X}")
        self._request_ack(
            BOOTLOADER_FRAME_ID_START,
            seq,
            build_start_payload(seq, image),
            timeout_seconds,
            poll_interval,
        )

        seq = (seq + 1) & 0xFF
        emit("ERASE")
        self._request_ack(
            BOOTLOADER_FRAME_ID_ERASE,
            seq,
            bytes([seq]),
            erase_timeout_seconds,
            poll_interval,
        )

        for offset, data in split_write_chunks(image, chunk_size):
            seq = (seq + 1) & 0xFF
            emit(f"WRITE offset={offset} size={len(data)}")
            self._request_ack(
                BOOTLOADER_FRAME_ID_WRITE,
                seq,
                build_write_payload(seq, offset, data),
                timeout_seconds,
                poll_interval,
            )

        seq = (seq + 1) & 0xFF
        emit("VERIFY")
        self._request_ack(
            BOOTLOADER_FRAME_ID_VERIFY,
            seq,
            bytes([seq]),
            timeout_seconds,
            poll_interval,
        )

        if jump:
            seq = (seq + 1) & 0xFF
            emit("JUMP")
            self._request_ack(
                BOOTLOADER_FRAME_ID_JUMP,
                seq,
                bytes([seq]),
                timeout_seconds,
                poll_interval,
            )
        elif reset:
            seq = (seq + 1) & 0xFF
            emit("RESET")
            self._request_ack(
                BOOTLOADER_FRAME_ID_RESET,
                seq,
                bytes([seq]),
                timeout_seconds,
                poll_interval,
            )

        return info


__all__ = [
    "APP_BOOTLOADER_PASSWORD",
    "BOOTLOADER_WRITE_DATA_MAX",
    "BootloaderAck",
    "BootloaderClient",
    "BootloaderError",
    "BootloaderInfo",
    "BootloaderProtocolError",
    "BootloaderStatus",
    "build_start_payload",
    "build_write_payload",
    "crc32",
    "pack_frame",
    "split_write_chunks",
]
