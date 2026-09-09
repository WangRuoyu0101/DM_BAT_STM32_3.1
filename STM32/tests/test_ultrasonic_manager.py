from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UltrasonicManagerTests(unittest.TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_manager_module_defines_three_sensor_instances(self):
        header = self.read("Core/Inc/app_ultrasonic_manager.h")
        source = self.read("Core/Src/app_ultrasonic_manager.c")
        makefile = self.read("Makefile")

        self.assertIn("#ifndef APP_ULTRASONIC_MANAGER_H", header)
        self.assertIn("APP_ULTRASONIC_SENSOR_FRONT", header)
        self.assertIn("APP_ULTRASONIC_SENSOR_LEFT", header)
        self.assertIn("APP_ULTRASONIC_SENSOR_RIGHT", header)
        self.assertIn("App_UltrasonicManager_Init", header)
        self.assertIn("App_UltrasonicManager_Run", header)
        self.assertIn("App_UltrasonicManager_HandleRxCplt", header)
        self.assertIn("App_UltrasonicManager_GetSnapshot", header)
        self.assertIn('#include "app_ultrasonic_manager.h"', source)
        self.assertIn('#include "app_ultrasonic_protocol.h"', source)
        self.assertIn("Core/Src/app_ultrasonic_manager.c", makefile)

    def test_manager_uses_expected_uart_mapping_and_controlled_trigger_timing(self):
        source = self.read("Core/Src/app_ultrasonic_manager.c")
        main = self.read("Core/Src/main.c")
        interrupts = self.read("Core/Src/stm32f4xx_it.c")
        msp = self.read("Core/Src/stm32f4xx_hal_msp.c")

        self.assertIn("APP_ULTRASONIC_TRIGGER_PERIOD_MS 200U", source)
        self.assertIn("APP_ULTRASONIC_TRIGGER_GAP_MS 20U", source)
        self.assertIn("APP_ULTRASONIC_RESPONSE_TIMEOUT_MS 80U", source)
        self.assertIn("APP_ULTRASONIC_WAKE_RESPONSE_EXTRA_MS 12U", source)
        self.assertIn("APP_ULTRASONIC_SLEEP_TIMEOUT_MS 5000U", source)
        self.assertIn("{APP_ULTRASONIC_SENSOR_FRONT, USART2", source)
        self.assertIn("{APP_ULTRASONIC_SENSOR_LEFT, UART4", source)
        self.assertIn("{APP_ULTRASONIC_SENSOR_RIGHT, USART3", source)
        self.assertIn("HAL_UART_Transmit(sensor->huart, &trigger_byte, 1U", source)
        self.assertIn("HAL_UART_Receive_IT(sensor->huart, &sensor->rx_byte, 1U)", source)
        self.assertIn("current_tick - sensor->last_trigger_tick", source)
        self.assertIn("APP_ULTRASONIC_TRIGGER_PERIOD_MS", source)
        self.assertIn("sensor->last_trigger_tick == 0U", source)
        self.assertIn("sensor->slot_delay_ms", source)
        self.assertIn("App_UltrasonicProtocol_ParseByte(&sensor->parser, sensor->rx_byte, &distance_mm)", source)
        self.assertIn("APP_ULTRASONIC_PARSE_INTERFERENCE", source)
        self.assertIn("APP_ULTRASONIC_PARSE_NO_TARGET", source)
        self.assertIn("APP_ULTRASONIC_ERROR_TIMEOUT", source)

        self.assertIn('#include "app_ultrasonic_manager.h"', main)
        self.assertIn("App_UltrasonicManager_Init(&huart2, &huart4, &huart3)", main)
        self.assertIn("App_UltrasonicManager_Run(current_tick);", main)
        self.assertIn("extern UART_HandleTypeDef huart2;", interrupts)
        self.assertIn("extern UART_HandleTypeDef huart3;", interrupts)
        self.assertIn("extern UART_HandleTypeDef huart4;", interrupts)
        self.assertIn("void USART2_IRQHandler(void)", interrupts)
        self.assertIn("void USART3_IRQHandler(void)", interrupts)
        self.assertIn("void UART4_IRQHandler(void)", interrupts)
        self.assertIn("HAL_UART_IRQHandler(&huart2);", interrupts)
        self.assertIn("HAL_UART_IRQHandler(&huart3);", interrupts)
        self.assertIn("HAL_UART_IRQHandler(&huart4);", interrupts)
        self.assertIn("HAL_NVIC_EnableIRQ(USART2_IRQn);", msp)
        self.assertIn("HAL_NVIC_EnableIRQ(USART3_IRQn);", msp)
        self.assertIn("HAL_NVIC_EnableIRQ(UART4_IRQn);", msp)


if __name__ == "__main__":
    unittest.main()
