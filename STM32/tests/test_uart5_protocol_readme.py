from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Uart5ProtocolReadmeTests(unittest.TestCase):
    def test_readme_explains_uart5_protocol_in_chinese(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("## USB CDC 应用通信协议", readme)
        self.assertIn("从机节点", readme)
        self.assertIn("Jetson", readme)
        self.assertIn("115200", readme)
        self.assertIn("8N1", readme)
        self.assertIn("帧头", readme)
        self.assertIn("帧ID", readme)
        self.assertIn("数据长度", readme)
        self.assertIn("校验", readme)
        self.assertIn("CRC8", readme)
        self.assertIn("0x07", readme)
        self.assertIn("seq", readme)
        self.assertIn("AA 55", readme)
        self.assertIn("0x01", readme)
        self.assertIn("0x02", readme)
        self.assertIn("0x03", readme)
        self.assertIn("0x04", readme)
        self.assertIn("0x81", readme)
        self.assertIn("0x82", readme)
        self.assertIn("0x83", readme)
        self.assertIn("0x84", readme)
        self.assertIn("0xE1", readme)
        self.assertIn("tick(uint32 小端)", readme)
        self.assertIn("gpio_bitmap", readme)
        self.assertIn("seq + channel_id + level", readme)
        self.assertIn("seq + channel_id + result", readme)
        self.assertIn("seq + front_mm(uint16 小端) + left_mm(uint16 小端) + right_mm(uint16 小端) + valid_bitmap + error_bitmap", readme)
        self.assertIn("seq + source_frame_id + error_code", readme)
        self.assertIn("超声波", readme)
        self.assertIn("受控型", readme)
        self.assertIn("UART2", readme)
        self.assertIn("UART4", readme)
        self.assertIn("UART3", readme)
        self.assertIn("0xFFFE", readme)
        self.assertIn("0xFFFD", readme)
        self.assertIn("150ms", readme)
        self.assertIn("SIGNAL-FLASH-CTR", readme)
        self.assertIn("SIGNAL-LED", readme)
        self.assertIn("SIGNAL-BEE", readme)
        self.assertIn("SIGNAL-MOTOR", readme)
        self.assertIn("SIGNAL-FLASH", readme)
        self.assertIn("SIGNAL-SOUND", readme)
        self.assertIn("PC1", readme)
        self.assertIn("PE7", readme)
        self.assertIn("PE2", readme)
        self.assertIn("PD8", readme)
        self.assertIn("PC3", readme)
        self.assertIn("PD12", readme)
        self.assertNotIn("SIGNAL-MOROTX-SW", readme)
        self.assertNotIn("SIGNAL-RESERVED", readme)
        self.assertIn("Bootloader", readme)
        self.assertIn("编译", readme)
        self.assertIn("烧录", readme)
        self.assertIn("调试", readme)

    def test_readmes_document_fail_safe_bootloader_recovery(self):
        stm32 = (ROOT / "README.md").read_text(encoding="utf-8")
        host = (
            ROOT.parent
            / "Linux_ROS_WS/src/stm32_jetson_serial_comm/README.md"
        ).read_text(encoding="utf-8")
        qt = (ROOT.parent / "QT_Host/README.md").read_text(encoding="utf-8")

        for text in (stm32, host, qt):
            self.assertIn("352 KiB", text)
            self.assertIn("首次", text)
            self.assertIn("Bootloader", text)
        self.assertIn("0x08060000", stm32)
        self.assertIn("BOOTLOADER_STATUS", stm32)
        self.assertIn("每 1 秒", stm32)
        self.assertIn("没有有效元数据", stm32)
        self.assertIn("取消勾选", qt)
        self.assertIn("升级失败后", qt)
        self.assertIn("0x92", host)
        self.assertIn("重新发起完整升级", host)

    def test_readmes_document_ws2812_rgb_control(self):
        stm32 = (ROOT / "README.md").read_text(encoding="utf-8")
        host = (
            ROOT.parent
            / "Linux_ROS_WS/src/stm32_jetson_serial_comm/README.md"
        ).read_text(encoding="utf-8")
        qt = (ROOT.parent / "QT_Host/README.md").read_text(encoding="utf-8")

        for expected in (
            "`PD10`（`RGB_Pin`）以 GPIO 时序驱动 WS2812B",
            "三颗灯按 DIN 到 DOUT 级联",
            "它们是一个逻辑像素：三颗灯始终显示相同颜色",
            "连续发送三组相同的 24 bit GRB 数据",
            "上电默认绿色 `#00FF00`、25% 亮度、1 Hz 慢闪",
            "`docs/RGB手册.pdf` 要求 0 码高电平不超过 410 ns",
            "复位低电平配置为 125 us",
            "当前原理图没有 `PD10` 的 3.3 V -> 5 V 电平转换",
            "`74AHCT`/`74HCT` 电平转换缓冲器",
            "用示波器确认逻辑高电平和波形余量",
        ):
            self.assertIn(expected, stm32)

        for stm32_row, host_row in (
            (
                "| `0x0C` | Jetson -> STM32 | `seq + red + green + blue + brightness + mode`",
                "| 设置 | `0x0C` | `seq + red + green + blue + brightness + mode` |",
            ),
            (
                "| `0x8C` | STM32 -> Jetson | `seq + result`",
                "| 设置响应 | `0x8C` | `seq + result` |",
            ),
            (
                "| `0x0D` | Jetson -> STM32 | `seq`",
                "| 查询 | `0x0D` | `seq` |",
            ),
            (
                "| `0x8D` | STM32 -> Jetson | `seq + red + green + blue + brightness + mode + output_on`",
                "| 状态响应 | `0x8D` | `seq + red + green + blue + brightness + mode + output_on` |",
            ),
        ):
            self.assertIn(stm32_row, stm32)
            self.assertIn(host_row, host)

        for expected in (
            "基础色预设为红、绿、蓝、白、黄、青、紫、",
            "橙；马卡龙预设为樱花粉",
            "樱花粉 `#FFB7C5`、蜜桃橙 `#FFCBA4`、奶油黄 `#FFF1A8`、薄荷绿",
            "`#B8E8D0`、湖水蓝 `#A7D8F0`、薰衣草紫 `#C8B6E2`、杏仁米 `#E8D5C4`、珊瑚粉",
            "`#FF9AA2`，共 16 个预设",
            "点击预设或“自定义颜色”只修改编辑器；必须点击“应用”才发送 `0x0C` 设置帧并等待",
            "“启用状态回读”才会轮询。控制页的“RGB 状态 Hz”单独设置回读频率，默认 2 Hz",
            "QSettings 保存，并在下次启动恢复；恢复配置不会",
            "自动向 STM32 发送颜色",
            "使用示波器验收",
            "`74AHCT`/`74HCT` 电平转换缓冲器",
        ):
            self.assertIn(expected, qt)


if __name__ == "__main__":
    unittest.main()
