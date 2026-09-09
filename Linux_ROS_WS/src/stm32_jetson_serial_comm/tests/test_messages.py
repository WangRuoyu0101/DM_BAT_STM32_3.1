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
    ErrorResponse,
    FanControlResult,
    GpioStatus,
    RgbSetResult,
    RgbStatus,
    SlaveStatus,
    UltrasonicStatus,
    decode_board_io_status,
    decode_error_response,
    decode_fan_control_response,
    decode_gpio_status,
    decode_rgb_set_response,
    decode_rgb_status,
    decode_slave_status,
    decode_ultrasonic_status,
    decode_cs1237_channel_response,
    decode_cs1237_status,
)


class MessageDecodeTest(unittest.TestCase):
    def test_decodes_rgb_payloads(self):
        self.assertEqual(
            decode_rgb_set_response(bytes.fromhex("20 00")),
            RgbSetResult(seq=0x20, result=0),
        )
        self.assertEqual(
            decode_rgb_status(bytes.fromhex("21 FF B7 C5 19 02 01")),
            RgbStatus(0x21, 255, 183, 197, 25, 2, True),
        )

    def test_decodes_fan_control_and_board_io_payloads(self):
        self.assertEqual(
            decode_fan_control_response(bytes.fromhex("21 03 00")),
            FanControlResult(seq=0x21, level=3, result=0),
        )
        self.assertEqual(
            decode_board_io_status(bytes.fromhex("22 02 B8 0B 70 17 03")),
            BoardIOStatus(seq=0x22, fan_level=2, fan1_rpm=3000, fan2_rpm=6000, key_bitmap=3),
        )

    def test_decodes_cs1237_payloads(self):
        self.assertEqual(
            decode_cs1237_status(bytes.fromhex("10 C0 7C 3E 00 02 01 00")),
            CS1237Status(seq=0x10, raw_adc=4095168, channel=2, valid=True, error=0),
        )
        self.assertEqual(
            decode_cs1237_channel_response(bytes.fromhex("11 02 00")),
            CS1237ChannelResult(seq=0x11, channel=2, result=0),
        )

    def test_decodes_slave_status_response_payload(self):
        payload = bytes.fromhex("10 39 30 00 00 00 03")

        status = decode_slave_status(payload)

        self.assertEqual(status, SlaveStatus(seq=0x10, tick=12345, status=0, gpio_bitmap=0x03))

    def test_decodes_extended_slave_status_diagnostics(self):
        payload = bytes.fromhex("10 39 30 00 00 00 03") + b"".join(
            value.to_bytes(4, "little") for value in (1, 2, 3, 4, 5)
        ) + (700).to_bytes(2, "little")

        self.assertEqual(
            decode_slave_status(payload),
            SlaveStatus(
                seq=0x10,
                tick=12345,
                status=0,
                gpio_bitmap=0x03,
                usb_busy_retries=1,
                usb_queue_overflows=2,
                usb_tx_failures=3,
                rtk_overflow_bytes=4,
                rtk_uart_errors=5,
                rtk_rx_high_water=700,
                extended=True,
            ),
        )

    def test_decodes_gpio_status_payload(self):
        self.assertEqual(
            decode_gpio_status(bytes.fromhex("12 21")),
            GpioStatus(seq=0x12, gpio_bitmap=0x21),
        )

    def test_decodes_ultrasonic_status_payload(self):
        payload = bytes.fromhex("13 E8 03 D0 07 FD FF 03 30")

        status = decode_ultrasonic_status(payload)

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

    def test_decodes_error_response_payload(self):
        self.assertEqual(
            decode_error_response(bytes.fromhex("11 02 03")),
            ErrorResponse(seq=0x11, source_frame_id=0x02, error_code=0x03),
        )

    def test_rejects_wrong_payload_lengths(self):
        with self.assertRaises(ValueError):
            decode_slave_status(b"\x10")
        with self.assertRaises(ValueError):
            decode_gpio_status(b"\x12")
        with self.assertRaises(ValueError):
            decode_ultrasonic_status(b"\x13")
        with self.assertRaises(ValueError):
            decode_error_response(b"\x11")
        with self.assertRaises(ValueError):
            decode_rgb_set_response(b"\x20")
        with self.assertRaises(ValueError):
            decode_rgb_status(b"\x21")

    def test_rejects_out_of_contract_rgb_response_values(self):
        for payload in (
            bytes.fromhex("20 03"),
            bytes.fromhex("21 01 02 03 65 02 01"),
            bytes.fromhex("21 01 02 03 19 05 01"),
            bytes.fromhex("21 01 02 03 19 02 02"),
        ):
            with self.subTest(payload=payload):
                decoder = decode_rgb_set_response if len(payload) == 2 else decode_rgb_status
                with self.assertRaises(ValueError):
                    decoder(payload)


if __name__ == "__main__":
    unittest.main()
