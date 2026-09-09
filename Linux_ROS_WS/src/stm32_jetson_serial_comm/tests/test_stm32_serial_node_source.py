#!/usr/bin/env python3
import pathlib
import unittest


PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]


class Stm32SerialNodeSourceTest(unittest.TestCase):
    def test_node_defines_gpio_setbool_services_and_serial_lock(self):
        source = (PACKAGE_ROOT / "stm32_jetson_serial_comm/stm32_serial_node.py").read_text()

        self.assertIn("from std_srvs.srv import SetBool", source)
        self.assertIn('import os', source)
        self.assertIn('declare_parameter("device", os.environ.get("STM32_SERIAL_DEVICE", "/dev/ttyACM0"))', source)
        self.assertIn("threading.Lock", source)
        self.assertIn("status_rate_hz", source)
        self.assertIn("gpio_status_rate_hz", source)
        self.assertIn("ultrasonic_rate_hz", source)
        self.assertIn("_poll_status_once", source)
        self.assertIn("_poll_gpio_once", source)
        self.assertIn("_poll_ultrasonic_once", source)
        self.assertIn('declare_parameter("cs1237_rate_hz", 10.0)', source)
        self.assertIn('"/stm32/cs1237_raw"', source)
        self.assertIn('"/stm32/cs1237_text"', source)
        self.assertIn("_poll_cs1237_once", source)
        self.assertIn('declare_parameter("board_io_rate_hz", 2.0)', source)
        self.assertIn('"/stm32/fan_rpm"', source)
        self.assertIn('"/stm32/fan_level"', source)
        self.assertIn('"/stm32/key_bitmap"', source)
        self.assertIn('"/stm32/board_io_text"', source)
        self.assertIn("_poll_board_io_once", source)
        self.assertIn("_try_poll_lock", source)
        self.assertIn("acquire(blocking=False)", source)
        for service_name in [
            "/stm32/gpio/flash_ctr/set",
            "/stm32/gpio/led/set",
            "/stm32/gpio/bee/set",
            "/stm32/gpio/motor/set",
            "/stm32/gpio/flash/set",
            "/stm32/gpio/sound/set",
        ]:
            self.assertIn(service_name, source)
        self.assertIn("create_service(", source)
        self.assertIn("SetBool,", source)
        self.assertIn("control_gpio(", source)


if __name__ == "__main__":
    unittest.main()
