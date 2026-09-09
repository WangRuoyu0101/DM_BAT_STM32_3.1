#!/usr/bin/env python3
import pathlib
import sys
import unittest
from unittest import mock


PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from stm32_jetson_serial_comm import fan_cli
from stm32_jetson_serial_comm.messages import BoardIOStatus, FanControlResult


class FakeHost:
    def __init__(self, _driver):
        pass

    def set_fan_level(self, level, seq=0, timeout_seconds=0.5):
        return FanControlResult(seq, level, 0)

    def query_board_io(self, seq=0, timeout_seconds=0.5):
        return BoardIOStatus(seq, 2, 3000, 3100, 1)


class FakeDriver:
    @classmethod
    def open(cls, *_args):
        return cls()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass


class FanCliTest(unittest.TestCase):
    def test_parser_accepts_four_levels_and_status(self):
        self.assertEqual(fan_cli.build_arg_parser().parse_args(["set", "4"]).level, 4)
        self.assertEqual(fan_cli.build_arg_parser().parse_args(["status"]).command, "status")
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            fan_cli.build_arg_parser().parse_args(["set", "5"])

    @mock.patch.object(fan_cli, "SerialDriver", FakeDriver)
    @mock.patch.object(fan_cli, "SerialHost", FakeHost)
    def test_set_and_status_commands(self):
        with mock.patch("builtins.print") as output:
            self.assertEqual(fan_cli.main(["set", "3"]), 0)
            output.assert_called_with("FAN level 3 (75%): OK")
        with mock.patch("builtins.print") as output:
            self.assertEqual(fan_cli.main(["status"]), 0)
            output.assert_called_with("FAN level=2 (50%) rpm1=3000 rpm2=3100 keys=0x01")


if __name__ == "__main__":
    unittest.main()
