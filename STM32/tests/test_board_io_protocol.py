from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BoardIOProtocolTest(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_protocol_declares_fan_control_and_board_io_frames(self):
        header = self.read("Core/Inc/app_comm_protocol.h")
        source = self.read("Core/Src/app_comm_protocol.c")

        self.assertIn("APP_COMM_FRAME_ID_FAN_CONTROL_REQUEST 0x0AU", header)
        self.assertIn("APP_COMM_FRAME_ID_BOARD_IO_QUERY 0x0BU", header)
        self.assertIn("APP_COMM_FRAME_ID_FAN_CONTROL_RESPONSE 0x8AU", header)
        self.assertIn("APP_COMM_FRAME_ID_BOARD_IO_RESPONSE 0x8BU", header)
        self.assertIn("App_CommFanControl", header)
        self.assertIn("App_CommBoardIOQuery", header)
        self.assertIn("App_CommProtocol_DecodeFanControlRequest", source)
        self.assertIn("App_CommProtocol_DecodeBoardIOQuery", source)

    def test_slave_applies_level_and_returns_seven_byte_snapshot(self):
        header = self.read("Core/Inc/app_uart5_slave.h")
        source = self.read("Core/Src/app_uart5_slave.c")

        self.assertIn('#include "app_board_io.h"', header)
        self.assertIn("App_BoardIO_SetFanLevel(control.level)", source)
        self.assertIn("APP_COMM_FRAME_ID_FAN_CONTROL_RESPONSE", source)
        self.assertIn("App_BoardIO_GetSnapshot(&snapshot)", source)
        self.assertIn("uint8_t payload[7]", source)
        self.assertIn("payload[6] = snapshot.key_bitmap", source)
        self.assertIn("APP_COMM_FRAME_ID_BOARD_IO_RESPONSE", source)


if __name__ == "__main__":
    unittest.main()
