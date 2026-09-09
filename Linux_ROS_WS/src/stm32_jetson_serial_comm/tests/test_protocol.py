#!/usr/bin/env python3
import pathlib
import sys
import unittest

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from stm32_jetson_serial_comm.protocol import Frame, FrameParser, ProtocolError, crc8, pack_frame


class ProtocolTest(unittest.TestCase):
    def test_crc8_uses_stm32_polynomial(self):
        self.assertEqual(crc8(bytes.fromhex("01 01 10")), 0x0E)
        self.assertEqual(crc8(bytes.fromhex("04 01 13")), 0xC7)

    def test_pack_frame_builds_stm32_uart5_frame(self):
        self.assertEqual(
            pack_frame(0x01, b"\x10"),
            bytes.fromhex("AA 55 01 01 10 0E"),
        )

    def test_pack_frame_rejects_invalid_frame_id(self):
        with self.assertRaises(ValueError):
            pack_frame(0x100, b"")

    def test_pack_frame_rejects_payload_longer_than_250_bytes(self):
        pack_frame(0x01, bytes(250))

        with self.assertRaises(ValueError):
            pack_frame(0x01, bytes(251))

    def test_parser_emits_frame_from_single_complete_packet(self):
        parser = FrameParser()

        frames = parser.feed(bytes.fromhex("AA 55 01 01 10 0E"))

        self.assertEqual(frames, [Frame(frame_id=0x01, payload=b"\x10")])

    def test_parser_handles_multiple_frames_in_one_chunk(self):
        parser = FrameParser()
        chunk = pack_frame(0x01, b"\x10") + pack_frame(0x03, b"\x12")

        frames = parser.feed(chunk)

        self.assertEqual(
            frames,
            [
                Frame(frame_id=0x01, payload=b"\x10"),
                Frame(frame_id=0x03, payload=b"\x12"),
            ],
        )

    def test_parser_keeps_partial_frame_until_more_bytes_arrive(self):
        parser = FrameParser()
        frame = pack_frame(0x04, b"\x13")

        self.assertEqual(parser.feed(frame[:4]), [])
        self.assertEqual(parser.feed(frame[4:]), [Frame(frame_id=0x04, payload=b"\x13")])

    def test_parser_resynchronizes_after_garbage_bytes(self):
        parser = FrameParser()
        frame = pack_frame(0x04, b"\x13")

        frames = parser.feed(b"\x00\xFF\xAA\x00" + frame)

        self.assertEqual(frames, [Frame(frame_id=0x04, payload=b"\x13")])

    def test_parser_drops_bad_crc_frame_and_continues(self):
        parser = FrameParser()
        bad = bytearray(pack_frame(0x05, b"\x99"))
        bad[-1] ^= 0xFF
        good = pack_frame(0x06, b"\x88")

        frames = parser.feed(bytes(bad) + good)

        self.assertEqual(frames, [Frame(frame_id=0x06, payload=b"\x88")])

    def test_unpack_rejects_bad_crc_when_requested_directly(self):
        frame = bytearray(pack_frame(0x07, b"\x01"))
        frame[-1] ^= 0xFF

        with self.assertRaises(ProtocolError):
            FrameParser.unpack(bytes(frame))


if __name__ == "__main__":
    unittest.main()
