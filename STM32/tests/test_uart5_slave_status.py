from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Uart5SlaveStatusTests(unittest.TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def strip_c_comments(self, source):
        return re.sub(r"//[^\n]*|/\*.*?\*/", "", source, flags=re.DOTALL)

    def extract_braced_block(self, source, start_pattern):
        match = re.search(start_pattern, source, re.MULTILINE)
        self.assertIsNotNone(match, f"missing code matching {start_pattern!r}")

        opening_brace = source.find("{", match.end())
        self.assertNotEqual(opening_brace, -1, "matching code has no body")

        depth = 0
        for index in range(opening_brace, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    return source[opening_brace + 1:index]

        self.fail("matching code has an unterminated body")

    def test_uart5_slave_module_is_separate_and_built(self):
        header = self.read("Core/Inc/app_uart5_slave.h")
        source = self.read("Core/Src/app_uart5_slave.c")
        makefile = self.read("Makefile")

        self.assertIn("#ifndef APP_UART5_SLAVE_H", header)
        self.assertIn('#include "app_comm_protocol.h"', header)
        self.assertIn("HAL_StatusTypeDef App_Uart5Slave_Init(UART_HandleTypeDef *huart);", header)
        self.assertIn("void App_Uart5Slave_Run(uint32_t current_tick);", header)
        self.assertIn("void App_Uart5Slave_HandleRxCplt(UART_HandleTypeDef *huart);", header)
        self.assertIn('#include "app_uart5_slave.h"', source)
        self.assertIn("App_CommParser", source)
        self.assertIn("Core/Src/app_uart5_slave.c", makefile)

    def test_main_starts_uart5_slave_and_runs_it_from_main_loop(self):
        main = self.read("Core/Src/main.c")
        uncommented_main = self.strip_c_comments(main)

        self.assertIn('#include "app_uart5_slave.h"', main)
        self.assertIn("#define APP_USB_REENUMERATE_DELAY_MS 120U", main)
        self.assertIn("static void App_ForceUsbDisconnect(void);", main)
        self.assertIn("App_ForceUsbDisconnect();", main)
        self.assertIn("HAL_GPIO_WritePin(GPIOA, GPIO_PIN_12, GPIO_PIN_RESET);", main)
        self.assertIn("App_Uart5Slave_Init(&huart5)", main)
        self.assertIn("Error_Handler();", self.extract_braced_block(
            uncommented_main,
            r"\bif\s*\(\s*App_Uart5Slave_Init\s*\(\s*&huart5\s*\)\s*!=\s*HAL_OK\s*\)",
        ))

        main_body = self.extract_braced_block(uncommented_main, r"\bint\s+main\s*\(\s*void\s*\)")
        main_loop = self.extract_braced_block(main_body, r"\bwhile\s*\(\s*1\s*\)")
        self.assertIn("uint32_t current_tick = App_PeriodicTick_Get();", main_loop)
        self.assertIn("App_Uart5Slave_Run(current_tick);", main_loop)

    def test_main_services_fast_gpio_before_ultrasonic(self):
        main = self.read("Core/Src/main.c")
        uncommented_main = self.strip_c_comments(main)
        main_body = self.extract_braced_block(uncommented_main, r"\bint\s+main\s*\(\s*void\s*\)")
        main_loop = self.extract_braced_block(main_body, r"\bwhile\s*\(\s*1\s*\)")

        fast_index = main_loop.index("App_Uart5Slave_RunFastGpio(current_tick);")
        ultrasonic_index = main_loop.index("App_UltrasonicManager_Run(current_tick);")
        self.assertLess(fast_index, ultrasonic_index)

    def test_uart5_irq_is_enabled_and_routed_to_hal(self):
        interrupts = self.read("Core/Src/stm32f4xx_it.c")
        msp = self.read("Core/Src/stm32f4xx_hal_msp.c")

        self.assertIn("extern UART_HandleTypeDef huart5;", interrupts)
        self.assertIn("void UART5_IRQHandler(void)", interrupts)
        self.assertIn("HAL_UART_IRQHandler(&huart5);", interrupts)
        self.assertIn("HAL_NVIC_SetPriority(UART5_IRQn", msp)
        self.assertIn("HAL_NVIC_EnableIRQ(UART5_IRQn);", msp)
        self.assertIn("HAL_NVIC_DisableIRQ(UART5_IRQn);", msp)

    def test_uart5_rx_callback_dispatches_to_app_module(self):
        source = self.read("Core/Src/app_uart5_slave.c")
        uncommented_source = self.strip_c_comments(source)

        callback = self.extract_braced_block(
            uncommented_source,
            r"\bvoid\s+HAL_UART_RxCpltCallback\s*\(\s*UART_HandleTypeDef\s*\*\s*huart\s*\)",
        )
        self.assertIn("App_Uart5Slave_HandleRxCplt(huart);", callback)

        handler = self.extract_braced_block(
            uncommented_source,
            r"\bvoid\s+App_Uart5Slave_HandleRxCplt\s*\(\s*UART_HandleTypeDef\s*\*\s*huart\s*\)",
        )
        self.assertIn("huart->Instance != UART5", handler)
        self.assertIn("HAL_UART_Receive_IT(s_uart5, &s_rx_byte, 1U);", handler)

    def test_status_protocol_uses_binary_frames(self):
        source = self.read("Core/Src/app_uart5_slave.c")

        self.assertIn("APP_COMM_FRAME_ID_STATUS_QUERY", source)
        self.assertIn("APP_COMM_FRAME_ID_STATUS_RESPONSE", source)
        self.assertIn("APP_COMM_FRAME_ID_ERROR_RESPONSE", source)
        self.assertIn("App_CommProtocol_ParseByte(&s_parser, s_rx_byte, &s_rx_frame)", source)
        self.assertIn("App_CommProtocol_Encode(", source)
        self.assertIn("App_CommProtocol_DecodeStatusQuery(frame, &status_query)", source)
        self.assertIn("payload[0] = seq;", source)
        self.assertIn("payload[1] = (uint8_t)(current_tick & 0xFFU);", source)
        self.assertIn("payload[5] = APP_UART5_SLAVE_STATUS_OK;", source)
        self.assertIn("payload[6] = App_RelayControl_GetBitmap();", source)
        self.assertNotIn('"STATUS?"', source)
        self.assertNotIn('"DM3.1_BAT,OK', source)
        self.assertIn("HAL_UART_Transmit(s_uart5", source)

    def test_status_response_appends_communication_diagnostics(self):
        source = self.read("Core/Src/app_uart5_slave.c")

        self.assertIn("uint8_t payload[29];", source)
        self.assertIn("App_RtkBridge_GetDiagnostics(&rtk_diagnostics);", source)
        self.assertIn("App_Uart5Slave_StoreU32(&payload[7], s_usb_busy_retries);", source)
        self.assertIn("App_Uart5Slave_StoreU32(&payload[11], s_usb_queue_overflows);", source)
        self.assertIn("App_Uart5Slave_StoreU32(&payload[15], s_usb_tx_failures);", source)
        self.assertIn("App_Uart5Slave_StoreU32(&payload[19], rtk_diagnostics.overflow_bytes);", source)
        self.assertIn("App_Uart5Slave_StoreU32(&payload[23], rtk_diagnostics.uart_errors);", source)
        self.assertIn("payload[27] = (uint8_t)(rtk_diagnostics.rx_high_water & 0xFFU);", source)

    def test_usb_cdc_can_feed_same_protocol_and_return_responses(self):
        header = self.read("Core/Inc/app_uart5_slave.h")
        source = self.read("Core/Src/app_uart5_slave.c")

        self.assertIn("void App_Uart5Slave_HandleUsbData(const uint8_t *data, uint32_t length);", header)
        self.assertIn('#include "usbd_cdc_if.h"', source)
        self.assertIn('#include "usbd_core.h"', source)
        self.assertIn("App_CommProtocol_ParseByte(&s_usb_parser", source)
        self.assertIn("APP_UART5_SLAVE_USB_TX_QUEUE_DEPTH 2U", source)
        self.assertIn("App_Uart5Slave_QueueUsbFrame", source)
        self.assertIn("App_Uart5Slave_PumpUsbTx", source)
        self.assertIn("CDC_Transmit_FS(frame->data, frame->length)", source)
        self.assertIn("result == USBD_BUSY", source)
        self.assertIn("App_Uart5Slave_HandleUsbTxComplete", source)
        self.assertIn("App_Uart5Slave_HandleUsbTxComplete();", self.read("USB_DEVICE/App/usbd_cdc_if.c"))
        self.assertIn("USBD_Stop(&hUsbDeviceFS)", source)
        self.assertIn("USBD_DeInit(&hUsbDeviceFS)", source)
        self.assertIn("HAL_Delay(50U);", source)

    def test_uart5_slave_dispatches_gpio_control_frames(self):
        source = self.read("Core/Src/app_uart5_slave.c")
        header = self.read("Core/Inc/app_uart5_slave.h")

        self.assertIn('#include "app_relay_control.h"', header)
        self.assertIn("void App_Uart5Slave_RunFastGpio(uint32_t current_tick);", header)
        self.assertIn("APP_COMM_FRAME_ID_GPIO_CONTROL_REQUEST", source)
        self.assertIn("APP_COMM_FRAME_ID_GPIO_CONTROL_RESPONSE", source)
        self.assertIn("App_CommProtocol_DecodeGpioControlRequest(&frame, &control)", source)
        self.assertIn("App_RelayControl_Apply(&control, current_tick)", source)
        self.assertIn("App_Uart5Slave_SendControlResponse(control.seq, control.channel_id, result);", source)

    def test_fast_gpio_service_consumes_only_gpio_control_frames(self):
        source = self.read("Core/Src/app_uart5_slave.c")
        uncommented_source = self.strip_c_comments(source)

        fast_handler = self.extract_braced_block(
            uncommented_source,
            r"\bvoid\s+App_Uart5Slave_RunFastGpio\s*\(\s*uint32_t\s+current_tick\s*\)",
        )

        self.assertIn("APP_COMM_FRAME_ID_GPIO_CONTROL_REQUEST", fast_handler)
        self.assertIn("s_frame_ready = 0U;", fast_handler)
        self.assertIn("App_CommProtocol_DecodeGpioControlRequest(&frame, &control)", fast_handler)
        self.assertIn("App_RelayControl_Apply(&control, current_tick)", fast_handler)
        self.assertIn("App_Uart5Slave_SendControlResponse(control.seq, control.channel_id, result);", fast_handler)

    def test_uart5_slave_dispatches_gpio_status_query_frames(self):
        source = self.read("Core/Src/app_uart5_slave.c")

        self.assertIn("APP_COMM_FRAME_ID_GPIO_STATUS_QUERY", source)
        self.assertIn("APP_COMM_FRAME_ID_GPIO_STATUS_RESPONSE", source)
        self.assertIn("App_CommProtocol_DecodeGpioStatusQuery(frame, &gpio_status_query)", source)
        self.assertIn("App_Uart5Slave_SendGpioStatus(gpio_status_query.seq);", source)
        self.assertIn("payload[0] = seq;", source)
        self.assertIn("payload[1] = App_RelayControl_GetBitmap();", source)

    def test_uart5_slave_dispatches_ultrasonic_query_frames(self):
        source = self.read("Core/Src/app_uart5_slave.c")
        header = self.read("Core/Inc/app_uart5_slave.h")

        self.assertIn('#include "app_ultrasonic_manager.h"', header)
        self.assertIn("APP_COMM_FRAME_ID_ULTRASONIC_QUERY", source)
        self.assertIn("APP_COMM_FRAME_ID_ULTRASONIC_RESPONSE", source)
        self.assertIn("App_CommProtocol_DecodeUltrasonicQuery(frame, &ultrasonic_query)", source)
        self.assertIn("App_UltrasonicManager_GetSnapshot(&ultrasonic_snapshot)", source)
        self.assertIn("App_Uart5Slave_SendUltrasonicStatus(ultrasonic_query.seq);", source)
        self.assertIn("payload[0] = seq;", source)
        self.assertIn("payload[1] = (uint8_t)(ultrasonic_snapshot.front_mm & 0xFFU);", source)
        self.assertIn("payload[3] = (uint8_t)(ultrasonic_snapshot.left_mm & 0xFFU);", source)
        self.assertIn("payload[5] = (uint8_t)(ultrasonic_snapshot.right_mm & 0xFFU);", source)
        self.assertIn("payload[7] = ultrasonic_snapshot.valid_bitmap;", source)
        self.assertIn("payload[8] = ultrasonic_snapshot.error_bitmap;", source)

    def test_uart5_slave_error_response_includes_context(self):
        source = self.read("Core/Src/app_uart5_slave.c")

        self.assertIn("static void App_Uart5Slave_SendError(uint8_t seq, uint8_t source_frame_id, uint8_t error_code)", source)
        self.assertIn("payload[0] = seq;", source)
        self.assertIn("payload[1] = source_frame_id;", source)
        self.assertIn("payload[2] = error_code;", source)
        self.assertIn("APP_COMM_ERROR_CODE_CHECKSUM", source)
        self.assertIn("APP_COMM_ERROR_CODE_LENGTH", source)


if __name__ == "__main__":
    unittest.main()
