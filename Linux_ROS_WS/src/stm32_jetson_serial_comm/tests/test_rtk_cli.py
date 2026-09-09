#!/usr/bin/env python3
from pathlib import Path
import io
import sys
import unittest
from unittest import mock

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from stm32_jetson_serial_comm.rtk_bridge import RtkOverflowError
from stm32_jetson_serial_comm.rtk_cli import build_arg_parser, encode_text_command, main


class RtkCliTest(unittest.TestCase):
    def test_text_command_appends_exactly_one_crlf(self):
        self.assertEqual(encode_text_command("GPGGA 1"), b"GPGGA 1\r\n")
        self.assertEqual(encode_text_command("saveconfig\r\n"), b"saveconfig\r\n")

    def test_cli_accepts_send_and_listen_modes(self):
        parser = build_arg_parser()
        self.assertEqual(parser.parse_args(["--send-text", "GPGGA 1"]).send_text, "GPGGA 1")
        self.assertEqual(parser.parse_args(["--send-hex", "D3 00"]).send_hex, "D3 00")
        self.assertTrue(parser.parse_args(["--listen"]).listen)

    def test_setup_registers_console_command(self):
        setup = (PACKAGE_ROOT / "setup.py").read_text(encoding="utf-8")
        self.assertIn("stm32_rtk = stm32_jetson_serial_comm.rtk_cli:main", setup)

    def test_listen_exits_cleanly_on_keyboard_interrupt(self):
        with mock.patch("stm32_jetson_serial_comm.rtk_cli.SerialDriver") as driver, \
             mock.patch("stm32_jetson_serial_comm.rtk_cli.RtkBridge") as bridge:
            driver.open.return_value.__enter__.return_value = object()
            bridge.return_value.read.side_effect = KeyboardInterrupt

            self.assertEqual(main(["--listen"]), 130)

    def test_command_drains_stale_overflow_before_writing(self):
        stderr = io.StringIO()
        with mock.patch("stm32_jetson_serial_comm.rtk_cli.SerialDriver") as driver, \
             mock.patch("stm32_jetson_serial_comm.rtk_cli.RtkBridge") as bridge, \
             mock.patch("sys.stderr", stderr):
            driver.open.return_value.__enter__.return_value = object()
            bridge.return_value.read.side_effect = [
                RtkOverflowError("overflow"),
                b"",
            ]

            self.assertEqual(main(["--send-text", "GPGGA 1", "--read-seconds", "0"]), 0)

        self.assertEqual(
            bridge.return_value.method_calls,
            [
                mock.call.read(),
                mock.call.read(),
                mock.call.write(b"GPGGA 1\r\n"),
            ],
        )
        self.assertEqual(stderr.getvalue().count("overflow"), 1)

    def test_listen_warns_once_and_continues_after_overflow(self):
        stderr = io.StringIO()
        stdout = mock.Mock()
        stdout.buffer = io.BytesIO()
        with mock.patch("stm32_jetson_serial_comm.rtk_cli.SerialDriver") as driver, \
             mock.patch("stm32_jetson_serial_comm.rtk_cli.RtkBridge") as bridge, \
             mock.patch("sys.stderr", stderr), \
             mock.patch("sys.stdout", stdout):
            driver.open.return_value.__enter__.return_value = object()
            bridge.return_value.read.side_effect = [
                RtkOverflowError("overflow"),
                RtkOverflowError("overflow"),
                b"$GNGGA\r\n",
                KeyboardInterrupt,
            ]

            self.assertEqual(main(["--listen"]), 130)

        self.assertEqual(stderr.getvalue().count("overflow"), 1)
        self.assertEqual(stdout.buffer.getvalue(), b"$GNGGA\r\n")


if __name__ == "__main__":
    unittest.main()
