from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CS1237ProtocolTest(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_protocol_defines_query_and_channel_selection(self):
        header = self.read("Core/Inc/app_comm_protocol.h")
        source = self.read("Core/Src/app_comm_protocol.c")
        slave_h = self.read("Core/Inc/app_uart5_slave.h")
        slave = self.read("Core/Src/app_uart5_slave.c")

        self.assertIn("APP_COMM_FRAME_ID_CS1237_QUERY 0x06U", header)
        self.assertIn("APP_COMM_FRAME_ID_CS1237_CHANNEL_REQUEST 0x07U", header)
        self.assertIn("APP_COMM_FRAME_ID_CS1237_RESPONSE 0x86U", header)
        self.assertIn("APP_COMM_FRAME_ID_CS1237_CHANNEL_RESPONSE 0x87U", header)
        self.assertIn("App_CommProtocol_DecodeCS1237Query", source)
        self.assertIn("App_CommProtocol_DecodeCS1237ChannelRequest", source)
        self.assertIn('#include "app_cs1237.h"', slave_h)
        self.assertIn("App_CS1237_GetSnapshot", slave)
        self.assertIn("App_CS1237_SetChannel", slave)
        self.assertIn("APP_COMM_FRAME_ID_CS1237_RESPONSE", slave)
        self.assertIn("APP_COMM_FRAME_ID_CS1237_CHANNEL_RESPONSE", slave)
        self.assertIn("raw_adc >> 24U", slave)


if __name__ == "__main__":
    unittest.main()
