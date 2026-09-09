#!/usr/bin/env python3
import pathlib
import sys
import unittest

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from stm32_jetson_serial_comm.messages import (
    BoardIOStatus,
    CS1237ChannelResult,
    CS1237Status,
    FanControlResult,
    GpioControlResult,
    GpioStatus,
    RgbSetResult,
    RgbStatus,
    SlaveStatus,
    UltrasonicStatus,
)
from stm32_jetson_serial_comm.protocol import Frame, pack_frame
from stm32_jetson_serial_comm.serial_host import SerialHost, SerialTimeoutError


class FakeDriver:
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


class SerialHostTest(unittest.TestCase):
    def test_set_rgb_and_query_rgb(self):
        driver = FakeDriver([
            pack_frame(0x8C, bytes.fromhex("20 00")),
            pack_frame(0x8D, bytes.fromhex("21 FF B7 C5 19 02 01")),
        ])
        host = SerialHost(driver)

        result = host.set_rgb(255, 183, 197, 25, 2, seq=0x20, timeout_seconds=0.05)
        status = host.query_rgb(seq=0x21, timeout_seconds=0.05)

        self.assertEqual(result, RgbSetResult(0x20, 0))
        self.assertEqual(status, RgbStatus(0x21, 255, 183, 197, 25, 2, True))
        self.assertEqual(driver.writes, [
            pack_frame(0x0C, bytes.fromhex("20 FF B7 C5 19 02")),
            pack_frame(0x0D, b"\x21"),
        ])

    def test_rgb_rejects_out_of_range_values_before_writing(self):
        invalid_arguments = (
            (-1, 0, 0, 0, 0, 0),
            (0, 256, 0, 0, 0, 0),
            (0, 0, 256, 0, 0, 0),
            (0, 0, 0, 101, 0, 0),
            (0, 0, 0, 0, 5, 0),
            (0, 0, 0, 0, 0, 256),
        )
        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                driver = FakeDriver()
                with self.assertRaises(ValueError):
                    SerialHost(driver).set_rgb(*arguments)
                self.assertEqual(driver.writes, [])

        driver = FakeDriver()
        with self.assertRaises(ValueError):
            SerialHost(driver).query_rgb(seq=-1)
        self.assertEqual(driver.writes, [])

    def test_rgb_ignores_late_same_frame_response_with_old_sequence(self):
        driver = FakeDriver([
            pack_frame(0x8C, bytes.fromhex("20 02")),
            pack_frame(0x8C, bytes.fromhex("21 00")),
            pack_frame(0x8D, bytes.fromhex("21 01 02 03 19 02 00")),
            pack_frame(0x8D, bytes.fromhex("22 04 05 06 32 04 01")),
        ])
        host = SerialHost(driver)

        result = host.set_rgb(1, 2, 3, 25, 2, seq=0x21, timeout_seconds=0.05)
        status = host.query_rgb(seq=0x22, timeout_seconds=0.05)

        self.assertEqual(result, RgbSetResult(0x21, 0))
        self.assertEqual(status, RgbStatus(0x22, 4, 5, 6, 50, 4, True))

    def test_rgb_mismatched_sequence_cannot_satisfy_request(self):
        driver = FakeDriver([pack_frame(0x8C, bytes.fromhex("20 00"))])

        with self.assertRaises(SerialTimeoutError):
            SerialHost(driver).set_rgb(
                1, 2, 3, 25, 2, seq=0x21, timeout_seconds=0.02, poll_interval=0.001
            )

    def test_fan_control_and_board_io_query(self):
        driver = FakeDriver([
            pack_frame(0x8A, bytes.fromhex("21 03 00")),
            pack_frame(0x8B, bytes.fromhex("22 03 B8 0B 70 17 03")),
        ])
        host = SerialHost(driver)

        result = host.set_fan_level(3, seq=0x21, timeout_seconds=0.05, poll_interval=0.01)
        status = host.query_board_io(seq=0x22, timeout_seconds=0.05, poll_interval=0.01)

        self.assertEqual(result, FanControlResult(0x21, 3, 0))
        self.assertEqual(status, BoardIOStatus(0x22, 3, 3000, 6000, 3))
        self.assertEqual(driver.writes, [
            pack_frame(0x0A, bytes.fromhex("21 03")),
            pack_frame(0x0B, b"\x22"),
        ])

    def test_cs1237_query_and_channel_selection(self):
        driver = FakeDriver([
            pack_frame(0x86, bytes.fromhex("10 C0 7C 3E 00 02 01 00")),
            pack_frame(0x87, bytes.fromhex("11 02 00")),
        ])
        host = SerialHost(driver)

        status = host.query_cs1237(seq=0x10, timeout_seconds=0.05, poll_interval=0.01)
        result = host.set_cs1237_channel(2, seq=0x11, timeout_seconds=0.05, poll_interval=0.01)

        self.assertEqual(status, CS1237Status(0x10, 4095168, 2, True, 0))
        self.assertEqual(result, CS1237ChannelResult(0x11, 2, 0))
        self.assertEqual(driver.writes, [
            pack_frame(0x06, b"\x10"),
            pack_frame(0x07, b"\x11\x02"),
        ])

    def test_send_frame_packs_command_and_payload(self):
        driver = FakeDriver()
        host = SerialHost(driver)

        host.send_frame(0x01, b"\x10\x20")

        self.assertEqual(driver.writes, [pack_frame(0x01, b"\x10\x20")])

    def test_read_frame_returns_first_valid_frame(self):
        driver = FakeDriver([pack_frame(0x02, b"\x33")])
        host = SerialHost(driver)

        frame = host.read_frame(timeout_seconds=0.05, poll_interval=0.01)

        self.assertEqual(frame, Frame(frame_id=0x02, payload=b"\x33"))

    def test_read_frame_preserves_additional_frames_from_same_chunk(self):
        driver = FakeDriver([pack_frame(0x02, b"\x33") + pack_frame(0x03, b"\x44")])
        host = SerialHost(driver)

        first = host.read_frame(timeout_seconds=0.05, poll_interval=0.01)
        second = host.read_frame(timeout_seconds=0.05, poll_interval=0.01)

        self.assertEqual(first, Frame(frame_id=0x02, payload=b"\x33"))
        self.assertEqual(second, Frame(frame_id=0x03, payload=b"\x44"))

    def test_read_frame_handles_partial_chunks(self):
        raw = pack_frame(0x03, b"\xAA\x55")
        driver = FakeDriver([raw[:3], raw[3:]])
        host = SerialHost(driver)

        frame = host.read_frame(timeout_seconds=0.05, poll_interval=0.01)

        self.assertEqual(frame, Frame(frame_id=0x03, payload=b"\xAA\x55"))

    def test_read_frame_raises_timeout_when_no_complete_frame_arrives(self):
        driver = FakeDriver([b"\xAA"])
        host = SerialHost(driver)

        with self.assertRaises(SerialTimeoutError):
            host.read_frame(timeout_seconds=0.02, poll_interval=0.01)

    def test_request_sends_frame_then_returns_response(self):
        driver = FakeDriver([pack_frame(0x81, b"\x00")])
        host = SerialHost(driver)

        response = host.request(0x01, b"\x10", timeout_seconds=0.05, poll_interval=0.01)

        self.assertEqual(driver.writes, [pack_frame(0x01, b"\x10")])
        self.assertEqual(response, Frame(frame_id=0x81, payload=b"\x00"))

    def test_query_status_sends_seq_and_decodes_status_response(self):
        driver = FakeDriver([pack_frame(0x81, bytes.fromhex("10 39 30 00 00 00 03"))])
        host = SerialHost(driver)

        status = host.query_status(seq=0x10, timeout_seconds=0.05, poll_interval=0.01)

        self.assertEqual(driver.writes, [pack_frame(0x01, b"\x10")])
        self.assertEqual(status, SlaveStatus(seq=0x10, tick=12345, status=0, gpio_bitmap=0x03))

    def test_query_gpio_sends_seq_and_decodes_gpio_status(self):
        driver = FakeDriver([pack_frame(0x83, bytes.fromhex("12 21"))])
        host = SerialHost(driver)

        status = host.query_gpio(seq=0x12, timeout_seconds=0.05, poll_interval=0.01)

        self.assertEqual(driver.writes, [pack_frame(0x03, b"\x12")])
        self.assertEqual(status, GpioStatus(seq=0x12, gpio_bitmap=0x21))

    def test_control_gpio_sends_channel_level_and_decodes_result(self):
        driver = FakeDriver([pack_frame(0x82, bytes.fromhex("20 02 00"))])
        host = SerialHost(driver)

        result = host.control_gpio(
            channel_id=0x02,
            level=1,
            seq=0x20,
            timeout_seconds=0.05,
            poll_interval=0.01,
        )

        self.assertEqual(driver.writes, [pack_frame(0x02, bytes.fromhex("20 02 01"))])
        self.assertEqual(result, GpioControlResult(seq=0x20, channel_id=0x02, result=0x00))

    def test_query_ultrasonic_sends_seq_and_decodes_distances(self):
        driver = FakeDriver([pack_frame(0x84, bytes.fromhex("13 E8 03 D0 07 FD FF 03 30"))])
        host = SerialHost(driver)

        status = host.query_ultrasonic(seq=0x13, timeout_seconds=0.05, poll_interval=0.01)

        self.assertEqual(driver.writes, [pack_frame(0x04, b"\x13")])
        self.assertEqual(
            status,
            UltrasonicStatus(
                seq=0x13,
                front_mm=1000,
                left_mm=2000,
                right_mm=0xFFFD,
                valid_bitmap=0x03,
                error_bitmap=0x30,
            ),
        )


if __name__ == "__main__":
    unittest.main()
