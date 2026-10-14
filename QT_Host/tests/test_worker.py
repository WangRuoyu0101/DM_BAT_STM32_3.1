import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PySide6.QtCore import QCoreApplication

from dm31_host.core import PortChoice
from dm31_host.worker import RtkSerialWorker, SerialWorker, _LoggingDriver
from stm32_jetson_serial_comm.bootloader import BootloaderStatus
from stm32_jetson_serial_comm.serial_host import SerialTimeoutError, UnexpectedFrameError


class FakeDriver:
    def __init__(self, device, baudrate):
        self.device = device
        self.baudrate = baudrate
        self.closed = False

    def close(self):
        self.closed = True


class WorkerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def make_worker(
        self,
        poll_intervals=None,
        bootloader_mode=False,
        program_errors=None,
        jump_error=None,
    ):
        drivers = []
        bootloaders = []
        program_errors = list(program_errors or [])

        def driver_factory(device, baudrate, _timeout):
            driver = FakeDriver(device, baudrate)
            drivers.append(driver)
            return driver

        class Host:
            def __init__(self, driver):
                self.driver = driver
                self.rgb_commands = []
                self.rgb_queries = 0
                self.status_queries = 0

            def query_status(self, **_kwargs):
                self.status_queries += 1
                return SimpleNamespace(status=0)

            def query_gpio(self, **_kwargs):
                return SimpleNamespace(gpio_bitmap=0x21)

            def query_ultrasonic(self, **_kwargs):
                return SimpleNamespace(
                    front_mm=100,
                    left_mm=200,
                    right_mm=300,
                    valid_bitmap=7,
                    error_bitmap=0,
                )

            def query_cs1237(self, **_kwargs):
                return SimpleNamespace(raw_adc=1234, channel=2, valid=True, error=0)

            def query_board_io(self, **_kwargs):
                return SimpleNamespace(fan_level=2, fan1_rpm=3000, fan2_rpm=3100, key_bitmap=1)

            def query_rgb(self, **_kwargs):
                self.rgb_queries += 1
                return SimpleNamespace(
                    red=255,
                    green=183,
                    blue=197,
                    brightness=25,
                    mode=2,
                    output_on=True,
                )

            def control_gpio(self, channel_id, level, **_kwargs):
                return SimpleNamespace(channel_id=channel_id, result=0, level=level)

            def set_fan_level(self, level, **_kwargs):
                return SimpleNamespace(level=level, result=0)

            def set_cs1237_channel(self, channel, **_kwargs):
                return SimpleNamespace(channel=channel, result=0)

            def set_rgb(self, red, green, blue, brightness, mode, **_kwargs):
                self.rgb_commands.append((red, green, blue, brightness, mode))
                return SimpleNamespace(result=0)

        class Bootloader:
            def __init__(self, driver, status_callback=None):
                self.driver = driver
                self.requested = False
                self.status_callback = status_callback
                bootloaders.append(self)

            def hello(self, **_kwargs):
                if not bootloader_mode:
                    raise SerialTimeoutError("application mode")
                return SimpleNamespace(version=0x00020000)

            def read_status(self, **_kwargs):
                status = BootloaderStatus(0, False, 0, 0)
                if self.status_callback is not None:
                    self.status_callback(status)
                return status

            def request_app_bootloader(self, **_kwargs):
                self.requested = True

            def program_image(self, image, progress, **_kwargs):
                if program_errors:
                    raise program_errors.pop(0)
                progress("HELLO")
                progress(f"WRITE offset=0 size={len(image)}")
                progress("VERIFY")
                progress("JUMP")
                if jump_error is not None:
                    raise jump_error
                return SimpleNamespace(app_size=0x78000)

        ports = lambda: [SimpleNamespace(
            device="COM7",
            description="STM32",
            hwid="USB",
            vid=1,
            pid=2,
            serial_number="ABC",
        )]
        worker = SerialWorker(
            driver_factory=driver_factory,
            host_factory=Host,
            bootloader_factory=Bootloader,
            port_source=ports,
            sleep=lambda _seconds: None,
            poll_intervals=poll_intervals,
        )
        return worker, drivers, bootloaders

    def test_logging_driver_reports_frame_id_and_hex_bytes(self):
        class Driver:
            def write(self, data):
                return len(data)

            def read(self, _size):
                return b"\xAA\x55\x81\x00\x8E"

            def close(self):
                pass

        logs = []
        driver = _LoggingDriver(Driver(), logs.append)
        driver.write(b"\xAA\x55\x01\x00\x15")
        driver.read()

        self.assertIn("[STM32] TX frame=0x01 AA 55 01 00 15", logs)
        self.assertIn("[STM32] RX frame=0x81 AA 55 81 00 8E", logs)

    def test_connect_poll_and_controls_publish_decoded_state(self):
        worker, drivers, _bootloaders = self.make_worker()
        telemetry = []
        commands = []
        logs = []
        worker.telemetry_changed.connect(telemetry.append)
        worker.command_finished.connect(lambda *args: commands.append(args))
        worker.log_message.connect(logs.append)

        worker.connect_port(PortChoice("COM7", vid=1, pid=2, serial_number="ABC"))
        worker._deadlines = {name: 0.0 for name in worker._deadlines}
        for _ in range(5):
            worker.poll_once()
        worker.set_gpio(2, 1)
        worker.set_fan(3)
        worker.set_cs1237_channel(2)

        sample = telemetry[-1]
        self.assertTrue(sample.link_ok)
        self.assertEqual(sample.gpio_bitmap, 0x21)
        self.assertEqual((sample.fan_level, sample.fan1_rpm, sample.fan2_rpm), (2, 3000, 3100))
        self.assertEqual((sample.ultrasonic_front_mm, sample.cs1237_raw), (100, 1234))
        self.assertIsNotNone(sample.board_io_timestamp)
        self.assertEqual([item[:2] for item in commands], [("GPIO 2", True), ("风扇", True), ("CS1237", True)])
        self.assertEqual(drivers[0].baudrate, 115200)

        worker.configure_polling(
            {
                "status": 1.0,
                "gpio": 2.0,
                "ultrasonic": 4.0,
                "cs1237": 8.0,
                "board_io": 2.0,
                "rgb": 2.0,
            },
            {name: True for name in worker._intervals},
            0.35,
        )
        self.assertEqual(worker._intervals["gpio"], 0.5)
        self.assertEqual(worker._serial_timeout, 0.35)

    def test_rgb_control_and_poll_update_flat_telemetry(self):
        worker, _drivers, _bootloaders = self.make_worker()
        worker.connect_port(PortChoice("COM7", vid=1, pid=2, serial_number="ABC"))
        host = worker._host

        self.assertEqual(worker._intervals["rgb"], 0.5)
        worker.set_rgb(255, 183, 197, 25, 2)
        self.assertIn((255, 183, 197, 25, 2), host.rgb_commands)
        worker._poll_rgb()
        self.assertEqual(worker._telemetry.rgb_red, 255)
        self.assertEqual(worker._telemetry.rgb_mode, 2)
        self.assertTrue(worker._telemetry.rgb_output_on)

    def test_connect_recognizes_bootloader_and_publishes_idle_status(self):
        worker, drivers, _bootloaders = self.make_worker(bootloader_mode=True)
        states = []
        statuses = []
        worker.state_changed.connect(lambda *args: states.append(args))
        worker.bootloader_status_changed.connect(statuses.append)

        worker.connect_port(PortChoice("COM7", vid=1, pid=2, serial_number="ABC"))
        worker.poll_once()

        self.assertEqual([driver.baudrate for driver in drivers], [115200])
        self.assertEqual(states[-1][0], "BOOTLOADER")
        self.assertEqual(statuses[-1], BootloaderStatus(0, False, 0, 0))
        self.assertTrue(worker._timer.isActive())

    def test_upgrade_exclusively_switches_baudrate_and_recovers_application(self):
        worker, drivers, bootloaders = self.make_worker()
        states = []
        finished = []
        worker.state_changed.connect(lambda *args: states.append(args))
        worker.upgrade_finished.connect(lambda *args: finished.append(args))
        worker.connect_port(PortChoice("COM7", vid=1, pid=2, serial_number="ABC"))

        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "DM3.1_BAT_app.bin"
            image.write_bytes(b"firmware")
            worker.upgrade(str(image), True)

        self.assertEqual([driver.baudrate for driver in drivers], [115200, 460800, 115200])
        self.assertTrue(any(bootloader.requested for bootloader in bootloaders))
        self.assertEqual(finished[-1][0], True)
        self.assertEqual(states[-1][0], "APPLICATION")
        self.assertTrue(worker._timer.isActive())
        self.assertEqual(worker._host.status_queries, 1)

    def test_jump_usb_disconnect_waits_for_and_verifies_application(self):
        worker, _drivers, _bootloaders = self.make_worker(
            jump_error=RuntimeError("read failed: [Errno 6] Device not configured")
        )
        logs = []
        finished = []
        worker.log_message.connect(logs.append)
        worker.upgrade_finished.connect(lambda *args: finished.append(args))
        worker.connect_port(PortChoice("COM7", vid=1, pid=2, serial_number="ABC"))

        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "DM3.1_BAT_app.bin"
            image.write_bytes(b"firmware")
            worker.upgrade(str(image), True)

        self.assertTrue(finished[-1][0])
        self.assertEqual(worker._state, "APPLICATION")
        self.assertEqual(worker._host.status_queries, 1)
        self.assertTrue(any("JUMP 后 USB 已断开" in message for message in logs))

    def test_bootloader_only_upgrade_accepts_wrapped_usb_disconnect(self):
        worker, _drivers, _bootloaders = self.make_worker(
            bootloader_mode=True,
            jump_error=RuntimeError("read failed: [Errno 6] Device not configured"),
        )
        finished = []
        worker.upgrade_finished.connect(lambda *args: finished.append(args))
        worker.connect_port(PortChoice("COM7", vid=1, pid=2, serial_number="ABC"))

        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "DM3.1_BAT_app.bin"
            image.write_bytes(b"firmware")
            worker.upgrade(str(image), False)

        self.assertTrue(finished[-1][0])
        self.assertEqual(worker._state, "APPLICATION")
        self.assertEqual(worker._host.status_queries, 1)

    def test_usb_disconnect_detection_checks_wrapped_and_chained_errors(self):
        wrapped = RuntimeError("read failed: [Errno 6] Device not configured")
        try:
            try:
                raise OSError(19, "No such device")
            except OSError as exc:
                raise RuntimeError("serial read failed") from exc
        except RuntimeError as chained:
            self.assertTrue(SerialWorker._is_usb_disconnect(chained))

        self.assertTrue(SerialWorker._is_usb_disconnect(wrapped))
        self.assertFalse(SerialWorker._is_usb_disconnect(RuntimeError("CRC mismatch")))

    def test_failed_upgrade_keeps_bootloader_connected_and_can_retry(self):
        worker, _drivers, _bootloaders = self.make_worker(
            program_errors=[RuntimeError("write failed")]
        )
        states = []
        finished = []
        worker.state_changed.connect(lambda *args: states.append(args))
        worker.upgrade_finished.connect(lambda *args: finished.append(args))
        worker.connect_port(PortChoice("COM7", vid=1, pid=2, serial_number="ABC"))

        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "DM3.1_BAT_app.bin"
            image.write_bytes(b"firmware")
            worker.upgrade(str(image), True)
            self.assertEqual(states[-1][0], "BOOTLOADER")
            self.assertFalse(finished[-1][0])
            self.assertIsNotNone(worker._driver)
            self.assertTrue(worker._timer.isActive())

            worker.upgrade(str(image), False)

        self.assertTrue(finished[-1][0])
        self.assertEqual(states[-1][0], "APPLICATION")

    def test_configure_polling_accepts_legacy_ui_dictionaries_without_rgb(self):
        worker, _drivers, _bootloaders = self.make_worker()
        commands = []
        worker.command_finished.connect(lambda *args: commands.append(args))
        rates = {"status": 1.0, "gpio": 2.0, "ultrasonic": 4.0, "cs1237": 8.0, "board_io": 2.0}
        enabled = {name: True for name in worker._enabled}
        enabled["rgb"] = False
        worker.configure_polling({**rates, "rgb": 4.0}, enabled, 0.35)

        legacy_enabled = {name: value for name, value in enabled.items() if name != "rgb"}
        legacy_enabled["gpio"] = False
        worker.configure_polling(rates, legacy_enabled, 0.4)

        self.assertEqual(commands[-1], ("轮询设置", True, "OK"))
        self.assertEqual(worker._intervals["gpio"], 0.5)
        self.assertEqual(worker._intervals["rgb"], 0.25)
        self.assertFalse(worker._enabled["gpio"])
        self.assertFalse(worker._enabled["rgb"])
        self.assertEqual(worker._serial_timeout, 0.4)

    def test_poll_switches_disable_queries_and_reenable_immediately(self):
        worker, _drivers, _bootloaders = self.make_worker()
        worker.connect_port(PortChoice("COM7", vid=1, pid=2, serial_number="ABC"))
        calls = []
        for name in worker._intervals:
            if name == "rgb":
                continue
            setattr(worker, f"_poll_{name}", lambda name=name: calls.append(name))

        rates = {
            "status": 1.0,
            "gpio": 2.0,
            "ultrasonic": 4.0,
            "cs1237": 8.0,
            "board_io": 2.0,
            "rgb": 2.0,
        }
        enabled = {name: False for name in worker._intervals}
        worker.configure_polling(rates, enabled, 0.35)
        worker.poll_once()
        self.assertEqual(calls, [])
        self.assertEqual(worker._host.rgb_queries, 0)
        enabled["gpio"] = True
        worker.configure_polling(rates, enabled, 0.35)
        worker.poll_once()
        self.assertEqual(calls, ["gpio"])

        enabled["gpio"] = False
        enabled["rgb"] = True
        worker.configure_polling(rates, enabled, 0.35)
        worker.poll_once()
        self.assertEqual(worker._host.rgb_queries, 1)

    def test_invalid_poll_rates_do_not_change_active_settings(self):
        worker, _drivers, _bootloaders = self.make_worker()
        commands = []
        worker.command_finished.connect(lambda *args: commands.append(args))
        original = dict(worker._intervals)
        enabled = {name: True for name in worker._intervals}

        for invalid in (float("inf"), float("nan"), "not-a-number"):
            rates = {
                "status": invalid,
                "gpio": 2.0,
                "ultrasonic": 4.0,
                "cs1237": 8.0,
                "board_io": 2.0,
                "rgb": 2.0,
            }
            try:
                worker.configure_polling(rates, enabled, 0.35)
            except ValueError:
                self.fail("invalid polling rate escaped validation")
            self.assertEqual(worker._intervals, original)
            self.assertEqual(commands[-1][0:2], ("轮询设置", False))

    def test_unsupported_rgb_poll_keeps_old_firmware_connected(self):
        worker, drivers, _bootloaders = self.make_worker()
        logs = []
        worker.log_message.connect(logs.append)
        worker.connect_port(PortChoice("COM7", vid=1, pid=2, serial_number="ABC"))
        worker._host.query_rgb = mock.Mock(
            side_effect=UnexpectedFrameError("expected frame 0x8D, got 0xE1")
        )
        worker._deadlines = {name: float("inf") for name in worker._deadlines}
        worker._deadlines["rgb"] = 0.0

        worker.poll_once()
        worker.poll_once()

        self.assertEqual(worker._state, "APPLICATION")
        self.assertFalse(drivers[0].closed)
        self.assertEqual(worker._host.query_rgb.call_count, 1)
        self.assertIn("rgb: 固件不支持 RGB 回读，已暂停本次连接的 RGB 轮询", logs)

    def test_rtk_worker_uses_direct_serial_port(self):
        class Driver:
            def __init__(self):
                self.reads = [b"$GNGGA,,,,,,0,,,,,,,,*78\r\n", b""]
                self.writes = []
                self.closed = False

            def read(self, size):
                self.assert_size = size
                return self.reads.pop(0)

            def write(self, data):
                self.writes.append(data)
                return len(data)

            def close(self):
                self.closed = True

        driver = Driver()
        opened = []

        def factory(device, baudrate, timeout):
            opened.append((device, baudrate, timeout))
            return driver

        worker = RtkSerialWorker(driver_factory=factory)
        states = []
        received = []
        commands = []
        worker.state_changed.connect(lambda *args: states.append(args))
        worker.received.connect(received.append)
        worker.command_finished.connect(lambda *args: commands.append(args))

        worker.connect_port(PortChoice("COM8"), 921600)
        worker.poll_once()
        worker.send(b"LOG VERSION\r\n")
        worker.disconnect_port()

        self.assertEqual(opened, [("COM8", 921600, 0.0)])
        self.assertEqual(received, [b"$GNGGA,,,,,,0,,,,,,,,*78\r\n"])
        self.assertEqual(driver.writes, [b"LOG VERSION\r\n"])
        self.assertEqual(commands[-1], ("RTK 发送", True, "13 bytes"))
        self.assertEqual(states[-1][0], "DISCONNECTED")
        self.assertTrue(driver.closed)

if __name__ == "__main__":
    unittest.main()
