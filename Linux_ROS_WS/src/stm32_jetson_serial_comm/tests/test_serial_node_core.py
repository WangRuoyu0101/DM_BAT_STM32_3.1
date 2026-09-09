#!/usr/bin/env python3
import pathlib
import sys
import unittest

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from stm32_jetson_serial_comm.messages import BoardIOStatus, CS1237Status, GpioStatus, SlaveStatus, UltrasonicStatus
from stm32_jetson_serial_comm.serial_host import SerialTimeoutError
from stm32_jetson_serial_comm.serial_node_core import SerialNodeCore


class FakeHost:
    def __init__(self):
        self.status = SlaveStatus(seq=0, tick=12345, status=0, gpio_bitmap=0x03)
        self.gpio = GpioStatus(seq=0, gpio_bitmap=0x21)
        self.ultrasonic = UltrasonicStatus(
            seq=0,
            front_mm=1000,
            left_mm=2000,
            right_mm=0xFFFD,
            valid_bitmap=0x03,
            error_bitmap=0x30,
        )
        self.calls = []
        self.failures = []
        self.cs1237 = CS1237Status(seq=0, raw_adc=4100000, channel=2, valid=True, error=0)
        self.board_io = BoardIOStatus(seq=0, fan_level=2, fan1_rpm=3000, fan2_rpm=3100, key_bitmap=1)

    def _maybe_raise(self, name):
        self.calls.append(name)
        if self.failures:
            raise self.failures.pop(0)

    def query_status(self, seq, timeout_seconds):
        self._maybe_raise(("status", seq, timeout_seconds))
        return SlaveStatus(
            seq=seq,
            tick=self.status.tick,
            status=self.status.status,
            gpio_bitmap=self.status.gpio_bitmap,
        )

    def query_gpio(self, seq, timeout_seconds):
        self._maybe_raise(("gpio", seq, timeout_seconds))
        return GpioStatus(seq=seq, gpio_bitmap=self.gpio.gpio_bitmap)

    def query_ultrasonic(self, seq, timeout_seconds):
        self._maybe_raise(("ultrasonic", seq, timeout_seconds))
        return UltrasonicStatus(
            seq=seq,
            front_mm=self.ultrasonic.front_mm,
            left_mm=self.ultrasonic.left_mm,
            right_mm=self.ultrasonic.right_mm,
            valid_bitmap=self.ultrasonic.valid_bitmap,
            error_bitmap=self.ultrasonic.error_bitmap,
        )

    def query_cs1237(self, seq, timeout_seconds):
        self._maybe_raise(("cs1237", seq, timeout_seconds))
        return CS1237Status(
            seq=seq,
            raw_adc=self.cs1237.raw_adc,
            channel=self.cs1237.channel,
            valid=self.cs1237.valid,
            error=self.cs1237.error,
        )

    def query_board_io(self, seq, timeout_seconds):
        self._maybe_raise(("board_io", seq, timeout_seconds))
        return BoardIOStatus(
            seq=seq,
            fan_level=self.board_io.fan_level,
            fan1_rpm=self.board_io.fan1_rpm,
            fan2_rpm=self.board_io.fan2_rpm,
            key_bitmap=self.board_io.key_bitmap,
        )


class SerialNodeCoreTest(unittest.TestCase):
    def test_board_io_poll_returns_ros_ready_values(self):
        host = FakeHost()
        result = SerialNodeCore(host).poll_board_io()

        self.assertEqual(host.calls, [("board_io", 0, 0.2)])
        self.assertEqual(result.fan_rpm, [3000, 3100])
        self.assertEqual(result.fan_level, 2)
        self.assertEqual(result.key_bitmap, 1)
        self.assertEqual(
            result.board_io_text,
            "STM32 board IO: seq=0x00 fan_level=2 fan1=3000rpm fan2=3100rpm keys=0x01",
        )

    def test_cs1237_poll_formats_temperature(self):
        host = FakeHost()
        core = SerialNodeCore(host)

        result = core.poll_cs1237()

        self.assertEqual(host.calls, [("cs1237", 0, 0.2)])
        self.assertEqual(result.cs1237_raw, 4100000)
        self.assertIn("temperature=23.00 C", result.cs1237_text)

    def test_individual_poll_methods_query_one_source_each(self):
        host = FakeHost()
        core = SerialNodeCore(host, timeout_seconds=0.2)

        status_result = core.poll_status()
        gpio_result = core.poll_gpio()
        ultrasonic_result = core.poll_ultrasonic()

        self.assertEqual(
            host.calls,
            [
                ("status", 0x00, 0.2),
                ("gpio", 0x01, 0.2),
                ("ultrasonic", 0x02, 0.2),
            ],
        )
        self.assertEqual(
            status_result.status_text,
            "STM32 status: seq=0x00 tick=12345 status=OK(0x00) app_gpio=0x03",
        )
        self.assertEqual(
            gpio_result.gpio_text,
            "STM32 GPIO: seq=0x01 bitmap=0x21 outputs=[flash_ctr=ON, led=OFF, bee=OFF, motor=OFF, flash=OFF, sound=ON]",
        )
        self.assertEqual(
            ultrasonic_result.ultrasonic_text,
            "STM32 ultrasonic: seq=0x02 front=1000mm(OK) left=2000mm(OK) right=0mm(NO_TARGET)",
        )
        self.assertEqual(core.success_count, 3)

    def test_poll_once_queries_enabled_sources_and_returns_publications(self):
        host = FakeHost()
        core = SerialNodeCore(host, timeout_seconds=0.2)

        result = core.poll_once()

        self.assertEqual(
            host.calls,
            [
                ("status", 0x00, 0.2),
                ("gpio", 0x01, 0.2),
                ("ultrasonic", 0x02, 0.2),
            ],
        )
        self.assertTrue(result.link_ok)
        self.assertEqual(
            result.status_text,
            "STM32 status: seq=0x00 tick=12345 status=OK(0x00) app_gpio=0x03",
        )
        self.assertEqual(
            result.gpio_text,
            "STM32 GPIO: seq=0x01 bitmap=0x21 outputs=[flash_ctr=ON, led=OFF, bee=OFF, motor=OFF, flash=OFF, sound=ON]",
        )
        self.assertEqual(result.gpio_bitmap, 0x21)
        self.assertEqual(
            result.ultrasonic_text,
            "STM32 ultrasonic: seq=0x02 front=1000mm(OK) left=2000mm(OK) right=0mm(NO_TARGET)",
        )
        self.assertEqual(result.ultrasonic_mm, [1000, 2000, 0xFFFD, 0x03, 0x30])
        self.assertEqual(core.next_seq, 0x03)
        self.assertEqual(core.success_count, 3)
        self.assertEqual(core.timeout_count, 0)

    def test_poll_once_can_disable_optional_queries(self):
        host = FakeHost()
        core = SerialNodeCore(host, query_gpio=False, query_ultrasonic=False)

        result = core.poll_once()

        self.assertEqual(host.calls, [("status", 0x00, 0.2)])
        self.assertTrue(result.link_ok)
        self.assertIsNone(result.gpio_bitmap)
        self.assertIsNone(result.gpio_text)
        self.assertIsNone(result.ultrasonic_mm)
        self.assertIsNone(result.ultrasonic_text)

    def test_poll_once_reports_link_down_after_timeout(self):
        host = FakeHost()
        host.failures.append(SerialTimeoutError("no frame"))
        core = SerialNodeCore(host, timeout_seconds=0.1)

        result = core.poll_once()

        self.assertFalse(result.link_ok)
        self.assertEqual(result.error_text, "no frame")
        self.assertEqual(core.timeout_count, 1)
        self.assertEqual(core.success_count, 0)
        self.assertEqual(core.next_seq, 0x01)

    def test_ultrasonic_text_decodes_timeout_per_sensor(self):
        host = FakeHost()
        host.ultrasonic = UltrasonicStatus(
            seq=0,
            front_mm=0,
            left_mm=0,
            right_mm=0,
            valid_bitmap=0x00,
            error_bitmap=0x15,
        )
        core = SerialNodeCore(host, timeout_seconds=0.2)

        result = core.poll_once()

        self.assertEqual(
            result.ultrasonic_text,
            "STM32 ultrasonic: seq=0x02 front=0mm(TIMEOUT) left=0mm(TIMEOUT) right=0mm(TIMEOUT)",
        )

    def test_seq_wraps_at_one_byte(self):
        host = FakeHost()
        core = SerialNodeCore(host, query_gpio=False, query_ultrasonic=False)
        core.next_seq = 0xFF

        core.poll_once()
        core.poll_once()

        self.assertEqual(host.calls[0], ("status", 0xFF, 0.2))
        self.assertEqual(host.calls[1], ("status", 0x00, 0.2))
        self.assertEqual(core.next_seq, 0x01)


if __name__ == "__main__":
    unittest.main()
