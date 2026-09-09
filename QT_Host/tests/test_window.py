import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QPoint, QSettings, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGroupBox

from dm31_host.core import Telemetry
from dm31_host.window import MainWindow
from stm32_jetson_serial_comm.bootloader import BootloaderStatus


class FakeWorker(QObject):
    state_changed = Signal(str, str)
    telemetry_changed = Signal(object)
    log_message = Signal(str)
    rtk_received = Signal(bytes)
    command_finished = Signal(str, bool, str)
    upgrade_progress = Signal(str, int)
    upgrade_finished = Signal(bool, str)
    bootloader_status_changed = Signal(object)

    def __init__(self):
        super().__init__()
        self.rtk_sent = []
        self.gpio_commands = []
        self.rgb_commands = []
        self.poll_settings = []

    def connect_port(self, _choice):
        pass

    def disconnect_port(self):
        pass

    def set_gpio(self, channel, level):
        self.gpio_commands.append((channel, level))

    def set_fan(self, _level):
        pass

    def set_cs1237_channel(self, _channel):
        pass

    def set_rgb(self, red, green, blue, brightness, mode):
        self.rgb_commands.append((red, green, blue, brightness, mode))

    def upgrade(self, _path, _request):
        pass

    def configure_polling(self, rates, enabled, timeout):
        self.poll_settings.append((rates, enabled, timeout))

    def send_rtk(self, data):
        self.rtk_sent.append(data)


class WindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.settings_path = Path(self.directory.name) / "settings.ini"
        self.settings = QSettings(
            str(self.settings_path),
            QSettings.IniFormat,
        )

    def tearDown(self):
        self.settings.clear()
        self.directory.cleanup()

    def test_window_has_rtk_page_gpio_values_and_bounded_rtk_display(self):
        worker = FakeWorker()
        window = MainWindow(worker, settings=self.settings)
        self.assertEqual(
            [window.tabs.tabText(index) for index in range(window.tabs.count())],
            ["总览", "实时曲线", "控制", "RGB 灯", "RTK", "固件升级与日志"],
        )
        self.assertFalse(window.rtk_page.isEnabled())
        window.on_state_changed("APPLICATION", "")
        self.assertTrue(window.rtk_page.isEnabled())
        for name in (
            "connectButton",
            "csvButton",
            "upgradeButton",
            "saveLogButton",
            "applySettingsButton",
        ):
            self.assertIsNotNone(window.findChild(QObject, name))

        window.on_telemetry(Telemetry(gpio_bitmap=0b001011))
        self.assertEqual(
            [window.values[f"gpio_{channel}"].text() for channel in range(1, 7)],
            ["开启", "开启", "关闭", "开启", "关闭", "关闭"],
        )

        window.rtk_text_input.setText("LOG VERSION")
        window._send_rtk_text()
        window.rtk_hex_input.setText("AA 55, 0x01")
        window._send_rtk_hex()
        self.assertEqual(worker.rtk_sent, [b"LOG VERSION\r\n", b"\xAA\x55\x01"])

        window.rtk_text_input.clear()
        window._send_rtk_text()
        window.rtk_text_input.setText("你好")
        try:
            window._send_rtk_text()
        except UnicodeEncodeError:
            self.fail("non-ASCII RTK text escaped the handler")
        self.assertEqual(worker.rtk_sent, [b"LOG VERSION\r\n", b"\xAA\x55\x01"])
        self.assertIn("RTK 文本: 命令不能为空", window.log_view.toPlainText())
        self.assertIn("RTK 文本:", window.log_view.toPlainText())

        worker.rtk_received.emit(b"ABC")
        self.assertEqual(window.rtk_view.toPlainText(), "ABC")
        window.rtk_mode.setCurrentText("HEX")
        self.assertEqual(window.rtk_view.toPlainText(), "41 42 43")
        window.rtk_mode.setCurrentText("文本")
        window.rtk_paused.setChecked(True)
        rendered = window.rtk_view.toPlainText()
        worker.rtk_received.emit(b"x" * 65537)
        self.assertEqual(len(window.rtk_buffer), 65536)
        self.assertEqual(bytes(window.rtk_buffer), b"x" * 65536)
        self.assertEqual(window.rtk_view.toPlainText(), rendered)
        window.rtk_paused.setChecked(False)
        self.assertEqual(window.rtk_view.toPlainText(), "x" * 65536)

        for seq in range(605):
            window.on_telemetry(
                Telemetry(
                    sample_seq=seq,
                    link_ok=True,
                    fan_level=2,
                    fan1_rpm=3000 + seq,
                    fan2_rpm=3100 + seq,
                    key_bitmap=1,
                )
            )

        self.assertEqual(window.values["fan1"].text(), "3604 RPM")
        self.assertEqual(window.values["key1"].text(), "按下")
        self.assertEqual(len(window.chart_samples["fan1"]), 600)
        window.close()

    def test_rgb_page_presets_custom_color_apply_and_readback(self):
        worker = FakeWorker()
        window = MainWindow(worker, settings=self.settings)

        self.assertEqual(len(window.rgb_preset_buttons), 16)
        window.rgb_preset_buttons["樱花粉"].click()
        window.rgb_apply_button.click()
        self.assertEqual(worker.rgb_commands[-1], (255, 183, 197, 25, 2))
        self.assertTrue(window.poll_checks["rgb"].isChecked())
        self.assertEqual(window.rate_inputs["rgb"].value(), 2.0)

        with patch(
            "dm31_host.window.QColorDialog.getColor",
            return_value=QColor("#123456"),
        ) as get_color:
            window.rgb_custom_button.click()
        get_color.assert_called_once()
        self.assertEqual(window.rgb_color.name().upper(), "#123456")
        self.assertEqual(len(worker.rgb_commands), 1)

        window.on_telemetry(Telemetry(
            rgb_red=255,
            rgb_green=183,
            rgb_blue=197,
            rgb_brightness=25,
            rgb_mode=2,
            rgb_output_on=True,
        ))
        self.assertIn("#FFB7C5", window.rgb_status_label.text())
        self.assertIn("慢闪", window.rgb_status_label.text())
        self.assertIn("亮", window.rgb_status_label.text())
        window.close()

    def test_rgb_readback_click_applies_and_persists_polling_without_rgb_send(self):
        worker = FakeWorker()
        window = MainWindow(worker, settings=self.settings)
        initial_apply_count = len(worker.poll_settings)
        window.tabs.setCurrentWidget(window.rgb_page)
        window.show()
        self.app.processEvents()

        checkbox = window.poll_checks["rgb"]
        QTest.mouseClick(checkbox, Qt.LeftButton, pos=QPoint(5, checkbox.height() // 2))

        self.assertEqual(len(worker.poll_settings), initial_apply_count + 1)
        rates, enabled, timeout = worker.poll_settings[-1]
        self.assertEqual(set(rates), set(window.rate_inputs))
        self.assertEqual(set(enabled), set(window.poll_checks))
        self.assertFalse(enabled["rgb"])
        self.assertEqual(timeout, window.timeout_input.value())
        self.settings.sync()
        self.assertFalse(self.settings.value("poll/enabled/rgb", type=bool))
        self.assertEqual(worker.rgb_commands, [])
        window.close()

        restored_worker = FakeWorker()
        restored = MainWindow(
            restored_worker,
            settings=QSettings(str(self.settings_path), QSettings.IniFormat),
        )
        self.assertFalse(restored.poll_checks["rgb"].isChecked())
        self.assertEqual(len(restored_worker.poll_settings), 1)
        self.assertFalse(restored_worker.poll_settings[0][1]["rgb"])
        self.assertEqual(restored_worker.rgb_commands, [])
        restored.close()

    def test_overview_cards_and_chart_titles_show_live_status(self):
        worker = FakeWorker()
        window = MainWindow(worker, settings=self.settings)

        self.assertEqual(window.overview.objectName(), "overviewPage")
        self.assertEqual(len(window.overview.findChildren(QGroupBox, "overviewCard")), 4)
        self.assertIn("风扇 1 --", window.charts["fan"].title())

        window.charts_paused.setChecked(True)
        window.on_telemetry(Telemetry(
            sample_seq=7,
            link_ok=True,
            gpio_bitmap=1,
            fan1_rpm=3200,
            fan2_rpm=3150,
            key_bitmap=1,
            ultrasonic_front_mm=850,
            ultrasonic_left_mm=620,
            ultrasonic_right_mm=700,
            ultrasonic_valid_bitmap=7,
            ultrasonic_error_bitmap=0,
            cs1237_raw=123456,
            cs1237_valid=True,
            cs1237_error=0,
        ))

        self.assertEqual(window.values["link"].property("status"), "good")
        self.assertEqual(window.values["gpio_1"].property("status"), "good")
        self.assertEqual(window.values["gpio_2"].property("status"), "neutral")
        self.assertEqual(
            window.charts["fan"].title(),
            "风扇转速｜风扇 1 3200 RPM · 风扇 2 3150 RPM",
        )
        self.assertEqual(
            window.charts["ultrasonic"].title(),
            "超声波距离｜前 850 mm · 左 620 mm · 右 700 mm",
        )
        self.assertEqual(window.charts["adc"].title(), "CS1237 原始值｜ADC 123456")
        self.assertEqual(len(window.chart_samples["fan1"]), 0)
        window.close()

    def test_upgrade_page_displays_bootloader_status(self):
        worker = FakeWorker()
        window = MainWindow(worker, settings=self.settings)

        worker.bootloader_status_changed.emit(BootloaderStatus(1, False, 7, 245))

        self.assertIn("RECEIVING", window.bootloader_status_label.text())
        self.assertIn("App 无效", window.bootloader_status_label.text())
        self.assertIn("0x07", window.bootloader_status_label.text())
        self.assertIn("245", window.bootloader_status_label.text())
        window.close()

    def test_poll_switches_and_chart_y_ranges_are_configurable(self):
        worker = FakeWorker()
        window = MainWindow(worker, settings=self.settings)
        self.assertEqual(
            set(window.poll_checks),
            {"status", "gpio", "ultrasonic", "cs1237", "board_io", "rgb", "rtk"},
        )
        self.assertTrue(all(checkbox.isChecked() for checkbox in window.poll_checks.values()))

        window.poll_checks["gpio"].setChecked(False)
        window._apply_settings()
        self.assertFalse(worker.poll_settings[-1][1]["gpio"])
        self.assertTrue(worker.poll_settings[-1][1]["rtk"])

        ranges = {"fan": (100, 9000), "ultrasonic": (10, 8000), "adc": (-1000, 1000)}
        for key, (minimum, maximum) in ranges.items():
            window.y_axis_inputs[key][0].setValue(minimum)
            window.y_axis_inputs[key][1].setValue(maximum)
        window._apply_y_axes()
        for key, (minimum, maximum) in ranges.items():
            self.assertEqual((window.chart_axes_y[key].min(), window.chart_axes_y[key].max()), (minimum, maximum))

        window.y_axis_inputs["fan"][0].setValue(9000)
        window.y_axis_inputs["fan"][1].setValue(9000)
        window._apply_y_axes()
        self.assertEqual((window.chart_axes_y["fan"].min(), window.chart_axes_y["fan"].max()), (100, 9000))
        self.assertIn("Y 轴范围无效：最小值必须小于最大值", window.log_view.toPlainText())
        window.close()

    def test_flash_control_is_a_200_ms_trigger_button(self):
        worker = FakeWorker()
        window = MainWindow(worker, settings=self.settings)
        window.on_state_changed("APPLICATION", "")

        window.flash_button.click()
        self.assertEqual(worker.gpio_commands, [(1, 1)])
        self.assertFalse(window.flash_button.isEnabled())
        self.assertEqual(window.flash_button.text(), "脉冲中…")

        worker.command_finished.emit("GPIO 1", True, "OK")
        QTest.qWait(220)
        self.assertTrue(window.flash_button.isEnabled())
        self.assertEqual(window.flash_button.text(), "触发爆闪切换（200 ms）")

        window.flash_button.click()
        worker.command_finished.emit("GPIO 1", False, "失败")
        self.assertTrue(window.flash_button.isEnabled())
        window.close()

    def test_old_flash_timer_cannot_finish_a_new_pulse_early(self):
        worker = FakeWorker()
        window = MainWindow(worker, settings=self.settings)
        window.on_state_changed("APPLICATION", "")
        window.flash_button.click()
        worker.command_finished.emit("GPIO 1", True, "OK")
        QTest.qWait(110)

        window.on_state_changed("DISCONNECTED", "")
        window.on_state_changed("APPLICATION", "")
        window.flash_button.click()
        worker.command_finished.emit("GPIO 1", True, "OK")
        QTest.qWait(110)
        self.assertFalse(window.flash_button.isEnabled())
        QTest.qWait(110)
        self.assertTrue(window.flash_button.isEnabled())
        window.close()

    def test_applied_settings_restore_in_a_new_window(self):
        first = MainWindow(FakeWorker(), settings=self.settings)
        enabled = {
            "status": False, "gpio": True, "ultrasonic": False,
            "cs1237": True, "board_io": False, "rgb": False, "rtk": True,
        }
        rates = {
            "status": 1.0,
            "gpio": 3.0,
            "ultrasonic": 4.0,
            "cs1237": 8.0,
            "board_io": 2.0,
            "rgb": 2.0,
        }
        ranges = {"fan": (100, 9000), "ultrasonic": (10, 8000), "adc": (-1000, 1000)}
        for key, value in enabled.items():
            first.poll_checks[key].setChecked(value)
        for key, value in rates.items():
            first.rate_inputs[key].setValue(value)
        first.rgb_preset_buttons["樱花粉"].click()
        first.rgb_brightness_input.setValue(40)
        first.rgb_mode_combo.setCurrentIndex(4)
        first.timeout_input.setValue(0.4)
        first._apply_settings()
        for key, (minimum, maximum) in ranges.items():
            first.y_axis_inputs[key][0].setValue(minimum)
            first.y_axis_inputs[key][1].setValue(maximum)
        first._apply_y_axes()
        first.settings.sync()

        script = """
import json
import sys
from PySide6.QtCore import QSettings

settings = QSettings(sys.argv[1], QSettings.IniFormat)
print(json.dumps({
    "enabled": {key: settings.value(f"poll/enabled/{key}", type=bool) for key in ("status", "gpio", "ultrasonic", "cs1237", "board_io", "rgb", "rtk")},
    "rates": {key: settings.value(f"poll/rate/{key}", type=float) for key in ("status", "gpio", "ultrasonic", "cs1237", "board_io", "rgb")},
    "timeout": settings.value("poll/timeout", type=float),
    "rgb": {key: settings.value(f"rgb/{key}", type=int) for key in ("red", "green", "blue", "brightness", "mode")},
}))
"""
        saved = json.loads(subprocess.run(
            [sys.executable, "-c", script, str(self.settings_path)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout)
        self.assertEqual(saved["enabled"], enabled)
        self.assertEqual(saved["rates"], rates)
        self.assertAlmostEqual(saved["timeout"], 0.4)
        self.assertEqual(
            saved["rgb"],
            {"red": 255, "green": 183, "blue": 197, "brightness": 40, "mode": 4},
        )
        first.close()

        worker = FakeWorker()
        restored_settings = QSettings(str(self.settings_path), QSettings.IniFormat)
        restored = MainWindow(worker, settings=restored_settings)
        self.assertEqual(
            {key: checkbox.isChecked() for key, checkbox in restored.poll_checks.items()},
            enabled,
        )
        self.assertEqual(
            {key: spin.value() for key, spin in restored.rate_inputs.items()},
            rates,
        )
        self.assertEqual(restored.timeout_input.value(), 0.4)
        self.assertEqual(restored.rgb_color.name().upper(), "#FFB7C5")
        self.assertEqual(restored.rgb_brightness_input.value(), 40)
        self.assertEqual(restored.rgb_mode_combo.currentIndex(), 4)
        self.assertEqual(worker.rgb_commands, [])
        for key, expected in ranges.items():
            self.assertEqual((restored.chart_axes_y[key].min(), restored.chart_axes_y[key].max()), expected)
        self.assertEqual(worker.poll_settings[-1], (rates, enabled, 0.4))
        restored.close()

    def test_invalid_saved_values_fall_back_without_partial_axis_restore(self):
        self.settings.setValue("poll/enabled/status", "0")
        self.settings.setValue("poll/rate/status", "invalid")
        self.settings.setValue("poll/rate/gpio", 3.0)
        self.settings.setValue("poll/rate/ultrasonic", 51.0)
        self.settings.setValue("poll/timeout", 6.0)
        self.settings.setValue("chart/fan/minimum", 9000)
        self.settings.setValue("chart/fan/maximum", 100)
        self.settings.setValue("chart/ultrasonic/minimum", 0)
        self.settings.setValue("chart/ultrasonic/maximum", 10000)
        self.settings.setValue("chart/adc/minimum", -8388608)
        self.settings.setValue("chart/adc/maximum", 8388607)
        self.settings.setValue("rgb/red", 1)
        self.settings.setValue("rgb/green", 2)
        self.settings.setValue("rgb/blue", 3)
        self.settings.setValue("rgb/brightness", 101)
        self.settings.setValue("rgb/mode", 4)
        self.settings.sync()

        window = MainWindow(FakeWorker(), settings=self.settings)
        self.assertTrue(window.poll_checks["status"].isChecked())
        self.assertEqual(window.rate_inputs["status"].value(), 0.5)
        self.assertEqual(window.rate_inputs["gpio"].value(), 3.0)
        self.assertEqual(window.rate_inputs["ultrasonic"].value(), 5.0)
        self.assertEqual(window.timeout_input.value(), 0.2)
        self.assertEqual(window.rgb_color.name().upper(), "#00FF00")
        self.assertEqual(window.rgb_brightness_input.value(), 25)
        self.assertEqual(window.rgb_mode_combo.currentIndex(), 2)
        self.assertEqual(
            (window.chart_axes_y["fan"].min(), window.chart_axes_y["fan"].max()),
            (0, 12000),
        )
        window.close()

    def test_infinite_axis_value_falls_back_to_all_default_ranges(self):
        ranges = {
            "fan": (0, 12000),
            "ultrasonic": (0, 10000),
            "adc": (-8388608, 8388607),
        }
        for key, (minimum, maximum) in ranges.items():
            self.settings.setValue(f"chart/{key}/minimum", minimum)
            self.settings.setValue(f"chart/{key}/maximum", maximum)
        self.settings.setValue("chart/ultrasonic/maximum", float("inf"))
        self.settings.sync()

        window = MainWindow(FakeWorker(), settings=self.settings)
        for key, expected in ranges.items():
            self.assertEqual((window.chart_axes_y[key].min(), window.chart_axes_y[key].max()), expected)
        window.close()


if __name__ == "__main__":
    unittest.main()
