from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RtkProtocolTest(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_protocol_defines_binary_rtk_write_and_read_frames(self):
        header = self.read("Core/Inc/app_comm_protocol.h")
        source = self.read("Core/Src/app_comm_protocol.c")
        slave = self.read("Core/Src/app_uart5_slave.c")

        self.assertIn("APP_COMM_FRAME_ID_RTK_WRITE_REQUEST 0x08U", header)
        self.assertIn("APP_COMM_FRAME_ID_RTK_READ_REQUEST 0x09U", header)
        self.assertIn("APP_COMM_FRAME_ID_RTK_WRITE_RESPONSE 0x88U", header)
        self.assertIn("APP_COMM_FRAME_ID_RTK_READ_RESPONSE 0x89U", header)
        self.assertIn("App_CommProtocol_DecodeRtkWriteRequest", source)
        self.assertIn("App_CommProtocol_DecodeRtkReadRequest", source)
        self.assertIn("App_RtkBridge_Write", slave)
        self.assertIn("App_RtkBridge_Read", slave)
        self.assertIn("APP_COMM_FRAME_ID_RTK_WRITE_RESPONSE", slave)
        self.assertIn("APP_COMM_FRAME_ID_RTK_READ_RESPONSE", slave)
        self.assertIn(
            "APP_COMM_RTK_READ_DATA_MAX (APP_COMM_MAX_PAYLOAD_SIZE - 2U)",
            header,
        )


if __name__ == "__main__":
    unittest.main()
