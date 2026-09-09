"""Binary-safe UM982 bridge over the STM32 application protocol."""

from __future__ import annotations


FRAME_ID_RTK_WRITE_REQUEST = 0x08
FRAME_ID_RTK_READ_REQUEST = 0x09
FRAME_ID_RTK_WRITE_RESPONSE = 0x88
FRAME_ID_RTK_READ_RESPONSE = 0x89
RTK_WRITE_CHUNK_SIZE = 249
RTK_FLAG_OVERFLOW = 0x01


class RtkOverflowError(RuntimeError):
    pass


class RtkBridge:
    def __init__(self, host, timeout_seconds: float = 0.5):
        self._host = host
        self._timeout_seconds = timeout_seconds
        self._next_seq = 0

    def _allocate_seq(self) -> int:
        seq = self._next_seq
        self._next_seq = (self._next_seq + 1) & 0xFF
        return seq

    def write(self, data: bytes) -> None:
        if not data:
            raise ValueError("RTK write data must not be empty")

        for offset in range(0, len(data), RTK_WRITE_CHUNK_SIZE):
            chunk = data[offset : offset + RTK_WRITE_CHUNK_SIZE]
            seq = self._allocate_seq()
            response = self._host.request(
                FRAME_ID_RTK_WRITE_REQUEST,
                bytes([seq]) + chunk,
                timeout_seconds=self._timeout_seconds,
            )
            if response.frame_id != FRAME_ID_RTK_WRITE_RESPONSE or len(response.payload) != 3:
                raise RuntimeError("malformed RTK write response")
            response_seq, result, accepted = response.payload
            if response_seq != seq or result != 0 or accepted != len(chunk):
                raise RuntimeError(
                    f"RTK write failed: seq={response_seq} result={result} accepted={accepted}"
                )

    def read(self) -> bytes:
        seq = self._allocate_seq()
        response = self._host.request(
            FRAME_ID_RTK_READ_REQUEST,
            bytes([seq]),
            timeout_seconds=self._timeout_seconds,
        )
        if (
            response.frame_id != FRAME_ID_RTK_READ_RESPONSE
            or len(response.payload) < 2
            or response.payload[0] != seq
        ):
            raise RuntimeError("malformed RTK read response")
        flags = response.payload[1]
        if flags & RTK_FLAG_OVERFLOW:
            raise RtkOverflowError("STM32 USART6 receive buffer overflowed")
        return response.payload[2:]
