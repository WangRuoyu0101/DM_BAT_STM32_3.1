"""Serial port driver wrapper kept independent from ROS."""

from __future__ import annotations

import time


class SerialDriver:
    def __init__(self, port):
        self._port = port

    @classmethod
    def open(cls, device: str, baudrate: int, timeout: float = 0.1) -> "SerialDriver":
        try:
            import serial
        except ModuleNotFoundError as exc:
            raise SystemExit(
                "未安装 pyserial。请在 Jetson 上运行：sudo apt-get install -y python3-serial"
            ) from exc

        try:
            port = serial.Serial(
                port=device,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=timeout,
            )
        except Exception as exc:
            raise SystemExit(
                f"串口设备不存在或无法打开：{device}\n"
                f"原始错误：{exc}\n"
                "请在 Jetson 上运行：ls -l /dev/ttyTHS* /dev/ttyUSB* /dev/ttyACM*\n"
                "如果设备存在但权限不足，请确认当前用户属于 dialout 组：id"
            ) from exc
        return cls(port)

    def write(self, data: bytes) -> int:
        written = self._port.write(data)
        self._port.flush()
        return written

    def read(self, size: int = 256) -> bytes:
        return self._port.read(size)

    def close(self) -> None:
        self._port.close()

    def __enter__(self) -> "SerialDriver":
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()


def read_for_seconds(port, seconds: float, chunk_size: int = 256, monotonic_step=None) -> bytes:
    """Read available bytes until the time window expires."""
    chunks = []

    if monotonic_step is None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            chunk = port.read(chunk_size)
            if chunk:
                chunks.append(chunk)
        return b"".join(chunks)

    elapsed = 0.0
    while elapsed < seconds:
        chunk = port.read(chunk_size)
        if chunk:
            chunks.append(chunk)
        elapsed += monotonic_step
    return b"".join(chunks)
