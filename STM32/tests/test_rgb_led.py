from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RgbLedTest(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_ws2812_driver_and_pb13_wiring(self):
        main_h = self.read("Core/Inc/main.h")
        main_c = self.read("Core/Src/main.c")
        ioc = self.read("DM3.1_BAT.ioc")
        makefile = self.read("Makefile")

        self.assertIn("RGB_Pin GPIO_PIN_13", main_h)
        self.assertIn("RGB_GPIO_Port GPIOB", main_h)
        self.assertIn("PB13.GPIO_Label=RGB", ioc)
        self.assertIn("PB13.Signal=GPIO_Output", ioc)
        self.assertIn("Core/Src/app_rgb_led.c", makefile)
        self.assertIn("App_RgbLed_Init();", main_c)
        self.assertIn("App_RgbLed_Run(current_tick);", main_c)

    def test_driver_behavior_harness(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "rgb_led_harness"
            subprocess.run(
                [
                    "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "tests/c"),
                    "-I", str(ROOT / "Core/Inc"),
                    str(ROOT / "tests/c/rgb_led_harness.c"),
                    "-o", str(executable),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    unittest.main()
