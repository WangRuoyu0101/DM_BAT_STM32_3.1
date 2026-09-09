from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BoardIOTest(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_cube_and_hal_map_dm31_fan_and_keys(self):
        main_h = self.read("Core/Inc/main.h")
        main_c = self.read("Core/Src/main.c")
        msp = self.read("Core/Src/stm32f4xx_hal_msp.c")
        irq = self.read("Core/Src/stm32f4xx_it.c")
        ioc = self.read("DM3.1_BAT.ioc")

        self.assertIn("FAN_PWM_Pin GPIO_PIN_5", main_h)
        self.assertIn("FAN_SPEED_1_Pin GPIO_PIN_6", main_h)
        self.assertIn("FAN_SPEED_2_Pin GPIO_PIN_7", main_h)
        self.assertIn("KEY1_Pin GPIO_PIN_15", main_h)
        self.assertIn("KEY2_Pin GPIO_PIN_13", main_h)
        self.assertIn("htim2.Init.Period = 3359", main_c)
        self.assertIn("htim3.Init.Prescaler = 839", main_c)
        self.assertIn("HAL_TIM_PWM_Init(&htim2)", main_c)
        self.assertIn("HAL_TIM_IC_Init(&htim3)", main_c)
        self.assertIn("GPIO_AF1_TIM2", msp)
        self.assertIn("GPIO_AF2_TIM3", msp)
        self.assertIn("TIM3_IRQHandler", irq)
        self.assertIn("PA5.Signal=TIM2_CH1", ioc)
        self.assertIn("PA6.Signal=TIM3_CH1", ioc)
        self.assertIn("PA7.Signal=TIM3_CH2", ioc)
        self.assertIn("PE13.GPIO_PuPd=GPIO_PULLUP", ioc)
        self.assertIn("PE15.GPIO_PuPd=GPIO_PULLUP", ioc)

    def test_board_io_module_implements_four_levels_tach_and_debounce(self):
        header = self.read("Core/Inc/app_board_io.h")
        source = self.read("Core/Src/app_board_io.c")
        main_c = self.read("Core/Src/main.c")
        makefile = self.read("Makefile")

        self.assertIn("APP_BOARD_IO_DEFAULT_FAN_LEVEL 2U", header)
        self.assertIn("APP_BOARD_IO_FAN_PULSES_PER_REV 2U", header)
        self.assertIn("APP_BOARD_IO_KEY_DEBOUNCE_TICKS 10U", header)
        self.assertIn("APP_BOARD_IO_TACH_TIMEOUT_TICKS 750U", header)
        for pulse in ("840U", "1680U", "2520U", "3360U"):
            self.assertIn(pulse, source)
        self.assertIn("HAL_TIM_PWM_Start", source)
        self.assertIn("HAL_TIM_IC_Start_IT", source)
        self.assertIn("HAL_TIM_ReadCapturedValue", source)
        self.assertIn("APP_BOARD_IO_FAN_PULSES_PER_REV", source)
        self.assertIn("GPIO_PIN_RESET", source)
        self.assertIn("App_BoardIO_Init(&htim2, &htim3)", main_c)
        self.assertIn("App_BoardIO_Run(current_tick);", main_c)
        self.assertIn("Core/Src/app_board_io.c", makefile)


if __name__ == "__main__":
    unittest.main()
