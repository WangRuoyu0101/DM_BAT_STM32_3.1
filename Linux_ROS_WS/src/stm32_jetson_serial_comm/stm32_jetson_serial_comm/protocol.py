"""STM32 USB CDC binary frame protocol used by the Jetson host."""

from __future__ import annotations

from dataclasses import dataclass


HEADER = b"\xAA\x55"
CRC8_POLY = 0x07
MAX_PAYLOAD_LEN = 250
FRAME_OVERHEAD = 5


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class Frame:
    frame_id: int
    payload: bytes = b""

    @property
    def command(self) -> int:
        """Backward-compatible alias for older callers."""
        return self.frame_id


def crc8(data: bytes) -> int:
    """CRC8 with initial value 0x00 and polynomial 0x07."""
    crc = 0
    for value in data:
        crc ^= value
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ CRC8_POLY) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def _validate_frame_id(frame_id: int) -> None:
    if not 0 <= frame_id <= 0xFF:
        raise ValueError(f"frame_id must fit in one byte: {frame_id!r}")


def _validate_payload(payload: bytes) -> None:
    if len(payload) > MAX_PAYLOAD_LEN:
        raise ValueError(f"payload too long: {len(payload)} > {MAX_PAYLOAD_LEN}")


def pack_frame(frame_id: int, payload: bytes = b"") -> bytes:
    _validate_frame_id(frame_id)
    _validate_payload(payload)

    body = bytes([frame_id, len(payload)]) + payload
    checksum = crc8(body)
    return HEADER + body + bytes([checksum])


class FrameParser:
    def __init__(self):
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[Frame]:
        self._buffer.extend(data)
        frames = []

        while True:
            header_index = self._buffer.find(HEADER)
            if header_index < 0:
                keep = self._buffer[-1:] if self._buffer.endswith(HEADER[:1]) else b""
                self._buffer.clear()
                self._buffer.extend(keep)
                break

            if header_index > 0:
                del self._buffer[:header_index]

            if len(self._buffer) < FRAME_OVERHEAD:
                break

            payload_len = self._buffer[3]
            if payload_len > MAX_PAYLOAD_LEN:
                del self._buffer[:2]
                continue

            frame_len = FRAME_OVERHEAD + payload_len
            if len(self._buffer) < frame_len:
                break

            raw_frame = bytes(self._buffer[:frame_len])
            del self._buffer[:frame_len]

            try:
                frames.append(self.unpack(raw_frame))
            except ProtocolError:
                continue

        return frames

    @staticmethod
    def unpack(raw_frame: bytes) -> Frame:
        if len(raw_frame) < FRAME_OVERHEAD:
            raise ProtocolError("frame is too short")
        if not raw_frame.startswith(HEADER):
            raise ProtocolError("frame header mismatch")

        frame_id = raw_frame[2]
        payload_len = raw_frame[3]
        if payload_len > MAX_PAYLOAD_LEN:
            raise ProtocolError(f"payload too long: {payload_len} > {MAX_PAYLOAD_LEN}")

        expected_len = FRAME_OVERHEAD + payload_len
        if len(raw_frame) != expected_len:
            raise ProtocolError(
                f"frame length mismatch: expected {expected_len}, got {len(raw_frame)}"
            )

        payload = raw_frame[4 : 4 + payload_len]
        expected_crc = raw_frame[-1]
        actual_crc = crc8(raw_frame[2:-1])
        if actual_crc != expected_crc:
            raise ProtocolError(
                f"crc mismatch: expected 0x{expected_crc:02X}, got 0x{actual_crc:02X}"
            )

        return Frame(frame_id=frame_id, payload=payload)
