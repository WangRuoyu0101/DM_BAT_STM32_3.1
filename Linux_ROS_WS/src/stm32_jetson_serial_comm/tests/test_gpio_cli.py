#!/usr/bin/env python3
import pathlib
import sys
import unittest
from unittest import mock


PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from stm32_jetson_serial_comm import gpio_cli
from stm32_jetson_serial_comm.messages import GpioControlResult


class FakeSerialHost:
    instances = []

    def __init__(self, driver):
        self.driver = driver
        self.calls = []
        FakeSerialHost.instances.append(self)

    def control_gpio(self, channel_id, level, seq=0, timeout_seconds=0.5, poll_interval=0.01):
        self.calls.append((channel_id, level, seq, timeout_seconds, poll_interval))
        return GpioControlResult(seq=seq, channel_id=channel_id, result=0x00)


class FakeSerialDriver:
    @classmethod
    def open(cls, device, baudrate, timeout):
        return cls(device, baudrate, timeout)

    def __init__(self, device, baudrate, timeout):
        self.device = device
        self.baudrate = baudrate
        self.timeout = timeout
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        self.closed = True


class GpioCliTest(unittest.TestCase):
    def setUp(self):
        FakeSerialHost.instances = []

    def test_parser_accepts_short_named_channel_and_level(self):
        parser = gpio_cli.build_arg_parser()

        args = parser.parse_args(["led", "on", "--seq", "0x20"])

        self.assertEqual(args.channel, "led")
        self.assertEqual(args.level, "on")
        self.assertEqual(args.seq, 0x20)

    def test_dm3_flash_channels_keep_existing_wire_ids(self):
        self.assertEqual(gpio_cli.GPIO_CHANNELS["flash_ctr"], 0x01)
        self.assertEqual(gpio_cli.GPIO_CHANNELS["flash"], 0x05)
        self.assertNotIn("morotx_sw", gpio_cli.GPIO_CHANNELS)
        self.assertNotIn("reserved", gpio_cli.GPIO_CHANNELS)

    @mock.patch.object(gpio_cli, "SerialDriver", FakeSerialDriver)
    @mock.patch.object(gpio_cli, "SerialHost", FakeSerialHost)
    def test_main_controls_named_gpio_channel(self):
        with mock.patch("builtins.print") as print_mock:
            exit_code = gpio_cli.main(["led", "on", "--seq", "0x20", "--timeout", "0.05"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(FakeSerialHost.instances[0].calls, [(0x02, 1, 0x20, 0.05, 0.01)])
        print_mock.assert_called_with("GPIO led -> ON: OK(0x00)")

    def test_parse_channel_rejects_unknown_name(self):
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            gpio_cli.build_arg_parser().parse_args(["unknown", "on"])


if __name__ == "__main__":
    unittest.main()
