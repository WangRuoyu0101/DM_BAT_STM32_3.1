from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UltrasonicProtocolTests(unittest.TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_protocol_module_defines_controlled_sensor_frame(self):
        header = self.read("Core/Inc/app_ultrasonic_protocol.h")
        source = self.read("Core/Src/app_ultrasonic_protocol.c")
        makefile = self.read("Makefile")

        self.assertIn("#ifndef APP_ULTRASONIC_PROTOCOL_H", header)
        self.assertIn("#define APP_ULTRASONIC_TRIGGER_BYTE 0x55U", header)
        self.assertIn("#define APP_ULTRASONIC_FRAME_HEADER 0xFFU", header)
        self.assertIn("#define APP_ULTRASONIC_FRAME_SIZE 4U", header)
        self.assertIn("#define APP_ULTRASONIC_INTERFERENCE_VALUE 0xFFFEU", header)
        self.assertIn("#define APP_ULTRASONIC_NO_TARGET_VALUE 0xFFFDU", header)
        self.assertIn("APP_ULTRASONIC_PARSE_INTERFERENCE", header)
        self.assertIn("APP_ULTRASONIC_PARSE_NO_TARGET", header)
        self.assertIn("APP_ULTRASONIC_PARSE_CHECKSUM_ERROR", header)
        self.assertIn("App_UltrasonicProtocol_ParseByte", header)
        self.assertIn("Core/Src/app_ultrasonic_protocol.c", makefile)
        self.assertIn('#include "app_ultrasonic_protocol.h"', source)

    def test_protocol_parser_checks_header_checksum_and_special_values(self):
        source = self.read("Core/Src/app_ultrasonic_protocol.c")

        self.assertIn("byte != APP_ULTRASONIC_FRAME_HEADER", source)
        self.assertIn("parser->checksum = APP_ULTRASONIC_FRAME_HEADER;", source)
        self.assertIn("parser->distance_mm = (uint16_t)(((uint16_t)parser->data_high << 8U) | parser->data_low);", source)
        self.assertIn("expected_checksum = (uint8_t)(APP_ULTRASONIC_FRAME_HEADER + parser->data_high + parser->data_low);", source)
        self.assertIn("parser->distance_mm == APP_ULTRASONIC_INTERFERENCE_VALUE", source)
        self.assertIn("parser->distance_mm == APP_ULTRASONIC_NO_TARGET_VALUE", source)
        self.assertIn("*distance_mm = parser->distance_mm;", source)


if __name__ == "__main__":
    unittest.main()
