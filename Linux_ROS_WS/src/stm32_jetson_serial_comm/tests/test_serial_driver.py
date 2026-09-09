#!/usr/bin/env python3
import pathlib
import sys
import types
import unittest

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from stm32_jetson_serial_comm.serial_driver import SerialDriver, read_for_seconds


class FakePort:
    def __init__(self, reads=None):
        self.reads = list(reads or [])
        self.writes = []
        self.flushed = False
        self.closed = False

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data)

    def flush(self):
        self.flushed = True

    def read(self, _size):
        if self.reads:
            return self.reads.pop(0)
        return b""

    def close(self):
        self.closed = True


class SerialDriverTest(unittest.TestCase):
    def test_write_sends_bytes_and_flushes(self):
        port = FakePort()
        driver = SerialDriver(port)

        written = driver.write(b"\xAA\x55")

        self.assertEqual(written, 2)
        self.assertEqual(port.writes, [b"\xAA\x55"])
        self.assertTrue(port.flushed)

    def test_read_for_seconds_collects_available_chunks(self):
        port = FakePort([b"\xAA", b"\x55", b""])

        data = read_for_seconds(port, seconds=0.02, monotonic_step=0.01)

        self.assertEqual(data, b"\xAA\x55")

    def test_context_manager_closes_port(self):
        port = FakePort()

        with SerialDriver(port):
            pass

        self.assertTrue(port.closed)

    def test_open_reports_missing_device_with_actionable_hint(self):
        original_serial = sys.modules.get("serial")
        fake_serial = types.SimpleNamespace(
            EIGHTBITS=8,
            PARITY_NONE="N",
            STOPBITS_ONE=1,
        )

        class FakeSerialException(Exception):
            pass

        def fail_open(**_kwargs):
            raise FakeSerialException("could not open port /dev/ttyTHS0")

        fake_serial.SerialException = FakeSerialException
        fake_serial.Serial = fail_open
        sys.modules["serial"] = fake_serial

        try:
            with self.assertRaises(SystemExit) as context:
                SerialDriver.open("/dev/ttyTHS0", 115200)
        finally:
            if original_serial is None:
                sys.modules.pop("serial", None)
            else:
                sys.modules["serial"] = original_serial

        message = str(context.exception)
        self.assertIn("/dev/ttyTHS0", message)
        self.assertIn("ls -l /dev/ttyTHS*", message)
        self.assertIn("串口设备不存在", message)


if __name__ == "__main__":
    unittest.main()
