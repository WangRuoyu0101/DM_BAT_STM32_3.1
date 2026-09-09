#!/usr/bin/env python3
import pathlib
import sys
import unittest

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from stm32_jetson_serial_comm.protocol import Frame
from stm32_jetson_serial_comm.rtk_bridge import RtkBridge, RtkOverflowError


class FakeHost:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def request(self, frame_id, payload, timeout_seconds):
        self.requests.append((frame_id, payload, timeout_seconds))
        return self.responses.pop(0)


class RtkBridgeTest(unittest.TestCase):
    def test_write_fragments_arbitrary_bytes_at_249_bytes(self):
        data = bytes(range(250))
        host = FakeHost([
            Frame(0x88, bytes([0x00, 0x00, 249])),
            Frame(0x88, bytes([0x01, 0x00, 1])),
        ])
        bridge = RtkBridge(host)

        bridge.write(data)

        self.assertEqual(host.requests, [
            (0x08, b"\x00" + data[:249], 0.5),
            (0x08, b"\x01" + data[249:], 0.5),
        ])

    def test_read_preserves_binary_and_reports_overflow(self):
        host = FakeHost([Frame(0x89, b"\x00\x00\x00\xff\r\n")])
        bridge = RtkBridge(host)
        self.assertEqual(bridge.read(), b"\x00\xff\r\n")

        host = FakeHost([Frame(0x89, b"\x00\x01")])
        with self.assertRaises(RtkOverflowError):
            RtkBridge(host).read()

    def test_empty_write_and_malformed_response_are_rejected(self):
        host = FakeHost([])
        bridge = RtkBridge(host)
        with self.assertRaises(ValueError):
            bridge.write(b"")

        host = FakeHost([Frame(0x88, b"\x00\x00")])
        with self.assertRaises(RuntimeError):
            RtkBridge(host).write(b"x")


if __name__ == "__main__":
    unittest.main()
