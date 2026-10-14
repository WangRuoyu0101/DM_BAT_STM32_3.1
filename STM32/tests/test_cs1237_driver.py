from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CS1237DriverTest(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_driver_maps_pins_and_exposes_nonblocking_snapshot_api(self):
        header = self.read("Core/Inc/app_cs1237.h")
        source = self.read("Core/Src/app_cs1237.c")
        main_h = self.read("Core/Inc/main.h")
        main_c = self.read("Core/Src/main.c")
        ioc = self.read("DM3.1_BAT.ioc")
        makefile = self.read("Makefile")

        self.assertIn("CS1237_CLK_Pin GPIO_PIN_9", main_h)
        self.assertIn("CS1237_CLK_GPIO_Port GPIOC", main_h)
        self.assertIn("CS1237_DIO_Pin GPIO_PIN_8", main_h)
        self.assertIn("CS1237_DIO_GPIO_Port GPIOC", main_h)
        self.assertIn("PC9.GPIO_Label=CS1237_CLK", ioc)
        self.assertIn("PC8.GPIO_Label=CS1237_DIO", ioc)
        self.assertNotIn("PD11.GPIO_Label=CS1237_CLK", ioc)
        self.assertNotIn("PD14.GPIO_Label=CS1237_DIO", ioc)
        self.assertIn("App_CS1237_Init", header)
        self.assertIn("App_CS1237_Run", header)
        self.assertIn("App_CS1237_SetChannel", header)
        self.assertIn("App_CS1237_GetSnapshot", header)
        self.assertIn("APP_CS1237_CHANNEL_TEMPERATURE = 2", header)
        self.assertIn("APP_CS1237_SETTLING_SAMPLES 3U", source)
        self.assertIn(
            "return App_CS1237_SetChannel(APP_CS1237_CHANNEL_DIFFERENTIAL);",
            source,
        )
        self.assertIn("raw |= (int32_t)0xFF000000", source)
        self.assertIn("channel == APP_CS1237_CHANNEL_RESERVED", source)
        self.assertIn("App_CS1237_Init()", main_c)
        self.assertIn("App_CS1237_Run();", main_c)
        self.assertIn("Core/Src/app_cs1237.c", makefile)

    def test_channel_configuration_selects_required_gain(self):
        source = self.read("Core/Src/app_cs1237.c")

        self.assertIn("APP_CS1237_CONFIG_RATE_10HZ", source)
        self.assertIn("APP_CS1237_CONFIG_REF_ON", source)
        self.assertIn("APP_CS1237_CONFIG_PGA_1", source)
        self.assertIn("APP_CS1237_CONFIG_PGA_128", source)
        self.assertIn("App_CS1237_BuildConfig", source)
        self.assertIn("s_settling_samples--", source)
        self.assertIn("s_snapshot.valid = 0U", source)


if __name__ == "__main__":
    unittest.main()
