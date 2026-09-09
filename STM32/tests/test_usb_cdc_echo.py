from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UsbCdcProtocolTests(unittest.TestCase):
    def read_source(self):
        return (ROOT / "USB_DEVICE/App/usbd_cdc_if.c").read_text(encoding="utf-8")

    def test_cdc_receive_callback_feeds_protocol_bytes(self):
        source = self.read_source()

        self.assertIn('#include "app_uart5_slave.h"', source)
        self.assertIn("App_Uart5Slave_HandleUsbData(Buf, *Len);", source)
        self.assertNotIn("CDC_Transmit_FS(UserTxBufferFS, echo_len);", source)

    def test_cdc_control_handles_linux_line_coding_requests(self):
        source = self.read_source()

        self.assertIn("static uint8_t line_coding[7]", source)
        self.assertIn("memcpy(line_coding, pbuf, sizeof(line_coding));", source)
        self.assertIn("memcpy(pbuf, line_coding, sizeof(line_coding));", source)


if __name__ == "__main__":
    unittest.main()
