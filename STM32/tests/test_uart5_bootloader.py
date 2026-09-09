from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Uart5BootloaderTests(unittest.TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_flash_layout_constants_define_bootloader_and_app_regions(self):
        header = self.read("Core/Inc/app_flash_layout.h")

        self.assertIn("#define APP_FLASH_BOOT_BASE 0x08000000U", header)
        self.assertIn("#define APP_FLASH_BOOT_SIZE (32U * 1024U)", header)
        self.assertIn("#define APP_FLASH_BASE 0x08008000U", header)
        self.assertIn("#define APP_FLASH_SIZE (352U * 1024U)", header)
        self.assertIn("#define APP_FLASH_END 0x08060000U", header)
        self.assertIn("#define APP_METADATA_BASE 0x08060000U", header)
        self.assertIn("#define APP_METADATA_SIZE (128U * 1024U)", header)
        self.assertIn("#define APP_METADATA_MAGIC 0x41334D44U", header)
        self.assertIn("#define APP_METADATA_FORMAT_VERSION 1U", header)
        self.assertIn("#define APP_SRAM_BASE 0x20000000U", header)
        self.assertIn("#define APP_SRAM_END 0x20020000U", header)

    def test_linker_scripts_partition_flash(self):
        boot_ld = self.read("STM32F407XX_BOOT_FLASH.ld")
        app_ld = self.read("STM32F407XX_APP_FLASH.ld")

        self.assertIn("FLASH (rx)      : ORIGIN = 0x8000000, LENGTH = 32K", boot_ld)
        self.assertIn("FLASH (rx)      : ORIGIN = 0x8008000, LENGTH = 352K", app_ld)
        self.assertIn("RAM (xrw)      : ORIGIN = 0x20000000, LENGTH = 128K", boot_ld)
        self.assertIn("RAM (xrw)      : ORIGIN = 0x20000000, LENGTH = 128K", app_ld)

    def test_application_sets_vector_table_to_relocated_base(self):
        system = self.read("Core/Src/system_stm32f4xx.c")

        self.assertIn('#include "app_flash_layout.h"', system)
        self.assertIn("SCB->VTOR = APP_FLASH_BASE;", system)

    def test_makefile_builds_distinct_app_and_bootloader_images(self):
        makefile = self.read("Makefile")

        self.assertIn("APP_BUILD_DIR = build/app", makefile)
        self.assertIn("BOOT_BUILD_DIR = build/bootloader", makefile)
        self.assertIn("HOST_FIRMWARE_DIR = ../Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware", makefile)
        self.assertIn("HOST_APP_BIN = $(HOST_FIRMWARE_DIR)/$(TARGET)_app.bin", makefile)
        self.assertIn("APP_LDSCRIPT = STM32F407XX_APP_FLASH.ld", makefile)
        self.assertIn("BOOT_LDSCRIPT = STM32F407XX_BOOT_FLASH.ld", makefile)
        self.assertRegex(makefile, r"(?m)^app:\s+\$\(APP_BUILD_DIR\)/\$\(TARGET\)_app\.elf")
        self.assertIn("app: $(HOST_APP_BIN)", makefile)
        self.assertIn("$(HOST_APP_BIN): $(APP_BIN)", makefile)
        self.assertIn("cp $(APP_BIN) $(HOST_APP_BIN)", makefile)
        self.assertRegex(makefile, r"(?m)^bootloader:\s+\$\(BOOT_BUILD_DIR\)/\$\(TARGET\)_bootloader\.elf")
        self.assertIn("Bootloader/Core/Src/main.c", makefile)
        self.assertIn("Bootloader/Core/Src/bootloader_flash.c", makefile)
        self.assertIn("Bootloader/Core/Src/bootloader_protocol.c", makefile)
        self.assertIn("Bootloader/Core/Src/bootloader_jump.c", makefile)
        self.assertIn("Bootloader/Core/Src/bootloader_usb_cdc.c", makefile)
        self.assertIn("USB_DEVICE/App/usb_device.c", makefile)
        self.assertIn("USB_DEVICE/Target/usbd_conf.c", makefile)
        self.assertIn("Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Src/usbd_cdc.c", makefile)

    def test_bootloader_config_defines_protocol_and_limits(self):
        config = self.read("Bootloader/Core/Inc/bootloader_config.h")

        self.assertIn("#define BOOTLOADER_UART_BAUDRATE 460800U", config)
        self.assertIn("#define BOOTLOADER_HANDSHAKE_TIMEOUT_MS 2000U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_HELLO 0x10U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_INFO 0x90U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_START 0x11U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_ERASE 0x12U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_WRITE 0x13U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_VERIFY 0x14U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_JUMP 0x15U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_RESET 0x16U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_ACK 0x91U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_STATUS 0x92U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_ERROR 0xE2U", config)
        self.assertIn("#define BOOTLOADER_MAX_PAYLOAD_SIZE 250U", config)
        self.assertIn("#define BOOTLOADER_WRITE_DATA_MAX 245U", config)
        self.assertIn("#define BOOTLOADER_LED_TOGGLE_PERIOD_MS 75U", config)
        self.assertIn("#define BOOTLOADER_LED_RUN_PIN GPIO_PIN_10", config)
        self.assertIn("#define BOOTLOADER_STATUS_REPORT_PERIOD_MS 1000U", config)
        self.assertIn("#define BOOTLOADER_VERSION 0x00020000U", config)

    def test_bootloader_protocol_uses_binary_frames_and_crc8(self):
        header = self.read("Bootloader/Core/Inc/bootloader_protocol.h")
        source = self.read("Bootloader/Core/Src/bootloader_protocol.c")

        self.assertIn("Bootloader_ProtocolEncode", header)
        self.assertIn("Bootloader_ProtocolParseByte", header)
        self.assertIn("BOOTLOADER_FRAME_HEADER0", source)
        self.assertIn("BOOTLOADER_FRAME_HEADER1", source)
        self.assertIn("BOOTLOADER_CRC8_POLY", source)
        self.assertIn("crc ^= byte;", source)

    def test_bootloader_flash_protects_boot_region_and_verifies_crc32(self):
        header = self.read("Bootloader/Core/Inc/bootloader_flash.h")
        source = self.read("Bootloader/Core/Src/bootloader_flash.c")

        self.assertIn("Bootloader_FlashIsAppRange", header)
        self.assertIn("Bootloader_FlashStartSession", header)
        self.assertIn("Bootloader_FlashWrite", header)
        self.assertIn("Bootloader_FlashVerify", header)
        self.assertIn("Bootloader_FlashInvalidateMetadata", header)
        self.assertIn("Bootloader_FlashCommitMetadata", header)
        self.assertIn("Bootloader_FlashIsApplicationValid", header)
        self.assertIn("uint8_t erased;", header)
        self.assertIn("address < APP_FLASH_BASE", source)
        self.assertIn("end_address > APP_FLASH_END", source)
        self.assertIn("APP_FLASH_BASE + offset", source)
        self.assertIn("Bootloader_FlashEraseApplication(Bootloader_FlashSession *session)", source)
        self.assertIn("erase.Sector = FLASH_SECTOR_2;", source)
        self.assertIn("erase.NbSectors = 5U;", source)
        self.assertIn("FLASH_SECTOR_7", source)
        self.assertIn("session->erased", source)
        self.assertLess(
            source.index("Bootloader_FlashInvalidateMetadata()"),
            source.index("HAL_FLASHEx_Erase(&erase, &sector_error)"),
        )
        self.assertLess(
            source.index("Bootloader_FlashCommitMetadata(session->image_size, session->image_crc32)"),
            source.index("return BOOTLOADER_STATUS_OK;", source.index("Bootloader_FlashVerify")),
        )
        self.assertIn("result = Bootloader_FlashCommitMetadata", source)
        self.assertIn("return result;", source[source.index("Bootloader_FlashVerify"):])
        self.assertIn("Bootloader_FlashCrc32", source)

    def test_bootloader_jump_validates_vectors_before_jump(self):
        header = self.read("Bootloader/Core/Inc/bootloader_jump.h")
        source = self.read("Bootloader/Core/Src/bootloader_jump.c")

        self.assertIn("Bootloader_IsApplicationValid", header)
        self.assertIn("Bootloader_JumpToApplication", header)
        self.assertIn("Bootloader_FlashIsApplicationValid()", source)
        self.assertIn("__set_MSP(stack_pointer);", source)
        self.assertIn("__enable_irq();", source)
        self.assertIn("app_reset_handler();", source)

    def test_bootloader_main_initializes_uart5_and_dispatches_commands(self):
        source = self.read("Bootloader/Core/Src/main.c")

        self.assertIn("UART_HandleTypeDef huart5;", source)
        self.assertIn('#include "app_bootloader_request.h"', source)
        self.assertIn("MX_UART5_Init", source)
        self.assertIn("MX_GPIO_Init", source)
        self.assertIn("GPIO_AF8_UART5", source)
        self.assertIn("Bootloader_StatusLedRun(HAL_GetTick());", source)
        self.assertIn("HAL_GPIO_TogglePin(BOOTLOADER_LED_RUN_GPIO_PORT, BOOTLOADER_LED_RUN_PIN);", source)
        self.assertIn("BOOTLOADER_LED_TOGGLE_PERIOD_MS", source)
        self.assertIn("App_BootloaderRequest_ConsumeFlag()", source)
        self.assertIn("BOOTLOADER_HANDSHAKE_TIMEOUT_MS", source)
        self.assertIn("Bootloader_HandleFrame", source)
        self.assertIn("Bootloader_JumpToApplication", source)

    def test_bootloader_reports_cached_runtime_state_when_flash_is_idle(self):
        source = self.read("Bootloader/Core/Src/main.c")

        self.assertIn("BOOTLOADER_STATE_WAITING = 0U", source)
        self.assertIn("BOOTLOADER_STATE_RECEIVING = 1U", source)
        self.assertIn("BOOTLOADER_STATE_VERIFIED = 2U", source)
        self.assertIn("BOOTLOADER_STATE_ERROR = 3U", source)
        self.assertIn("s_app_valid = Bootloader_IsApplicationValid();", source)
        self.assertIn("Bootloader_ReportStatusIfDue(HAL_GetTick());", source)
        self.assertIn("Bootloader_WriteLe32(&payload[4], s_session.next_offset);", source)
        self.assertIn("Bootloader_UsbCdcSendFrame(BOOTLOADER_FRAME_ID_STATUS", source)
        self.assertIn(
            "if (Bootloader_UsbCdcSendFrame(BOOTLOADER_FRAME_ID_STATUS, payload, (uint8_t)sizeof(payload)) == 0U)",
            source,
        )
        self.assertIn("Bootloader_SetState(BOOTLOADER_STATE_RECEIVING", source)
        self.assertIn("Bootloader_SetState(BOOTLOADER_STATE_VERIFIED", source)
        self.assertIn("Bootloader_SetState(BOOTLOADER_STATE_ERROR", source)
        self.assertLess(
            source.index("Bootloader_HandleFrame(&frame);"),
            source.index("Bootloader_ReportStatusIfDue(HAL_GetTick());"),
        )

    def test_bootloader_usb_cdc_feeds_same_protocol(self):
        header = self.read("Bootloader/Core/Inc/bootloader_usb_cdc.h")
        source = self.read("Bootloader/Core/Src/bootloader_usb_cdc.c")
        main = self.read("Bootloader/Core/Src/main.c")

        self.assertIn("Bootloader_UsbCdcHandleData", header)
        self.assertIn("Bootloader_UsbCdcDeInit", header)
        self.assertIn("Bootloader_UsbCdcPollFrame", header)
        self.assertIn("Bootloader_UsbCdcSendFrame", header)
        self.assertIn("USBD_Stop(&hUsbDeviceFS)", source)
        self.assertIn("USBD_DeInit(&hUsbDeviceFS)", source)
        self.assertIn("Bootloader_ProtocolParseByte(&s_usb_parser", source)
        self.assertIn("CDC_SET_LINE_CODING", source)
        self.assertIn("CDC_GET_LINE_CODING", source)
        self.assertIn("USBD_Interface_fops_FS", source)
        self.assertIn("CDC_Transmit_FS", source)
        self.assertIn('#include "usb_device.h"', main)
        self.assertIn("Bootloader_EnableUsbCdc", main)
        self.assertIn("s_usb_cdc_enabled", main)
        self.assertIn("if ((stay_in_bootloader != 0U) || (s_app_valid == 0U))", main)
        self.assertIn("Bootloader_ForceUsbDisconnect();", main)
        self.assertIn("#define BOOTLOADER_USB_REENUMERATE_DELAY_MS 120U", main)
        self.assertIn("#define BOOTLOADER_USB_FINAL_ACK_DELAY_MS 20U", main)
        self.assertIn("HAL_GPIO_WritePin(GPIOA, GPIO_PIN_12, GPIO_PIN_RESET);", main)
        self.assertIn("HAL_Delay(BOOTLOADER_USB_FINAL_ACK_DELAY_MS);", main)
        self.assertIn("MX_USB_DEVICE_Init();", main)
        self.assertIn("Bootloader_UsbCdcDeInit();", main)
        self.assertIn("HAL_Delay(BOOTLOADER_USB_REENUMERATE_DELAY_MS);", main)
        self.assertIn("Bootloader_JumpToApplication();", main)
        self.assertIn("OTG_FS_IRQHandler", main)
        self.assertIn("Bootloader_UsbCdcPollFrame(&frame)", main)
        self.assertIn("Bootloader_UsbCdcSendFrame(frame_id, payload, length)", main)

    def test_application_can_request_bootloader_then_reset_after_led_blink_window(self):
        protocol = self.read("Core/Inc/app_comm_protocol.h")
        uart_header = self.read("Core/Inc/app_uart5_slave.h")
        uart_source = self.read("Core/Src/app_uart5_slave.c")
        request_header = self.read("Core/Inc/app_bootloader_request.h")
        request_source = self.read("Core/Src/app_bootloader_request.c")
        main = self.read("Core/Src/main.c")
        makefile = self.read("Makefile")

        self.assertIn("#define APP_COMM_FRAME_ID_BOOTLOADER_REQUEST 0x05U", protocol)
        self.assertIn("#define APP_COMM_FRAME_ID_BOOTLOADER_RESPONSE 0x85U", protocol)
        self.assertIn("#define APP_COMM_ERROR_CODE_AUTH 0x04U", protocol)
        self.assertIn("#define APP_UART5_SLAVE_BOOTLOADER_RESET_DELAY_TICKS 250U", uart_source)
        self.assertIn("#define APP_UART5_SLAVE_BOOTLOADER_LED_TOGGLE_TICKS 125U", uart_source)
        self.assertIn("#define APP_UART5_SLAVE_BOOTLOADER_REQUEST_LENGTH 5U", uart_source)
        self.assertIn("'w'", uart_source)
        self.assertIn("'b'", uart_source)
        self.assertIn("'8'", uart_source)
        self.assertIn("App_Uart5Slave_IsBootloaderPasswordValid", uart_source)
        self.assertIn("App_Uart5Slave_IsBootloaderResetPending", uart_header)
        self.assertIn("App_BootloaderRequest_SetFlag();", uart_source)
        self.assertIn("APP_COMM_FRAME_ID_BOOTLOADER_REQUEST", uart_source)
        self.assertIn("APP_COMM_FRAME_ID_BOOTLOADER_RESPONSE", uart_source)
        self.assertIn("APP_COMM_ERROR_CODE_AUTH", uart_source)
        self.assertIn("HAL_GPIO_TogglePin(LED_RUN_GPIO_Port, LED_RUN_Pin);", uart_source)
        self.assertIn("NVIC_SystemReset();", uart_source)
        self.assertIn("if (App_Uart5Slave_IsBootloaderResetPending() == 0U)", main)
        self.assertIn("APP_BOOTLOADER_REQUEST_MAGIC 0x424F4F54U", request_header)
        self.assertIn("RTC->BKP0R = APP_BOOTLOADER_REQUEST_MAGIC;", request_source)
        self.assertIn("RTC->BKP0R = 0U;", request_source)
        self.assertIn("PWR->CR |= PWR_CR_DBP;", request_source)
        self.assertIn("RCC->BDCR |= RCC_BDCR_RTCEN;", request_source)
        self.assertIn("Core/Src/app_bootloader_request.c", makefile)
        self.assertIn("Core/Src/app_bootloader_request.c", makefile)

    def test_bootloader_readme_documents_host_protocol(self):
        readme = self.read("README.md")

        self.assertIn("## USB CDC/UART5 Bootloader 协议", readme)
        self.assertIn("Flash 分区", readme)
        self.assertIn("通信参数", readme)
        self.assertIn("默认链路 | USB CDC `/dev/ttyACM0`", readme)
        self.assertIn("备用串口 | UART5", readme)
        self.assertIn("升级流程", readme)
        self.assertIn("0x08000000", readme)
        self.assertIn("0x08008000", readme)
        self.assertIn("HELLO", readme)
        self.assertIn("START", readme)
        self.assertIn("ERASE", readme)
        self.assertIn("WRITE", readme)
        self.assertIn("VERIFY", readme)
        self.assertIn("JUMP", readme)


if __name__ == "__main__":
    unittest.main()
