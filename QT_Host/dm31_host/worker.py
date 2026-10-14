"""Single-owner serial worker for the Qt debug host."""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime
import math
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from stm32_jetson_serial_comm.bootloader import BootloaderClient, BootloaderProtocolError
from stm32_jetson_serial_comm.serial_driver import SerialDriver
from stm32_jetson_serial_comm.serial_host import SerialHost, SerialTimeoutError, UnexpectedFrameError

from dm31_host.core import PortChoice, Telemetry, find_matching_port


class _LoggingDriver:
    def __init__(self, driver, logger, prefix="STM32"):
        self._driver = driver
        self._logger = logger
        self._prefix = prefix

    @staticmethod
    def _describe(direction: str, data: bytes) -> str:
        frame = f" frame=0x{data[2]:02X}" if len(data) >= 3 and data[:2] == b"\xAA\x55" else ""
        return f"{direction}{frame} {data.hex(' ').upper()}"

    def write(self, data: bytes) -> int:
        self._logger(f"[{self._prefix}] {self._describe('TX', data)}")
        return self._driver.write(data)

    def read(self, size: int = 256) -> bytes:
        data = self._driver.read(size)
        if data:
            self._logger(f"[{self._prefix}] {self._describe('RX', data)}")
        return data

    def close(self) -> None:
        self._driver.close()


class SerialWorker(QObject):
    state_changed = Signal(str, str)
    telemetry_changed = Signal(object)
    log_message = Signal(str)
    command_finished = Signal(str, bool, str)
    upgrade_progress = Signal(str, int)
    upgrade_finished = Signal(bool, str)
    bootloader_status_changed = Signal(object)

    def __init__(
        self,
        driver_factory=SerialDriver.open,
        host_factory=SerialHost,
        bootloader_factory=BootloaderClient,
        port_source=None,
        sleep=time.sleep,
        poll_intervals=None,
        serial_timeout=0.2,
        parent=None,
    ):
        super().__init__(parent)
        self._driver_factory = driver_factory
        self._host_factory = host_factory
        self._bootloader_factory = bootloader_factory
        self._port_source = port_source
        self._sleep = sleep
        self._driver = None
        self._host = None
        self._bootloader = None
        self._choice = None
        self._state = "DISCONNECTED"
        self._seq = 0
        self._telemetry = Telemetry()
        self._intervals = dict(poll_intervals or {
            "status": 2.0,
            "gpio": 1.0,
            "ultrasonic": 0.2,
            "cs1237": 0.1,
            "board_io": 0.5,
            "rgb": 0.5,
        })
        self._enabled = {name: True for name in self._intervals}
        self._serial_timeout = serial_timeout
        self._deadlines = {name: 0.0 for name in self._intervals}
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self.poll_once)

    def _open_driver(self, device: str, baudrate: int):
        driver = self._driver_factory(device, baudrate, 0.05)
        return _LoggingDriver(driver, self.log_message.emit)

    def _next_seq(self) -> int:
        seq = self._seq
        self._seq = (self._seq + 1) & 0xFF
        return seq

    def _set_state(self, state: str, detail: str = "") -> None:
        self._state = state
        self.state_changed.emit(state, detail)

    def _close_driver(self) -> None:
        if self._driver is not None:
            self._driver.close()
        self._driver = None
        self._host = None
        self._bootloader = None

    def _publish(self) -> None:
        self._telemetry.sample_seq += 1
        self._telemetry.timestamp = datetime.now().astimezone()
        self.telemetry_changed.emit(replace(self._telemetry))

    @Slot(object)
    def connect_port(self, choice: PortChoice) -> None:
        self.disconnect_port()
        try:
            self._driver = self._open_driver(choice.device, 115200)
            self._choice = choice
            bootloader = self._bootloader_factory(
                self._driver,
                status_callback=self.bootloader_status_changed.emit,
            )
            try:
                info = bootloader.hello(seq=self._next_seq(), timeout_seconds=0.25)
            except (BootloaderProtocolError, SerialTimeoutError, UnexpectedFrameError):
                pass
            else:
                self._bootloader = bootloader
                self._telemetry.link_ok = True
                self._set_state("BOOTLOADER", f"{choice.device} v{info.version >> 16}.{info.version & 0xFFFF}")
                self._timer.start()
                return
            self._host = self._host_factory(self._driver)
            self._telemetry.link_ok = True
            self._deadlines = {name: 0.0 for name in self._intervals}
            self._set_state("APPLICATION", choice.device)
            self._timer.start()
            self._publish()
        except (Exception, SystemExit) as exc:
            self._close_driver()
            self._set_state("DISCONNECTED", str(exc))
            self.log_message.emit(str(exc))

    @Slot()
    def disconnect_port(self) -> None:
        self._timer.stop()
        self._close_driver()
        self._telemetry.link_ok = False
        self._set_state("DISCONNECTED", "")

    def _poll_status(self) -> None:
        status = self._host.query_status(seq=self._next_seq(), timeout_seconds=self._serial_timeout)
        self._telemetry.link_ok = status.status == 0
        self._telemetry.status_timestamp = datetime.now().astimezone()

    def _poll_gpio(self) -> None:
        status = self._host.query_gpio(seq=self._next_seq(), timeout_seconds=self._serial_timeout)
        self._telemetry.gpio_bitmap = status.gpio_bitmap
        self._telemetry.gpio_timestamp = datetime.now().astimezone()

    def _poll_ultrasonic(self) -> None:
        status = self._host.query_ultrasonic(seq=self._next_seq(), timeout_seconds=self._serial_timeout)
        self._telemetry.ultrasonic_front_mm = status.front_mm
        self._telemetry.ultrasonic_left_mm = status.left_mm
        self._telemetry.ultrasonic_right_mm = status.right_mm
        self._telemetry.ultrasonic_valid_bitmap = status.valid_bitmap
        self._telemetry.ultrasonic_error_bitmap = status.error_bitmap
        self._telemetry.ultrasonic_timestamp = datetime.now().astimezone()

    def _poll_cs1237(self) -> None:
        status = self._host.query_cs1237(seq=self._next_seq(), timeout_seconds=self._serial_timeout)
        self._telemetry.cs1237_raw = status.raw_adc
        self._telemetry.cs1237_channel = status.channel
        self._telemetry.cs1237_valid = status.valid
        self._telemetry.cs1237_error = status.error
        self._telemetry.cs1237_timestamp = datetime.now().astimezone()

    def _poll_board_io(self) -> None:
        status = self._host.query_board_io(seq=self._next_seq(), timeout_seconds=self._serial_timeout)
        self._telemetry.fan_level = status.fan_level
        self._telemetry.fan1_rpm = status.fan1_rpm
        self._telemetry.fan2_rpm = status.fan2_rpm
        self._telemetry.key_bitmap = status.key_bitmap
        self._telemetry.board_io_timestamp = datetime.now().astimezone()

    def _poll_rgb(self) -> None:
        status = self._host.query_rgb(seq=self._next_seq(), timeout_seconds=self._serial_timeout)
        self._telemetry.rgb_red = status.red
        self._telemetry.rgb_green = status.green
        self._telemetry.rgb_blue = status.blue
        self._telemetry.rgb_brightness = status.brightness
        self._telemetry.rgb_mode = status.mode
        self._telemetry.rgb_output_on = status.output_on
        self._telemetry.rgb_timestamp = datetime.now().astimezone()

    @Slot()
    def poll_once(self) -> None:
        if self._state == "BOOTLOADER" and self._bootloader is not None:
            try:
                self._bootloader.read_status(timeout_seconds=0.01, poll_interval=0.001)
            except SerialTimeoutError:
                pass
            except (Exception, SystemExit) as exc:
                self.log_message.emit(f"bootloader: {exc}")
                self.disconnect_port()
            return
        if self._state != "APPLICATION" or self._host is None:
            return
        now = time.monotonic()
        enabled_names = (name for name in self._intervals if self._enabled[name])
        for name in sorted(enabled_names, key=self._deadlines.__getitem__):
            interval = self._intervals[name]
            if now < self._deadlines[name]:
                continue
            try:
                getattr(self, f"_poll_{name}")()
                self._deadlines[name] = now + interval
                self._publish()
            except UnexpectedFrameError as exc:
                if name == "rgb" and str(exc).endswith("got 0xE1"):
                    self._deadlines[name] = float("inf")
                    self.log_message.emit(
                        "rgb: 固件不支持 RGB 回读，已暂停本次连接的 RGB 轮询"
                    )
                else:
                    self.log_message.emit(f"{name}: {exc}")
                    self.disconnect_port()
            except (Exception, SystemExit) as exc:
                self.log_message.emit(f"{name}: {exc}")
                self.disconnect_port()
            return

    def _command(self, name: str, callback) -> None:
        if self._state != "APPLICATION" or self._host is None:
            self.command_finished.emit(name, False, "设备未连接")
            return
        try:
            result = callback()
            ok = result.result == 0
            self.command_finished.emit(name, ok, "OK" if ok else f"错误 0x{result.result:02X}")
        except (Exception, SystemExit) as exc:
            self.command_finished.emit(name, False, str(exc))

    @Slot(object, object, float)
    def configure_polling(self, rates_hz, enabled, serial_timeout: float) -> None:
        expected = set(self._intervals)
        try:
            legacy_rates = set(rates_hz) == expected - {"rgb"}
            if not legacy_rates and set(rates_hz) != expected:
                raise ValueError
            rates = {name: float(rates_hz[name]) for name in rates_hz}
        except (KeyError, TypeError, ValueError):
            self.command_finished.emit("轮询设置", False, "频率必须大于 0")
            return
        if any(not math.isfinite(rate) or rate <= 0 for rate in rates.values()):
            self.command_finished.emit("轮询设置", False, "频率必须大于 0")
            return
        legacy_enabled = set(enabled) == set(self._intervals) - {"rgb"}
        if (
            not legacy_enabled and set(enabled) != set(self._intervals)
        ) or any(type(value) is not bool for value in enabled.values()):
            self.command_finished.emit("轮询设置", False, "轮询开关配置无效")
            return
        if not 0.05 <= serial_timeout <= 5.0:
            self.command_finished.emit("轮询设置", False, "超时范围为 0.05–5 秒")
            return
        self._intervals = {
            name: self._intervals[name] if name == "rgb" and legacy_rates
            else 1.0 / rates[name]
            for name in self._intervals
        }
        self._enabled = {
            name: self._enabled[name] if name == "rgb" and legacy_enabled else enabled[name]
            for name in self._enabled
        }
        self._serial_timeout = float(serial_timeout)
        self._deadlines = {name: 0.0 for name in self._intervals}
        self.command_finished.emit("轮询设置", True, "OK")

    @Slot(int, int)
    def set_gpio(self, channel_id: int, level: int) -> None:
        self._command(
            f"GPIO {channel_id}",
            lambda: self._host.control_gpio(
                channel_id, level, seq=self._next_seq(), timeout_seconds=self._serial_timeout
            ),
        )

    @Slot(int)
    def set_fan(self, level: int) -> None:
        self._command(
            "风扇",
            lambda: self._host.set_fan_level(
                level, seq=self._next_seq(), timeout_seconds=self._serial_timeout
            ),
        )

    @Slot(int)
    def set_cs1237_channel(self, channel: int) -> None:
        self._command(
            "CS1237",
            lambda: self._host.set_cs1237_channel(
                channel, seq=self._next_seq(), timeout_seconds=self._serial_timeout
            ),
        )

    @Slot(int, int, int, int, int)
    def set_rgb(self, red: int, green: int, blue: int, brightness: int, mode: int) -> None:
        self._command(
            "RGB",
            lambda: self._host.set_rgb(
                red, green, blue, brightness, mode,
                seq=self._next_seq(), timeout_seconds=self._serial_timeout,
            ),
        )

    def _wait_for_port(self) -> PortChoice:
        for _ in range(50):
            match = find_matching_port(self._choice, self._port_source)
            if match is not None:
                return match
            self._sleep(0.1)
        raise RuntimeError("USB 设备重枚举超时，请重新选择串口")

    def _upgrade_log(self, message: str, image_size: int) -> None:
        progress = {"HELLO": 5, "START": 10, "ERASE": 15, "VERIFY": 90, "JUMP": 98}
        percent = next((value for key, value in progress.items() if message.startswith(key)), 20)
        if message.startswith("WRITE"):
            offset = int(message.split("offset=", 1)[1].split()[0])
            percent = 20 + int(65 * offset / max(1, image_size))
        self.log_message.emit(message)
        self.upgrade_progress.emit(message, percent)

    @staticmethod
    def _is_usb_disconnect(exc: BaseException) -> bool:
        """Recognize USB removal errors even when pyserial wraps the OSError.

        On macOS, pyserial commonly raises ``SerialException`` with a textual
        ``[Errno 6] Device not configured`` message but leaves ``errno`` unset.
        The STM32 deliberately disconnects USB after accepting JUMP, so that
        wrapped exception is expected while the application re-enumerates.
        """
        disconnect_errnos = {5, 6, 19}
        disconnect_markers = (
            "[errno 5]",
            "[errno 6]",
            "[errno 19]",
            "input/output error",
            "device not configured",
            "no such device",
        )
        pending: list[BaseException] = [exc]
        visited: set[int] = set()
        while pending:
            current = pending.pop()
            if id(current) in visited:
                continue
            visited.add(id(current))
            if getattr(current, "errno", None) in disconnect_errnos:
                return True
            message = str(current).lower()
            if any(marker in message for marker in disconnect_markers):
                return True
            for linked in (current.__cause__, current.__context__):
                if linked is not None:
                    pending.append(linked)
        return False

    @Slot(str, bool)
    def upgrade(self, image_path: str, request_from_app: bool = True) -> None:
        if self._choice is None:
            self.upgrade_finished.emit(False, "未选择设备")
            return
        try:
            image = Path(image_path).read_bytes()
            if not image:
                raise ValueError("固件文件为空")
            self._timer.stop()
            self._set_state("UPGRADING", image_path)
            if request_from_app:
                if self._driver is None:
                    raise RuntimeError("应用未连接")
                self._bootloader_factory(self._driver).request_app_bootloader(
                    seq=self._next_seq(), timeout_seconds=0.5
                )
            self._close_driver()
            self._sleep(1.5)
            boot_port = self._wait_for_port()
            self._driver = self._open_driver(boot_port.device, 460800)
            self._bootloader = self._bootloader_factory(
                self._driver,
                status_callback=self.bootloader_status_changed.emit,
            )
            jump_started = False

            def report_progress(message: str) -> None:
                nonlocal jump_started
                jump_started = jump_started or message.startswith("JUMP")
                self._upgrade_log(message, len(image))

            try:
                self._bootloader.program_image(
                    image,
                    timeout_seconds=3.0,
                    erase_timeout_seconds=10.0,
                    progress=report_progress,
                )
            except (Exception, SystemExit) as exc:
                if not jump_started or not self._is_usb_disconnect(exc):
                    raise
                self.log_message.emit(f"JUMP 后 USB 已断开，等待应用重新枚举: {exc}")
            self._close_driver()
            self._sleep(1.5)
            app_port = self._wait_for_port()
            self._driver = self._open_driver(app_port.device, 115200)
            host = self._host_factory(self._driver)
            status = host.query_status(seq=self._next_seq(), timeout_seconds=0.5)
            if status.status != 0:
                raise RuntimeError(f"应用状态异常: 0x{status.status:02X}")
            self._host = host
            self._choice = app_port
            self._telemetry.link_ok = True
            self._deadlines = {name: 0.0 for name in self._intervals}
            self._set_state("APPLICATION", app_port.device)
            self._timer.start()
            self.upgrade_progress.emit("DONE", 100)
            self.upgrade_finished.emit(True, "固件升级完成")
        except (Exception, SystemExit) as exc:
            self.log_message.emit(f"升级失败: {exc}")
            if self._bootloader is not None and self._driver is not None:
                self._set_state("BOOTLOADER", str(exc))
                self._timer.start()
            elif self._host is not None and self._driver is not None:
                self._set_state("APPLICATION", str(exc))
                self._timer.start()
            else:
                self._set_state("DISCONNECTED", str(exc))
            self.upgrade_finished.emit(False, str(exc))


class RtkSerialWorker(QObject):
    state_changed = Signal(str, str)
    received = Signal(bytes)
    log_message = Signal(str)
    command_finished = Signal(str, bool, str)

    def __init__(self, driver_factory=SerialDriver.open, poll_interval_ms=10, read_size=8192, parent=None):
        super().__init__(parent)
        self._driver_factory = driver_factory
        self._driver = None
        self._read_size = read_size
        self._timer = QTimer(self)
        self._timer.setInterval(poll_interval_ms)
        self._timer.timeout.connect(self.poll_once)

    @Slot(object, int)
    def connect_port(self, choice: PortChoice, baudrate: int) -> None:
        self.disconnect_port()
        try:
            self._driver = self._driver_factory(choice.device, baudrate, 0.0)
            self._timer.start()
            self.state_changed.emit("CONNECTED", f"{choice.device} @ {baudrate}")
        except (Exception, SystemExit) as exc:
            self._driver = None
            self.state_changed.emit("DISCONNECTED", str(exc))
            self.log_message.emit(str(exc))

    @Slot()
    def disconnect_port(self) -> None:
        self._timer.stop()
        if self._driver is not None:
            self._driver.close()
        self._driver = None
        self.state_changed.emit("DISCONNECTED", "")

    @Slot()
    def poll_once(self) -> None:
        if self._driver is None:
            return
        try:
            data = self._driver.read(self._read_size)
            if data:
                self.received.emit(data)
        except (Exception, SystemExit) as exc:
            self.log_message.emit(str(exc))
            self.disconnect_port()

    @Slot(bytes)
    def send(self, data: bytes) -> None:
        if self._driver is None:
            self.command_finished.emit("RTK 发送", False, "设备未连接")
            return
        try:
            written = self._driver.write(data)
            if written != len(data):
                raise RuntimeError(f"仅发送 {written}/{len(data)} bytes")
            self.log_message.emit(f"TX {data.hex(' ').upper()}")
            self.command_finished.emit("RTK 发送", True, f"{written} bytes")
        except (Exception, SystemExit) as exc:
            self.command_finished.emit("RTK 发送", False, str(exc))
