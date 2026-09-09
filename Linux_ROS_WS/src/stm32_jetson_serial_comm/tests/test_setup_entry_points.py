#!/usr/bin/env python3
import ast
import pathlib
import unittest


PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]


class SetupEntryPointsTest(unittest.TestCase):
    def _setup_call(self):
        setup_tree = ast.parse((PACKAGE_ROOT / "setup.py").read_text())
        return next(
            node
            for node in ast.walk(setup_tree)
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "setup"
        )

    def test_stm32_serial_node_console_script_is_registered(self):
        setup_call = self._setup_call()
        entry_points_keyword = next(
            keyword for keyword in setup_call.keywords if keyword.arg == "entry_points"
        )
        entry_points = ast.literal_eval(entry_points_keyword.value)

        self.assertIn(
            "stm32_serial_node = stm32_jetson_serial_comm.stm32_serial_node:main",
            entry_points["console_scripts"],
        )
        self.assertIn(
            "stm32_bootloader = stm32_jetson_serial_comm.bootloader_cli:main",
            entry_points["console_scripts"],
        )
        self.assertIn(
            "stm32_gpio = stm32_jetson_serial_comm.gpio_cli:main",
            entry_points["console_scripts"],
        )
        self.assertIn(
            "stm32_fan = stm32_jetson_serial_comm.fan_cli:main",
            entry_points["console_scripts"],
        )

    def test_launch_file_is_installed(self):
        setup_source = (PACKAGE_ROOT / "setup.py").read_text()
        launch_source = (PACKAGE_ROOT / "launch/stm32_serial.launch.py").read_text()

        self.assertIn('"share/" + package_name + "/launch"', setup_source)
        self.assertIn('"launch/stm32_serial.launch.py"', setup_source)
        self.assertTrue((PACKAGE_ROOT / "launch/stm32_serial.launch.py").is_file())
        self.assertIn('DeclareLaunchArgument("device", default_value="/dev/ttyACM0")', launch_source)
        self.assertIn('DeclareLaunchArgument("status_rate_hz", default_value="0.5")', launch_source)
        self.assertIn('DeclareLaunchArgument("gpio_status_rate_hz", default_value="1.0")', launch_source)
        self.assertIn('DeclareLaunchArgument("ultrasonic_rate_hz", default_value="5.0")', launch_source)
        self.assertIn('DeclareLaunchArgument("board_io_rate_hz", default_value="2.0")', launch_source)


if __name__ == "__main__":
    unittest.main()
