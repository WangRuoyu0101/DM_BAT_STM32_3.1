#!/usr/bin/env python3
import importlib
import pathlib
import sys
import unittest
from unittest import mock

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from stm32_jetson_serial_comm.messages import GpioStatus, SlaveStatus, UltrasonicStatus
from stm32_jetson_serial_comm.serial_link_cli import (
    LOOPBACK_TEST_PATTERN,
    build_arg_parser,
    format_bytes_hex,
    format_gpio_query,
    format_status_query,
    format_ultrasonic_query,
    parse_hex_bytes,
    run_loopback_test,
)


class FakePort:
    def __init__(self, reads=None):
        self.reads = list(reads or [])
        self.writes = []

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data)

    def read(self, _size=256):
        if self.reads:
            return self.reads.pop(0)
        return b""


class SerialLinkTest(unittest.TestCase):
    def test_parse_hex_bytes_accepts_spaces_commas_and_0x_prefixes(self):
        self.assertEqual(
            parse_hex_bytes("AA 55, 0x01 02"),
            bytes([0xAA, 0x55, 0x01, 0x02]),
        )

    def test_parse_hex_bytes_rejects_invalid_tokens(self):
        with self.assertRaises(ValueError):
            parse_hex_bytes("AA 555")

    def test_format_bytes_hex_uses_uppercase_pairs(self):
        self.assertEqual(format_bytes_hex(b"\xaa\x55\x01\x02"), "AA 55 01 02")

    def test_formats_business_queries_for_humans(self):
        self.assertEqual(
            format_status_query(SlaveStatus(seq=0x10, tick=12345, status=0, gpio_bitmap=0x03)),
            "STM32 status: seq=0x10 tick=12345 status=OK(0x00) app_gpio=0x03",
        )
        self.assertIn(
            "usb_busy=1 usb_overflow=2 usb_fail=3",
            format_status_query(
                SlaveStatus(
                    seq=0x10,
                    tick=12345,
                    status=0,
                    gpio_bitmap=0x03,
                    usb_busy_retries=1,
                    usb_queue_overflows=2,
                    usb_tx_failures=3,
                    extended=True,
                )
            ),
        )
        self.assertEqual(
            format_gpio_query(GpioStatus(seq=0x12, gpio_bitmap=0x21)),
            "STM32 GPIO: seq=0x12 bitmap=0x21 outputs=[flash_ctr=ON, led=OFF, bee=OFF, motor=OFF, flash=OFF, sound=ON]",
        )
        self.assertEqual(
            format_ultrasonic_query(
                UltrasonicStatus(
                    seq=0x13,
                    front_mm=1000,
                    left_mm=2000,
                    right_mm=0xFFFD,
                    valid_bitmap=0x03,
                    error_bitmap=0x30,
                )
            ),
            "STM32 ultrasonic: seq=0x13 front=1000mm(OK) left=2000mm(OK) right=0mm(NO_TARGET)",
        )

    def test_cli_accepts_business_query_options(self):
        parser = build_arg_parser()

        self.assertTrue(parser.parse_args(["--query-status"]).query_status)
        self.assertTrue(parser.parse_args(["--query-gpio"]).query_gpio)
        self.assertTrue(parser.parse_args(["--query-ultrasonic"]).query_ultrasonic)
        self.assertEqual(parser.parse_args(["--query-status", "--seq", "0x10"]).seq, 0x10)
        self.assertTrue(parser.parse_args(["--cs1237-query"]).cs1237_query)
        self.assertEqual(parser.parse_args(["--cs1237-set-channel", "temp"]).cs1237_set_channel, "temp")
        self.assertTrue(parser.parse_args(["--cs1237-calibrate-zero"]).cs1237_calibrate_zero)
        self.assertEqual(parser.parse_args(["--cs1237-calibrate-force", "10"]).cs1237_calibrate_force, 10.0)
        self.assertEqual(
            parser.parse_args(["--cs1237-calibrate-temperature", "26"]).cs1237_calibrate_temperature,
            26.0,
        )

    def test_cli_defaults_to_usb_cdc_device(self):
        self.assertEqual(build_arg_parser().parse_args(["--loopback-test"]).device, "/dev/ttyACM0")

    def test_default_device_can_be_overridden_by_environment(self):
        import stm32_jetson_serial_comm.serial_link_cli as serial_link_cli

        with mock.patch.dict("os.environ", {"STM32_SERIAL_DEVICE": "/dev/ttyTHS0"}):
            reloaded = importlib.reload(serial_link_cli)
            self.assertEqual(reloaded.build_arg_parser().parse_args(["--loopback-test"]).device, "/dev/ttyTHS0")

        importlib.reload(serial_link_cli)

    def test_cli_accepts_loopback_test_option(self):
        self.assertTrue(build_arg_parser().parse_args(["--loopback-test"]).loopback_test)

    @mock.patch("builtins.print")
    def test_business_query_prints_human_readable_status(self, print_mock):
        status = SlaveStatus(seq=0x10, tick=12345, status=0, gpio_bitmap=0x03)

        with mock.patch("stm32_jetson_serial_comm.serial_link_cli.SerialDriver") as driver_mock, \
             mock.patch("stm32_jetson_serial_comm.serial_link_cli.SerialHost") as host_mock:
            driver_mock.open.return_value.__enter__.return_value = object()
            host_mock.return_value.query_status.return_value = status

            from stm32_jetson_serial_comm.serial_link_cli import main

            exit_code = main(["--query-status", "--seq", "0x10", "--read-seconds", "3"])

        self.assertEqual(exit_code, 0)
        print_mock.assert_any_call(
            "STM32 status: seq=0x10 tick=12345 status=OK(0x00) app_gpio=0x03"
        )

    def test_loopback_test_passes_when_rx_matches_tx(self):
        port = FakePort([LOOPBACK_TEST_PATTERN])

        ok, message = run_loopback_test(port, timeout_seconds=0.02, monotonic_step=0.01)

        self.assertTrue(ok)
        self.assertIn("通过", message)
        self.assertEqual(port.writes, [LOOPBACK_TEST_PATTERN])

    def test_loopback_test_fails_when_rx_differs_from_tx(self):
        port = FakePort([b"\xAA\x55\x00"])

        ok, message = run_loopback_test(port, timeout_seconds=0.02, monotonic_step=0.01)

        self.assertFalse(ok)
        self.assertIn("失败", message)
        self.assertEqual(port.writes, [LOOPBACK_TEST_PATTERN])


if __name__ == "__main__":
    unittest.main()
