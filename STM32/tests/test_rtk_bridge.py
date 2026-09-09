from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RtkBridgeTest(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_uart6_bridge_uses_interrupt_ring_buffer(self):
        header = self.read("Core/Inc/app_rtk_bridge.h")
        source = self.read("Core/Src/app_rtk_bridge.c")
        main = self.read("Core/Src/main.c")
        makefile = self.read("Makefile")

        self.assertIn("APP_RTK_BRIDGE_RX_CAPACITY 1024U", header)
        self.assertIn("App_RtkBridge_Init", header)
        self.assertIn("App_RtkBridge_Write", header)
        self.assertIn("App_RtkBridge_Read", header)
        self.assertIn("App_RtkBridge_HandleRxCplt", header)
        self.assertIn("App_RtkBridge_HandleError", header)
        self.assertIn("s_rx_buffer[s_rx_head & APP_RTK_BRIDGE_RX_MASK]", source)
        self.assertIn("s_rx_overflow = 1U", source)
        self.assertIn("HAL_UART_Receive_IT", source)
        self.assertIn("HAL_UART_Transmit", source)
        self.assertIn("App_RtkBridge_Init(&huart6)", main)
        self.assertIn("Core/Src/app_rtk_bridge.c", makefile)

    def test_rtk_protocol_uses_full_application_payload(self):
        protocol = self.read("Core/Inc/app_comm_protocol.h")

        self.assertIn(
            "#define APP_COMM_RTK_WRITE_DATA_MAX (APP_COMM_MAX_PAYLOAD_SIZE - 1U)",
            protocol,
        )
        self.assertIn(
            "#define APP_COMM_RTK_READ_DATA_MAX (APP_COMM_MAX_PAYLOAD_SIZE - 2U)",
            protocol,
        )

    def test_rtk_bridge_exposes_cumulative_diagnostics(self):
        header = self.read("Core/Inc/app_rtk_bridge.h")
        source = self.read("Core/Src/app_rtk_bridge.c")

        self.assertIn("App_RtkBridgeDiagnostics", header)
        self.assertIn("uint32_t overflow_bytes;", header)
        self.assertIn("uint32_t uart_errors;", header)
        self.assertIn("uint16_t rx_high_water;", header)
        self.assertIn("App_RtkBridge_GetDiagnostics", header)
        self.assertIn("s_overflow_bytes", source)
        self.assertIn("s_uart_errors", source)
        self.assertIn("s_rx_high_water", source)

    def test_uart6_irq_and_callbacks_are_wired(self):
        msp = self.read("Core/Src/stm32f4xx_hal_msp.c")
        irq = self.read("Core/Src/stm32f4xx_it.c")
        irq_h = self.read("Core/Inc/stm32f4xx_it.h")
        slave = self.read("Core/Src/app_uart5_slave.c")

        usart6_msp = msp.split("else if(huart->Instance==USART6)", 1)[1].split(
            "void HAL_UART_MspDeInit", 1
        )[0]
        self.assertIn("HAL_NVIC_EnableIRQ(USART6_IRQn)", usart6_msp)
        self.assertIn("extern UART_HandleTypeDef huart6;", irq)
        self.assertIn("void USART6_IRQHandler(void)", irq)
        self.assertIn("HAL_UART_IRQHandler(&huart6)", irq)
        self.assertIn("void USART6_IRQHandler(void);", irq_h)
        self.assertIn("App_RtkBridge_HandleRxCplt(huart)", slave)
        self.assertIn("App_RtkBridge_HandleError(huart)", slave)


if __name__ == "__main__":
    unittest.main()
