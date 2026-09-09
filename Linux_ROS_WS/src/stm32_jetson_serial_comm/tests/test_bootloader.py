#!/usr/bin/env python3
import importlib
import pathlib
import sys
import unittest
from unittest import mock

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from stm32_jetson_serial_comm.protocol import pack_frame
from stm32_jetson_serial_comm.protocol import Frame
from stm32_jetson_serial_comm.serial_host import SerialTimeoutError
from stm32_jetson_serial_comm.bootloader import (
    BOOTLOADER_WRITE_DATA_MAX,
    BootloaderAck,
    BootloaderClient,
    BootloaderError,
    BootloaderInfo,
    BootloaderStatus,
    BootloaderProtocolError,
    build_start_payload,
    build_write_payload,
    crc32,
    split_write_chunks,
)
from stm32_jetson_serial_comm.bootloader_cli import (
    APP_REQUEST_DEFAULT_BAUDRATE,
    BOOTLOADER_DEFAULT_BAUDRATE,
    build_arg_parser,
)


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


def ack(seq, command, status=0):
    return pack_frame(0x91, bytes([seq, command, status]))


class BootloaderProtocolTest(unittest.TestCase):
    def test_bootloader_cli_uses_separate_app_and_bootloader_baudrates(self):
        parser = build_arg_parser()

        args = parser.parse_args(["firmware.bin"])

        self.assertEqual(BOOTLOADER_DEFAULT_BAUDRATE, 460800)
        self.assertEqual(APP_REQUEST_DEFAULT_BAUDRATE, 115200)
        self.assertEqual(args.baudrate, 460800)
        self.assertEqual(args.app_baudrate, 115200)
        self.assertEqual(args.device, "/dev/ttyACM0")
        self.assertEqual(args.timeout, 3.0)
        self.assertEqual(args.reset_wait, 1.5)

    def test_bootloader_default_device_can_be_overridden_by_environment(self):
        import stm32_jetson_serial_comm.bootloader_cli as bootloader_cli

        with mock.patch.dict("os.environ", {"STM32_BOOTLOADER_DEVICE": "/dev/ttyTHS0"}):
            reloaded = importlib.reload(bootloader_cli)
            self.assertEqual(reloaded.build_arg_parser().parse_args(["firmware.bin"]).device, "/dev/ttyTHS0")

        importlib.reload(bootloader_cli)

    def test_crc32_matches_stm32_bootloader_algorithm(self):
        self.assertEqual(crc32(b"123456789"), 0xCBF43926)

    def test_build_start_payload_uses_little_endian_size_and_crc(self):
        payload = build_start_payload(seq=0x22, image=b"ABC")

        self.assertEqual(payload, bytes.fromhex("22 03 00 00 00 48 03 83 A3"))

    def test_split_write_chunks_uses_bootloader_max_data_size(self):
        chunks = list(split_write_chunks(bytes(range(256))))

        self.assertEqual([offset for offset, _data in chunks], [0, 245])
        self.assertEqual([len(data) for _offset, data in chunks], [245, 11])
        self.assertEqual(BOOTLOADER_WRITE_DATA_MAX, 245)

    def test_build_write_payload_contains_seq_offset_and_data(self):
        payload = build_write_payload(seq=0x23, offset=0x11223344, data=b"\xAA\xBB")

        self.assertEqual(payload, bytes.fromhex("23 44 33 22 11 AA BB"))

    def test_decode_bootloader_responses(self):
        client = BootloaderClient(FakeDriver())

        self.assertEqual(
            client.decode_info(
                bytes.fromhex("10 00 80 00 08 00 80 07 00 F5 00 00 00 00 00 01 00")
            ),
            BootloaderInfo(
                seq=0x10,
                app_base=0x08008000,
                app_size=0x00078000,
                write_data_max=245,
                version=0x00010000,
            ),
        )
        self.assertEqual(client.decode_ack(bytes.fromhex("11 12 00")), BootloaderAck(0x11, 0x12, 0))
        self.assertEqual(
            client.decode_error(bytes.fromhex("12 13 04")),
            BootloaderError(seq=0x12, command=0x13, error_code=0x04),
        )
        self.assertEqual(
            client.decode_status(bytes.fromhex("01 00 07 00 F5 00 00 00")),
            BootloaderStatus(state=1, app_valid=False, last_error=7, received_bytes=245),
        )

    def test_decode_status_rejects_malformed_payload(self):
        client = BootloaderClient(FakeDriver())

        with self.assertRaisesRegex(BootloaderProtocolError, "STATUS payload length"):
            client.decode_status(b"\x00" * 7)
        with self.assertRaisesRegex(BootloaderProtocolError, "invalid STATUS payload"):
            client.decode_status(bytes.fromhex("04 00 00 00 00 00 00 00"))


class BootloaderClientTest(unittest.TestCase):
    def test_status_and_ack_in_same_read_are_dispatched_without_losing_ack(self):
        statuses = []
        driver = FakeDriver([
            pack_frame(0x92, bytes.fromhex("01 00 00 00 F5 00 00 00")) + ack(0x11, 0x11)
        ])
        client = BootloaderClient(driver, status_callback=statuses.append)

        result = client._request_ack(0x11, 0x11, b"\x11", 0.05, 0.01)

        self.assertEqual(result, BootloaderAck(seq=0x11, command=0x11, status=0))
        self.assertEqual(statuses, [BootloaderStatus(1, False, 0, 245)])

    def test_hello_skips_interleaved_status(self):
        statuses = []
        driver = FakeDriver([
            pack_frame(0x92, bytes.fromhex("00 00 00 00 00 00 00 00"))
            + pack_frame(0x90, bytes.fromhex("10 00 80 00 08 00 80 05 00 F5 00 00 00 00 00 02 00"))
        ])
        client = BootloaderClient(driver, status_callback=statuses.append)

        info = client.hello(seq=0x10, timeout_seconds=0.05, poll_interval=0.01)

        self.assertEqual(info.app_size, 352 * 1024)
        self.assertEqual(info.version, 0x00020000)
        self.assertEqual(statuses, [BootloaderStatus(0, False, 0, 0)])

    def test_program_image_rejects_image_larger_than_application_area_before_start(self):
        class SmallApplicationClient(BootloaderClient):
            def __init__(self):
                self.ack_calls = []

            def _request_info(self, seq, timeout_seconds, poll_interval):
                return BootloaderInfo(seq, 0x08008000, 4, 245, 0x00010000)

            def _request_ack(self, *args):
                self.ack_calls.append(args)

        client = SmallApplicationClient()

        with self.assertRaisesRegex(ValueError, "image size 5 exceeds application area 4"):
            client.program_image(b"12345")
        self.assertEqual(client.ack_calls, [])

    def test_request_bootloader_from_running_app_sends_password_payload(self):
        driver = FakeDriver([pack_frame(0x85, bytes.fromhex("44 00"))])
        client = BootloaderClient(driver)

        client.request_app_bootloader(seq=0x44, timeout_seconds=0.05, poll_interval=0.01)

        self.assertEqual(driver.writes, [pack_frame(0x05, b"\x44wb88")])

    def test_request_bootloader_rejects_error_response(self):
        driver = FakeDriver([pack_frame(0xE1, bytes.fromhex("44 05 04"))])
        client = BootloaderClient(driver)

        with self.assertRaises(BootloaderProtocolError):
            client.request_app_bootloader(seq=0x44, timeout_seconds=0.05, poll_interval=0.01)

    def test_request_bootloader_accepts_bootloader_error_as_already_active(self):
        driver = FakeDriver([pack_frame(0xE2, bytes.fromhex("44 05 01"))])
        client = BootloaderClient(driver)

        client.request_app_bootloader(seq=0x44, timeout_seconds=0.05, poll_interval=0.01)

        self.assertEqual(driver.writes, [pack_frame(0x05, b"\x44wb88")])

    def test_program_image_runs_hello_start_erase_write_verify_and_jump(self):
        image = bytes(range(40))
        driver = FakeDriver(
            [
                pack_frame(0x90, bytes.fromhex("10 00 80 00 08 00 80 07 00 F5 00 00 00 00 00 01 00")),
                ack(0x11, 0x11),
                ack(0x12, 0x12),
                ack(0x13, 0x13),
                ack(0x14, 0x14),
                ack(0x15, 0x15),
            ]
        )
        client = BootloaderClient(driver)

        info = client.program_image(
            image,
            seq_start=0x10,
            jump=True,
            timeout_seconds=0.05,
            poll_interval=0.01,
        )

        self.assertEqual(info.write_data_max, 245)
        self.assertEqual(
            driver.writes,
            [
                pack_frame(0x10, b"\x10"),
                pack_frame(0x11, build_start_payload(0x11, image)),
                pack_frame(0x12, b"\x12"),
                pack_frame(0x13, build_write_payload(0x13, 0, image)),
                pack_frame(0x14, b"\x14"),
                pack_frame(0x15, b"\x15"),
            ],
        )

    def test_bootloader_hello_is_retried_during_usb_reenumeration(self):
        class RetryHelloClient(BootloaderClient):
            def __init__(self):
                self.calls = 0

            def _send_and_read(self, frame_id, payload, timeout_seconds, poll_interval):
                self.calls += 1
                if self.calls == 1:
                    raise SerialTimeoutError("first HELLO missed during USB setup")
                return Frame(
                    0x90,
                    bytes.fromhex("10 00 80 00 08 00 80 07 00 F5 00 00 00 00 00 01 00"),
                )

        client = RetryHelloClient()

        info = client._request_info(seq=0x10, timeout_seconds=1.0, poll_interval=0.01)

        self.assertEqual(client.calls, 2)
        self.assertEqual(info.app_base, 0x08008000)

    def test_program_image_uses_dedicated_erase_timeout(self):
        class SpyBootloaderClient(BootloaderClient):
            def __init__(self):
                self.ack_calls = []

            def _request_info(self, seq, timeout_seconds, poll_interval):
                return BootloaderInfo(
                    seq=seq,
                    app_base=0x08008000,
                    app_size=0x00078000,
                    write_data_max=245,
                    version=0x00010000,
                )

            def _request_ack(self, frame_id, seq, payload, timeout_seconds, poll_interval):
                self.ack_calls.append((frame_id, timeout_seconds))
                return BootloaderAck(seq=seq, command=frame_id, status=0)

        client = SpyBootloaderClient()

        client.program_image(
            b"\x01\x02",
            timeout_seconds=0.05,
            erase_timeout_seconds=12.0,
            jump=False,
        )

        self.assertIn((0x12, 12.0), client.ack_calls)
        self.assertIn((0x11, 0.05), client.ack_calls)
        self.assertIn((0x13, 0.05), client.ack_calls)
        self.assertIn((0x14, 0.05), client.ack_calls)


if __name__ == "__main__":
    unittest.main()
