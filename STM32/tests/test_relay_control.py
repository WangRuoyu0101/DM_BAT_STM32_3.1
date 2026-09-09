from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RelayControlTests(unittest.TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_relay_control_module_maps_channels_to_gpio_pins(self):
        header = self.read("Core/Inc/app_relay_control.h")
        source = self.read("Core/Src/app_relay_control.c")
        main = self.read("Core/Src/main.c")
        ioc = self.read("DM3.1_BAT.ioc")
        makefile = self.read("Makefile")

        self.assertIn("#ifndef APP_RELAY_CONTROL_H", header)
        self.assertIn('#include "app_comm_protocol.h"', header)
        self.assertIn(
            "uint8_t App_RelayControl_Apply(const App_CommGpioControl *control, uint32_t current_tick);",
            header,
        )
        self.assertIn("uint8_t App_RelayControl_GetBitmap(void);", header)
        self.assertIn('#include "app_relay_control.h"', source)
        self.assertIn("SIGNAL-FLASH-CTR", source)
        self.assertIn("SIGNAL-LED", source)
        self.assertIn("SIGNAL-BEE", source)
        self.assertIn("SIGNAL-MOTOR", source)
        self.assertIn("SIGNAL-FLASH", source)
        self.assertIn("SIGNAL-SOUND", source)
        self.assertIn("{APP_COMM_GPIO_CHANNEL_FLASH_CTR, GPIOC, GPIO_PIN_5}", source)
        self.assertIn("{APP_COMM_GPIO_CHANNEL_LED, GPIOE, GPIO_PIN_7}", source)
        self.assertIn("{APP_COMM_GPIO_CHANNEL_BEE, GPIOE, GPIO_PIN_9}", source)
        self.assertIn("{APP_COMM_GPIO_CHANNEL_MOTOR, GPIOE, GPIO_PIN_12}", source)
        self.assertIn("{APP_COMM_GPIO_CHANNEL_FLASH, GPIOB, GPIO_PIN_1}", source)
        self.assertIn("{APP_COMM_GPIO_CHANNEL_SOUND, GPIOB, GPIO_PIN_12}", source)
        self.assertNotIn("MOROTX", source)
        self.assertNotIn("RESERVED", source)
        self.assertNotIn("HAL_GPIO_WritePin(GPIOA, GPIO_PIN_7", main)
        self.assertNotIn("GPIO_PIN_4|LED_RUN_Pin", main)
        self.assertIn("GPIO_PIN_5|LED_RUN_Pin", main)
        self.assertIn("HAL_GPIO_WritePin(GPIOB, GPIO_PIN_12, GPIO_PIN_SET);", main)
        self.assertIn("PB12.GPIO_OutputLevel=GPIO_PIN_SET", ioc)
        self.assertIn("PA7.Signal=TIM3_CH2", ioc)
        self.assertNotIn("PC4.Signal=GPIO_Output", ioc)
        self.assertIn("PC5.Signal=GPIO_Output", ioc)
        self.assertIn("HAL_GPIO_WritePin", source)
        self.assertIn("HAL_GPIO_ReadPin", source)
        self.assertIn("bitmap = (uint8_t)(bitmap | (1U << index));", source)
        self.assertIn("GPIO_PIN_SET", source)
        self.assertIn("GPIO_PIN_RESET", source)
        self.assertIn("Core/Src/app_relay_control.c", makefile)

    def test_flash_control_is_a_retriggerable_200_ms_pulse(self):
        header = self.read("Core/Inc/app_relay_control.h")
        source = self.read("Core/Src/app_relay_control.c")
        uart5 = self.read("Core/Src/app_uart5_slave.c")
        main = self.read("Core/Src/main.c")

        self.assertIn("#define APP_RELAY_CONTROL_FLASH_PULSE_TICKS 100U", source)
        self.assertIn(
            "uint8_t App_RelayControl_Apply(const App_CommGpioControl *control, uint32_t current_tick);",
            header,
        )
        self.assertIn("void App_RelayControl_Service(uint32_t current_tick);", header)
        self.assertIn("s_flash_pulse_active", source)
        self.assertIn("s_flash_pulse_start_tick = current_tick;", source)
        self.assertIn(
            "(uint32_t)(current_tick - s_flash_pulse_start_tick) >= APP_RELAY_CONTROL_FLASH_PULSE_TICKS",
            source,
        )
        self.assertIn("control->channel_id == APP_COMM_GPIO_CHANNEL_FLASH_CTR", source)
        self.assertIn("control->level == APP_COMM_GPIO_LEVEL_LOW", source)
        self.assertNotIn("HAL_Delay", source)
        self.assertEqual(uart5.count("App_RelayControl_Apply(&control, current_tick)"), 2)
        self.assertNotIn("(void)current_tick;", uart5)
        self.assertIn("App_RelayControl_Service(current_tick);", main)
