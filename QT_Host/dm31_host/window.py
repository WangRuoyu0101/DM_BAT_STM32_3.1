"""PySide6 Widgets interface for the DM3.1 debug host."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import QPointF, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dm31_host.core import CsvRecorder, Telemetry, append_bounded, list_serial_ports
from stm32_jetson_serial_comm.serial_link_cli import parse_hex_bytes


GPIO_CHANNELS = (
    ("爆闪切换", 0x01),
    ("照明", 0x02),
    ("蜂鸣器", 0x03),
    ("导盲杆马达", 0x04),
    ("红蓝爆闪", 0x05),
    ("声音功放", 0x06),
)
RTK_DISPLAY_LIMIT = 65536
RGB_BASIC_PRESETS = (
    ("红", "#FF0000"),
    ("绿", "#00FF00"),
    ("蓝", "#0000FF"),
    ("白", "#FFFFFF"),
    ("黄", "#FFFF00"),
    ("青", "#00FFFF"),
    ("紫", "#FF00FF"),
    ("橙", "#FF8000"),
)
RGB_MACARON_PRESETS = (
    ("樱花粉", "#FFB7C5"),
    ("蜜桃橙", "#FFCBA4"),
    ("奶油黄", "#FFF1A8"),
    ("薄荷绿", "#B8E8D0"),
    ("湖水蓝", "#A7D8F0"),
    ("薰衣草紫", "#C8B6E2"),
    ("杏仁米", "#E8D5C4"),
    ("珊瑚粉", "#FF9AA2"),
)
RGB_MODES = ("关闭", "常亮", "慢闪", "中闪", "快闪")


class MainWindow(QMainWindow):
    connect_requested = Signal(object)
    disconnect_requested = Signal()
    rtk_connect_requested = Signal(object, int)
    rtk_disconnect_requested = Signal()
    gpio_requested = Signal(int, int)
    fan_requested = Signal(int)
    cs1237_requested = Signal(int)
    upgrade_requested = Signal(str, bool)
    settings_requested = Signal(object, object, float)
    rtk_send_requested = Signal(bytes)
    rgb_requested = Signal(int, int, int, int, int)

    def __init__(self, worker, rtk_worker, parent=None, settings=None):
        super().__init__(parent)
        self.worker = worker
        self.rtk_worker = rtk_worker
        self.settings = settings if settings is not None else QSettings("DM3.1", "BATDebugHost")
        self.recorder = CsvRecorder()
        self.values = {}
        self.chart_samples = {}
        self.chart_series = {}
        self.chart_axes_x = {}
        self.chart_axes_y = {}
        self.charts = {}
        self.chart_visibility = {}
        self.gpio_checks = {}
        self.poll_checks = {}
        self.rtk_buffer = bytearray()
        self.current_state = "DISCONNECTED"
        self.rtk_connected = False
        self.flash_timer = QTimer(self)
        self.flash_timer.setSingleShot(True)
        self.flash_timer.timeout.connect(self._reset_flash_button)
        self.setWindowTitle("DM3.1 STM32 调试上位机")
        self.resize(1180, 760)

        self.connect_requested.connect(worker.connect_port)
        self.disconnect_requested.connect(worker.disconnect_port)
        self.rtk_connect_requested.connect(rtk_worker.connect_port)
        self.rtk_disconnect_requested.connect(rtk_worker.disconnect_port)
        self.gpio_requested.connect(worker.set_gpio)
        self.fan_requested.connect(worker.set_fan)
        self.cs1237_requested.connect(worker.set_cs1237_channel)
        self.upgrade_requested.connect(worker.upgrade)
        self.settings_requested.connect(worker.configure_polling)
        self.rtk_send_requested.connect(rtk_worker.send)
        self.rgb_requested.connect(worker.set_rgb)
        worker.state_changed.connect(self.on_state_changed)
        worker.telemetry_changed.connect(self.on_telemetry)
        worker.log_message.connect(self.append_log)
        worker.command_finished.connect(self.on_command_finished)
        worker.upgrade_progress.connect(self.on_upgrade_progress)
        worker.upgrade_finished.connect(self.on_upgrade_finished)
        worker.bootloader_status_changed.connect(self.on_bootloader_status)
        rtk_worker.state_changed.connect(self.on_rtk_state_changed)
        rtk_worker.received.connect(self._on_rtk_received)
        rtk_worker.log_message.connect(lambda message: self.append_log(f"[RTK] {message}"))
        rtk_worker.command_finished.connect(self.on_command_finished)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addLayout(self._build_connection_bar())
        self.tabs = QTabWidget()
        self.overview = self._build_overview()
        rgb_page = self._build_rgb()
        self.tabs.addTab(self.overview, "总览")
        self.tabs.addTab(self._build_charts(), "实时曲线")
        self.tabs.addTab(self._build_controls(), "控制")
        self.tabs.addTab(rgb_page, "RGB 灯")
        self.tabs.addTab(self._build_rtk(), "RTK")
        self.tabs.addTab(self._build_upgrade(), "固件升级与日志")
        layout.addWidget(self.tabs)
        self.setCentralWidget(root)
        self._restore_settings()
        self._apply_settings()
        self.refresh_ports()
        self.on_state_changed("DISCONNECTED", "")
        self.on_rtk_state_changed("DISCONNECTED", "")

    def _build_connection_bar(self):
        layout = QVBoxLayout()
        stm32_row = QHBoxLayout()
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(360)
        refresh = QPushButton("刷新串口")
        refresh.clicked.connect(self.refresh_ports)
        self.connect_button = QPushButton("连接")
        self.connect_button.setObjectName("connectButton")
        self.connect_button.clicked.connect(self._connect_selected)
        self.disconnect_button = QPushButton("断开")
        self.disconnect_button.clicked.connect(self.disconnect_requested)
        self.state_label = QLabel("未连接")
        self.csv_button = QPushButton("开始 CSV")
        self.csv_button.setObjectName("csvButton")
        self.csv_button.clicked.connect(self._toggle_csv)
        stm32_row.addWidget(QLabel("STM32 USB CDC："))
        stm32_row.addWidget(self.port_combo, 1)
        stm32_row.addWidget(refresh)
        stm32_row.addWidget(self.connect_button)
        stm32_row.addWidget(self.disconnect_button)
        stm32_row.addWidget(self.state_label)
        stm32_row.addWidget(self.csv_button)
        layout.addLayout(stm32_row)

        rtk_row = QHBoxLayout()
        self.rtk_port_combo = QComboBox()
        self.rtk_port_combo.setMinimumWidth(360)
        self.rtk_baud_combo = QComboBox()
        self.rtk_baud_combo.addItems(("921600", "115200"))
        self.rtk_connect_button = QPushButton("连接 RTK")
        self.rtk_connect_button.clicked.connect(self._connect_rtk_selected)
        self.rtk_disconnect_button = QPushButton("断开 RTK")
        self.rtk_disconnect_button.clicked.connect(self.rtk_disconnect_requested)
        self.rtk_state_label = QLabel("未连接")
        rtk_row.addWidget(QLabel("RTK CH343P："))
        rtk_row.addWidget(self.rtk_port_combo, 1)
        rtk_row.addWidget(QLabel("波特率："))
        rtk_row.addWidget(self.rtk_baud_combo)
        rtk_row.addWidget(self.rtk_connect_button)
        rtk_row.addWidget(self.rtk_disconnect_button)
        rtk_row.addWidget(self.rtk_state_label)
        layout.addLayout(rtk_row)
        return layout

    def _value_group(self, title, rows):
        box = QGroupBox(title)
        box.setObjectName("overviewCard")
        form = QFormLayout(box)
        for key, label in rows:
            value = QLabel("--")
            value.setObjectName("overviewValue")
            value.setProperty("status", "neutral")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.values[key] = value
            form.addRow(label, value)
        return box

    def _build_overview(self):
        page = QWidget()
        page.setObjectName("overviewPage")
        page.setStyleSheet("""
            QWidget#overviewPage {
                background: #F3F6FA;
            }
            QGroupBox#overviewCard {
                background: white;
                border: 1px solid #DCE4EE;
                border-radius: 10px;
                margin-top: 14px;
                padding: 14px;
                font-size: 15px;
                font-weight: 600;
                color: #245D9B;
            }
            QGroupBox#overviewCard::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
            }
            QLabel#overviewValue {
                color: #526170;
                font-size: 16px;
                font-weight: 600;
                padding: 3px 8px;
            }
            QLabel#overviewValue[status="good"] { color: #16845B; }
            QLabel#overviewValue[status="bad"] { color: #C43D4B; }
            QLabel#overviewValue[status="neutral"] { color: #526170; }
        """)
        grid = QGridLayout(page)
        grid.setContentsMargins(18, 18, 18, 18)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        gpio_rows = tuple((f"gpio_{channel}", name) for name, channel in GPIO_CHANNELS)
        grid.addWidget(self._value_group("连接与 GPIO", (("link", "链路"),) + gpio_rows), 0, 0)
        grid.addWidget(
            self._value_group(
                "风扇与按键",
                (
                    ("fan_level", "档位"),
                    ("fan1", "风扇 1"),
                    ("fan2", "风扇 2"),
                    ("key1", "KEY1"),
                    ("key2", "KEY2"),
                    ("key3", "KEY3"),
                ),
            ),
            0,
            1,
        )
        grid.addWidget(
            self._value_group(
                "超声波",
                (("front", "前"), ("left", "左"), ("right", "右"), ("ultra_flags", "状态")),
            ),
            1,
            0,
        )
        grid.addWidget(
            self._value_group(
                "CS1237",
                (("adc_raw", "原始值"), ("adc_channel", "通道"), ("adc_state", "状态")),
            ),
            1,
            1,
        )
        return page

    def _chart(self, axis_key, title, names, minimum, maximum):
        chart = QChart()
        chart.setTitle(f"{title}｜" + " · ".join(f"{label} --" for _key, label in names))
        self.charts[axis_key] = chart
        x_axis = QValueAxis()
        x_axis.setRange(0, 600)
        x_axis.setLabelFormat("%d")
        y_axis = QValueAxis()
        y_axis.setRange(minimum, maximum)
        self.chart_axes_y[axis_key] = y_axis
        chart.addAxis(x_axis, Qt.AlignBottom)
        chart.addAxis(y_axis, Qt.AlignLeft)
        for key, label in names:
            series = QLineSeries()
            series.setName(label)
            chart.addSeries(series)
            series.attachAxis(x_axis)
            series.attachAxis(y_axis)
            self.chart_samples[key] = deque()
            self.chart_series[key] = series
            self.chart_axes_x[key] = x_axis
            toggle = QCheckBox(f"{title}: {label}")
            toggle.setChecked(True)
            toggle.toggled.connect(series.setVisible)
            self.chart_visibility[key] = toggle
            self.chart_toggle_layout.addWidget(toggle)
        view = QChartView(chart)
        view.setRenderHint(QPainter.Antialiasing)
        view.setMinimumHeight(220)
        return view

    def _build_charts(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        self.charts_paused = QCheckBox("暂停曲线")
        clear = QPushButton("清空")
        clear.clicked.connect(self._clear_charts)
        toolbar = QHBoxLayout()
        self.chart_toggle_layout = toolbar
        toolbar.addWidget(self.charts_paused)
        toolbar.addWidget(clear)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        axis_box = QGroupBox("Y 轴范围")
        axis_layout = QGridLayout(axis_box)
        axis_layout.addWidget(QLabel("曲线"), 0, 0)
        axis_layout.addWidget(QLabel("下限"), 0, 1)
        axis_layout.addWidget(QLabel("上限"), 0, 2)
        self.y_axis_inputs = {}
        for row, (key, label, minimum, maximum) in enumerate((
            ("fan", "风扇转速", 0, 12000),
            ("ultrasonic", "超声波距离", 0, 10000),
            ("adc", "CS1237 原始值", -8388608, 8388607),
        ), start=1):
            minimum_input = QSpinBox()
            maximum_input = QSpinBox()
            for spin in (minimum_input, maximum_input):
                spin.setRange(-2147483648, 2147483647)
            minimum_input.setValue(minimum)
            maximum_input.setValue(maximum)
            self.y_axis_inputs[key] = (minimum_input, maximum_input)
            axis_layout.addWidget(QLabel(label), row, 0)
            axis_layout.addWidget(minimum_input, row, 1)
            axis_layout.addWidget(maximum_input, row, 2)
        apply_axes = QPushButton("应用 Y 轴")
        apply_axes.clicked.connect(self._apply_y_axes)
        axis_layout.addWidget(apply_axes, 1, 3, 3, 1)
        layout.addWidget(axis_box)

        layout.addWidget(self._chart("fan", "风扇转速", (("fan1", "风扇 1"), ("fan2", "风扇 2")), 0, 12000))
        layout.addWidget(
            self._chart(
                "ultrasonic",
                "超声波距离",
                (("front", "前"), ("left", "左"), ("right", "右")),
                0,
                10000,
            )
        )
        layout.addWidget(self._chart("adc", "CS1237 原始值", (("adc", "ADC"),), -8388608, 8388607))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        return scroll

    def _build_rgb(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.rgb_preset_buttons = {}
        for title, presets in (
            ("基础色", RGB_BASIC_PRESETS),
            ("马卡龙色", RGB_MACARON_PRESETS),
        ):
            box = QGroupBox(title)
            grid = QGridLayout(box)
            for index, (name, hex_color) in enumerate(presets):
                button = QPushButton(name)
                button.clicked.connect(
                    lambda _checked=False, value=hex_color: self._set_rgb_color(QColor(value))
                )
                self.rgb_preset_buttons[name] = button
                grid.addWidget(button, index // 4, index % 4)
            layout.addWidget(box)

        editor = QGroupBox("编辑")
        form = QFormLayout(editor)
        self.rgb_color = QColor("#00FF00")
        self.rgb_color_preview = QLabel()
        self.rgb_custom_button = QPushButton("自定义颜色")
        self.rgb_custom_button.clicked.connect(self._choose_rgb_color)
        color_row = QWidget()
        color_layout = QHBoxLayout(color_row)
        color_layout.setContentsMargins(0, 0, 0, 0)
        color_layout.addWidget(self.rgb_color_preview, 1)
        color_layout.addWidget(self.rgb_custom_button)
        form.addRow("颜色", color_row)
        self.rgb_brightness_input = QSpinBox()
        self.rgb_brightness_input.setRange(0, 100)
        self.rgb_brightness_input.setValue(25)
        self.rgb_brightness_input.setSuffix("%")
        form.addRow("亮度", self.rgb_brightness_input)
        self.rgb_mode_combo = QComboBox()
        self.rgb_mode_combo.addItems(RGB_MODES)
        self.rgb_mode_combo.setCurrentIndex(2)
        form.addRow("模式", self.rgb_mode_combo)
        self.rgb_apply_button = QPushButton("应用")
        self.rgb_apply_button.clicked.connect(self._apply_rgb)
        form.addRow(self.rgb_apply_button)
        self.poll_checks["rgb"] = QCheckBox("启用状态回读")
        self.poll_checks["rgb"].setChecked(True)
        self.poll_checks["rgb"].clicked.connect(self._apply_settings)
        form.addRow(self.poll_checks["rgb"])
        layout.addWidget(editor)

        status = QGroupBox("实际状态")
        status_layout = QVBoxLayout(status)
        self.rgb_status_label = QLabel("--")
        status_layout.addWidget(self.rgb_status_label)
        layout.addWidget(status)
        layout.addStretch()
        self._update_rgb_preview()
        self.rgb_brightness_input.valueChanged.connect(self._save_rgb_editor)
        self.rgb_mode_combo.currentIndexChanged.connect(self._save_rgb_editor)
        self.rgb_page = page
        return page

    def _build_controls(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        gpio_box = QGroupBox("GPIO 输出")
        gpio_layout = QGridLayout(gpio_box)
        self.flash_button = QPushButton("触发爆闪切换（200 ms）")
        self.flash_button.clicked.connect(self._trigger_flash)
        gpio_layout.addWidget(self.flash_button, 0, 0)
        for index, (name, channel) in enumerate(GPIO_CHANNELS[1:], start=1):
            checkbox = QCheckBox(name)
            checkbox.toggled.connect(
                lambda checked, channel=channel: self.gpio_requested.emit(channel, int(checked))
            )
            self.gpio_checks[channel] = checkbox
            gpio_layout.addWidget(checkbox, index // 3, index % 3)
        layout.addWidget(gpio_box)

        fan_box = QGroupBox("风扇档位")
        fan_layout = QHBoxLayout(fan_box)
        for level, percent in enumerate((25, 50, 75, 100), start=1):
            button = QPushButton(f"{level} 档 ({percent}%)")
            button.clicked.connect(lambda _checked=False, level=level: self.fan_requested.emit(level))
            fan_layout.addWidget(button)
        layout.addWidget(fan_box)

        adc_box = QGroupBox("CS1237 通道")
        adc_layout = QHBoxLayout(adc_box)
        for channel, name in ((0, "压力"), (2, "温度")):
            button = QPushButton(name)
            button.clicked.connect(
                lambda _checked=False, channel=channel: self.cs1237_requested.emit(channel)
            )
            adc_layout.addWidget(button)
        layout.addWidget(adc_box)

        settings_box = QGroupBox("轮询与超时")
        settings_form = QFormLayout(settings_box)
        self.rate_inputs = {}
        defaults = (
            ("status", "状态 Hz", 0.5),
            ("gpio", "GPIO Hz", 1.0),
            ("ultrasonic", "超声波 Hz", 5.0),
            ("cs1237", "CS1237 Hz", 10.0),
            ("board_io", "板载 IO Hz", 2.0),
        )
        for key, label, value in defaults:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            enabled = QCheckBox("启用")
            enabled.setChecked(True)
            spin = QDoubleSpinBox()
            spin.setRange(0.1, 50.0)
            spin.setValue(value)
            row_layout.addWidget(enabled)
            row_layout.addWidget(spin)
            self.poll_checks[key] = enabled
            self.rate_inputs[key] = spin
            settings_form.addRow(label, row)
        rgb_rate = QDoubleSpinBox()
        rgb_rate.setRange(0.1, 50.0)
        rgb_rate.setValue(2.0)
        self.rate_inputs["rgb"] = rgb_rate
        settings_form.addRow("RGB 状态 Hz", rgb_rate)
        self.timeout_input = QDoubleSpinBox()
        self.timeout_input.setRange(0.05, 5.0)
        self.timeout_input.setSingleStep(0.05)
        self.timeout_input.setValue(0.2)
        settings_form.addRow("串口超时 s", self.timeout_input)
        apply_settings = QPushButton("应用设置")
        apply_settings.setObjectName("applySettingsButton")
        apply_settings.clicked.connect(self._apply_settings)
        settings_form.addRow(apply_settings)
        layout.addWidget(settings_box)
        layout.addStretch()
        self.control_page = page
        return page

    def _build_rtk(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        text_row = QHBoxLayout()
        self.rtk_text_input = QLineEdit()
        text_send = QPushButton("发送文本")
        self.rtk_text_send_button = text_send
        text_send.clicked.connect(self._send_rtk_text)
        text_row.addWidget(self.rtk_text_input, 1)
        text_row.addWidget(text_send)
        hex_row = QHBoxLayout()
        self.rtk_hex_input = QLineEdit()
        hex_send = QPushButton("发送 HEX")
        self.rtk_hex_send_button = hex_send
        hex_send.clicked.connect(self._send_rtk_hex)
        hex_row.addWidget(self.rtk_hex_input, 1)
        hex_row.addWidget(hex_send)
        toolbar = QHBoxLayout()
        self.rtk_mode = QComboBox()
        self.rtk_mode.addItems(("文本", "HEX"))
        self.rtk_mode.currentTextChanged.connect(lambda _mode: self._render_rtk())
        self.rtk_paused = QCheckBox("暂停显示")
        self.rtk_paused.toggled.connect(lambda paused: not paused and self._render_rtk())
        clear = QPushButton("清空")
        clear.clicked.connect(self._clear_rtk)
        toolbar.addWidget(self.rtk_mode)
        toolbar.addWidget(self.rtk_paused)
        toolbar.addWidget(clear)
        toolbar.addStretch()
        self.rtk_view = QPlainTextEdit()
        self.rtk_view.setReadOnly(True)
        layout.addLayout(text_row)
        layout.addLayout(hex_row)
        layout.addLayout(toolbar)
        layout.addWidget(self.rtk_view, 1)
        self.rtk_page = page
        return page

    def _build_upgrade(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        self.image_path = QLineEdit()
        browse = QPushButton("选择固件")
        browse.clicked.connect(self._browse_image)
        self.request_from_app = QCheckBox("从运行态请求进入 bootloader")
        self.request_from_app.setChecked(True)
        self.upgrade_button = QPushButton("开始升级")
        self.upgrade_button.setObjectName("upgradeButton")
        self.upgrade_button.clicked.connect(self._start_upgrade)
        row.addWidget(self.image_path, 1)
        row.addWidget(browse)
        row.addWidget(self.request_from_app)
        row.addWidget(self.upgrade_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.bootloader_status_label = QLabel("Bootloader 状态：--")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        save_log = QPushButton("保存日志")
        save_log.setObjectName("saveLogButton")
        save_log.clicked.connect(self._save_log)
        layout.addLayout(row)
        layout.addWidget(self.bootloader_status_label)
        layout.addWidget(self.progress)
        layout.addWidget(save_log)
        layout.addWidget(self.log_view, 1)
        return page

    def refresh_ports(self):
        current = self.port_combo.currentData()
        current_rtk = self.rtk_port_combo.currentData()
        self.port_combo.clear()
        self.rtk_port_combo.clear()
        try:
            choices = list_serial_ports()
        except Exception as exc:
            self.append_log(f"串口枚举失败: {exc}")
            choices = []
        for choice in choices:
            self.port_combo.addItem(str(choice), choice)
            self.rtk_port_combo.addItem(str(choice), choice)
        if current:
            index = next(
                (i for i in range(self.port_combo.count()) if self.port_combo.itemData(i).device == current.device),
                -1,
            )
            self.port_combo.setCurrentIndex(index)
        else:
            index = next(
                (i for i, choice in enumerate(choices) if (choice.vid, choice.pid) == (0x0483, 0x5740)),
                -1,
            )
            self.port_combo.setCurrentIndex(index)
        if current_rtk:
            index = next(
                (i for i in range(self.rtk_port_combo.count()) if self.rtk_port_combo.itemData(i).device == current_rtk.device),
                -1,
            )
        else:
            index = next(
                (i for i, choice in enumerate(choices) if (choice.vid, choice.pid) == (0x1A86, 0x55D3)),
                -1,
            )
        self.rtk_port_combo.setCurrentIndex(index)

    def _connect_selected(self):
        choice = self.port_combo.currentData()
        if choice is not None:
            self.connect_requested.emit(choice)

    def _connect_rtk_selected(self):
        choice = self.rtk_port_combo.currentData()
        if choice is not None:
            baudrate = int(self.rtk_baud_combo.currentText())
            self.settings.setValue("rtk/baudrate", baudrate)
            self._sync_settings()
            self.rtk_connect_requested.emit(choice, baudrate)

    def _toggle_csv(self):
        if self.recorder.active:
            self.recorder.stop()
            self.csv_button.setText("开始 CSV")
            self.append_log("CSV 记录已停止")
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存遥测 CSV", "dm31_telemetry.csv", "CSV (*.csv)")
        if path:
            self.recorder.start(path)
            self.csv_button.setText("停止 CSV")
            self.append_log(f"CSV 记录: {path}")

    def _browse_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 STM32 固件", "", "Binary (*.bin)")
        if path:
            self.image_path.setText(path)

    def _start_upgrade(self):
        path = self.image_path.text().strip()
        if not path or not Path(path).is_file():
            self.append_log("请选择有效的 .bin 固件")
            return
        self.upgrade_requested.emit(path, self.request_from_app.isChecked())

    def _apply_settings(self):
        rates = {key: spin.value() for key, spin in self.rate_inputs.items()}
        enabled = {key: checkbox.isChecked() for key, checkbox in self.poll_checks.items()}
        self.settings_requested.emit(rates, enabled, self.timeout_input.value())
        for key, value in enabled.items():
            self.settings.setValue(f"poll/enabled/{key}", value)
        for key, value in rates.items():
            self.settings.setValue(f"poll/rate/{key}", value)
        self.settings.setValue("poll/timeout", self.timeout_input.value())
        self._sync_settings()

    def _set_rgb_color(self, color, persist=True):
        self.rgb_color = color
        self._update_rgb_preview()
        if persist:
            self._save_rgb_editor()

    def _update_rgb_preview(self):
        hex_color = self.rgb_color.name().upper()
        self.rgb_color_preview.setText(hex_color)
        self.rgb_color_preview.setStyleSheet(
            f"background: {hex_color}; border: 1px solid #808080; padding: 6px;"
        )

    def _choose_rgb_color(self):
        color = QColorDialog.getColor(self.rgb_color, self, "选择 RGB 颜色")
        if color.isValid():
            self._set_rgb_color(color)

    def _save_rgb_editor(self):
        for key, value in (
            ("red", self.rgb_color.red()),
            ("green", self.rgb_color.green()),
            ("blue", self.rgb_color.blue()),
            ("brightness", self.rgb_brightness_input.value()),
            ("mode", self.rgb_mode_combo.currentIndex()),
        ):
            self.settings.setValue(f"rgb/{key}", value)
        self._sync_settings()

    def _apply_rgb(self):
        self.rgb_requested.emit(
            self.rgb_color.red(),
            self.rgb_color.green(),
            self.rgb_color.blue(),
            self.rgb_brightness_input.value(),
            self.rgb_mode_combo.currentIndex(),
        )

    def _apply_y_axes(self):
        ranges = {
            key: (minimum.value(), maximum.value())
            for key, (minimum, maximum) in self.y_axis_inputs.items()
        }
        if any(minimum >= maximum for minimum, maximum in ranges.values()):
            self.append_log("Y 轴范围无效：最小值必须小于最大值")
            return
        for key, (minimum, maximum) in ranges.items():
            self.chart_axes_y[key].setRange(minimum, maximum)
            self.settings.setValue(f"chart/{key}/minimum", minimum)
            self.settings.setValue(f"chart/{key}/maximum", maximum)
        self._sync_settings()

    def _restore_settings(self):
        baudrate = str(self.settings.value("rtk/baudrate", "921600"))
        index = self.rtk_baud_combo.findText(baudrate)
        self.rtk_baud_combo.setCurrentIndex(index if index >= 0 else 0)

        for key, checkbox in self.poll_checks.items():
            default = checkbox.isChecked()
            value = self.settings.value(f"poll/enabled/{key}", default)
            if isinstance(value, bool):
                checkbox.setChecked(value)
            elif isinstance(value, str) and value.lower() in ("true", "false"):
                checkbox.setChecked(value.lower() == "true")
            else:
                checkbox.setChecked(default)

        number_inputs = {**self.rate_inputs, "timeout": self.timeout_input}
        for key, spin in number_inputs.items():
            setting_key = "poll/timeout" if key == "timeout" else f"poll/rate/{key}"
            default = spin.value()
            try:
                value = float(self.settings.value(setting_key, default))
            except (TypeError, ValueError):
                value = default
            spin.setValue(value if spin.minimum() <= value <= spin.maximum() else default)

        rgb_keys = ("red", "green", "blue", "brightness", "mode")
        if all(self.settings.contains(f"rgb/{key}") for key in rgb_keys):
            try:
                red, green, blue, brightness, mode = (
                    int(self.settings.value(f"rgb/{key}")) for key in rgb_keys
                )
            except (OverflowError, TypeError, ValueError):
                pass
            else:
                if (
                    all(0 <= value <= 255 for value in (red, green, blue))
                    and 0 <= brightness <= 100
                    and 0 <= mode < len(RGB_MODES)
                ):
                    self._set_rgb_color(QColor(red, green, blue), persist=False)
                    self.rgb_brightness_input.blockSignals(True)
                    self.rgb_mode_combo.blockSignals(True)
                    self.rgb_brightness_input.setValue(brightness)
                    self.rgb_mode_combo.setCurrentIndex(mode)
                    self.rgb_brightness_input.blockSignals(False)
                    self.rgb_mode_combo.blockSignals(False)

        keys = tuple(self.y_axis_inputs)
        required = tuple(
            f"chart/{key}/{bound}"
            for key in keys
            for bound in ("minimum", "maximum")
        )
        if not all(self.settings.contains(key) for key in required):
            return
        try:
            ranges = {
                key: (
                    int(self.settings.value(f"chart/{key}/minimum")),
                    int(self.settings.value(f"chart/{key}/maximum")),
                )
                for key in keys
            }
        except (OverflowError, TypeError, ValueError):
            return
        if any(
            minimum >= maximum
            or minimum < self.y_axis_inputs[key][0].minimum()
            or maximum > self.y_axis_inputs[key][1].maximum()
            for key, (minimum, maximum) in ranges.items()
        ):
            return
        for key, (minimum, maximum) in ranges.items():
            self.y_axis_inputs[key][0].setValue(minimum)
            self.y_axis_inputs[key][1].setValue(maximum)
            self.chart_axes_y[key].setRange(minimum, maximum)

    def _sync_settings(self):
        self.settings.sync()
        if self.settings.status() != QSettings.NoError:
            self.append_log("配置保存失败")

    def _trigger_flash(self):
        self.flash_timer.stop()
        self.flash_button.setText("脉冲中…")
        self.flash_button.setEnabled(False)
        self.gpio_requested.emit(1, 1)

    def _reset_flash_button(self):
        self.flash_button.setText("触发爆闪切换（200 ms）")
        self.flash_button.setEnabled(self.current_state == "APPLICATION")

    def _save_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存通信日志", "dm31_serial.log", "Log (*.log *.txt)")
        if path:
            Path(path).write_text(self.log_view.toPlainText() + "\n", encoding="utf-8")

    def _clear_charts(self):
        for key, samples in self.chart_samples.items():
            samples.clear()
            self.chart_series[key].clear()

    def _send_rtk_text(self):
        command = self.rtk_text_input.text()
        try:
            if not command:
                raise ValueError("命令不能为空")
            self.rtk_send_requested.emit(command.rstrip("\r\n").encode("ascii") + b"\r\n")
        except (UnicodeEncodeError, ValueError) as exc:
            self.append_log(f"RTK 文本: {exc}")

    def _send_rtk_hex(self):
        try:
            data = parse_hex_bytes(self.rtk_hex_input.text())
            if not data:
                raise ValueError("HEX 数据不能为空")
            self.rtk_send_requested.emit(data)
        except ValueError as exc:
            self.append_log(f"RTK HEX: {exc}")

    def _clear_rtk(self):
        self.rtk_buffer.clear()
        self._render_rtk()

    def _on_rtk_received(self, data):
        self.rtk_buffer.extend(data)
        del self.rtk_buffer[:-RTK_DISPLAY_LIMIT]
        if not self.rtk_paused.isChecked():
            self._render_rtk()

    def _render_rtk(self):
        data = bytes(self.rtk_buffer)
        text = data.hex(" ").upper() if self.rtk_mode.currentText() == "HEX" else data.decode("ascii", errors="replace")
        self.rtk_view.setPlainText(text)

    def _plot(self, key, sample_seq, value):
        if value is None or self.charts_paused.isChecked():
            return
        samples = self.chart_samples[key]
        append_bounded(samples, (sample_seq, value))
        self.chart_series[key].replace([QPointF(x, y) for x, y in samples])
        self.chart_axes_x[key].setRange(max(0, sample_seq - 599), max(600, sample_seq))

    def _set_overview_value(self, key, text, status="neutral"):
        label = self.values[key]
        label.setText(text)
        if label.property("status") != status:
            label.setProperty("status", status)
            label.style().unpolish(label)
            label.style().polish(label)

    def _update_chart_titles(self):
        self.charts["fan"].setTitle(
            f"风扇转速｜风扇 1 {self.values['fan1'].text()} · 风扇 2 {self.values['fan2'].text()}"
        )
        self.charts["ultrasonic"].setTitle(
            f"超声波距离｜前 {self.values['front'].text()} · 左 {self.values['left'].text()} · "
            f"右 {self.values['right'].text()}"
        )
        self.charts["adc"].setTitle(f"CS1237 原始值｜ADC {self.values['adc_raw'].text()}")

    def on_telemetry(self, telemetry: Telemetry):
        self._set_overview_value(
            "link",
            "在线" if telemetry.link_ok else "离线",
            "good" if telemetry.link_ok else "bad",
        )
        for _name, channel in GPIO_CHANNELS:
            text = "--" if telemetry.gpio_bitmap is None else (
                "开启" if telemetry.gpio_bitmap & (1 << (channel - 1)) else "关闭"
            )
            status = "neutral" if telemetry.gpio_bitmap is None else (
                "good" if telemetry.gpio_bitmap & (1 << (channel - 1)) else "neutral"
            )
            self._set_overview_value(f"gpio_{channel}", text, status)
        self.values["fan_level"].setText("--" if telemetry.fan_level is None else str(telemetry.fan_level))
        self.values["fan1"].setText("--" if telemetry.fan1_rpm is None else f"{telemetry.fan1_rpm} RPM")
        self.values["fan2"].setText("--" if telemetry.fan2_rpm is None else f"{telemetry.fan2_rpm} RPM")
        bitmap = telemetry.key_bitmap or 0
        self._set_overview_value("key1", "按下" if bitmap & 1 else "释放", "good" if bitmap & 1 else "neutral")
        self._set_overview_value("key2", "按下" if bitmap & 2 else "释放", "good" if bitmap & 2 else "neutral")
        self._set_overview_value("key3", "按下" if bitmap & 4 else "释放", "good" if bitmap & 4 else "neutral")
        for key, value in (
            ("front", telemetry.ultrasonic_front_mm),
            ("left", telemetry.ultrasonic_left_mm),
            ("right", telemetry.ultrasonic_right_mm),
        ):
            self.values[key].setText("--" if value is None else f"{value} mm")
        if telemetry.ultrasonic_valid_bitmap is None:
            self._set_overview_value("ultra_flags", "--")
        else:
            ultrasonic_error = telemetry.ultrasonic_error_bitmap or 0
            self._set_overview_value(
                "ultra_flags",
                f"valid=0x{telemetry.ultrasonic_valid_bitmap:02X} "
                f"error=0x{ultrasonic_error:02X}",
                "bad" if ultrasonic_error else "good",
            )
        self.values["adc_raw"].setText("--" if telemetry.cs1237_raw is None else str(telemetry.cs1237_raw))
        self.values["adc_channel"].setText("--" if telemetry.cs1237_channel is None else str(telemetry.cs1237_channel))
        if telemetry.cs1237_valid is None:
            self._set_overview_value("adc_state", "--")
        else:
            adc_error = telemetry.cs1237_error or 0
            adc_good = telemetry.cs1237_valid and not adc_error
            self._set_overview_value(
                "adc_state",
                f"{'有效' if telemetry.cs1237_valid else '无效'} / error={telemetry.cs1237_error}",
                "good" if adc_good else "bad",
            )
        if telemetry.gpio_bitmap is not None:
            for channel, checkbox in self.gpio_checks.items():
                checkbox.blockSignals(True)
                checkbox.setChecked(bool(telemetry.gpio_bitmap & (1 << (channel - 1))))
                checkbox.blockSignals(False)
        rgb_values = (
            telemetry.rgb_red,
            telemetry.rgb_green,
            telemetry.rgb_blue,
            telemetry.rgb_brightness,
            telemetry.rgb_mode,
            telemetry.rgb_output_on,
        )
        if all(value is not None for value in rgb_values):
            red, green, blue, brightness, mode, output_on = rgb_values
            hex_color = QColor(red, green, blue).name().upper()
            mode_name = RGB_MODES[mode] if 0 <= mode < len(RGB_MODES) else f"未知({mode})"
            self.rgb_status_label.setText(
                f"<span style='color: {hex_color}'>■</span> {hex_color} | "
                f"亮度 {brightness}% | {mode_name} | {'亮' if output_on else '灭'}"
            )
        self._update_chart_titles()
        for key, value in (
            ("fan1", telemetry.fan1_rpm),
            ("fan2", telemetry.fan2_rpm),
            ("front", telemetry.ultrasonic_front_mm),
            ("left", telemetry.ultrasonic_left_mm),
            ("right", telemetry.ultrasonic_right_mm),
            ("adc", telemetry.cs1237_raw),
        ):
            self._plot(key, telemetry.sample_seq, value)
        self.recorder.write(telemetry)

    def on_state_changed(self, state, detail):
        self.current_state = state
        self.flash_timer.stop()
        labels = {
            "DISCONNECTED": "未连接",
            "APPLICATION": "应用模式",
            "BOOTLOADER": "Bootloader",
            "UPGRADING": "升级中",
        }
        self.state_label.setText(f"{labels.get(state, state)} {detail}".strip())
        application = state == "APPLICATION"
        upgrading = state == "UPGRADING"
        self.connect_button.setEnabled(state == "DISCONNECTED")
        self.disconnect_button.setEnabled(state != "DISCONNECTED" and not upgrading)
        self.control_page.setEnabled(application)
        self.upgrade_button.setEnabled(state in ("APPLICATION", "BOOTLOADER"))
        self._reset_flash_button()
        if state == "BOOTLOADER":
            self.request_from_app.setChecked(False)

    def on_rtk_state_changed(self, state, detail):
        self.rtk_connected = state == "CONNECTED"
        self.rtk_state_label.setText(f"{'已连接' if self.rtk_connected else '未连接'} {detail}".strip())
        self.rtk_connect_button.setEnabled(not self.rtk_connected)
        self.rtk_disconnect_button.setEnabled(self.rtk_connected)
        self.rtk_text_send_button.setEnabled(self.rtk_connected)
        self.rtk_hex_send_button.setEnabled(self.rtk_connected)

    def append_log(self, message):
        timestamp = datetime.now().astimezone().strftime("%H:%M:%S.%f")[:-3]
        self.log_view.appendPlainText(f"[{timestamp}] {message}")

    def on_command_finished(self, name, ok, detail):
        self.append_log(f"{name}: {'OK' if ok else 'FAIL'} {detail}")
        self.statusBar().showMessage(f"{name}: {detail}", 5000)
        if name == "GPIO 1":
            if ok:
                self.flash_timer.start(200)
            else:
                self.flash_timer.stop()
                self._reset_flash_button()

    def on_upgrade_progress(self, stage, percent):
        self.progress.setValue(percent)
        self.append_log(stage)

    def on_bootloader_status(self, status):
        state = {
            0: "WAITING",
            1: "RECEIVING",
            2: "VERIFIED",
            3: "ERROR",
        }.get(status.state, f"UNKNOWN({status.state})")
        app = "App 有效" if status.app_valid else "App 无效"
        self.bootloader_status_label.setText(
            f"Bootloader 状态：{state} | {app} | 错误 0x{status.last_error:02X} | 已接收 {status.received_bytes} 字节"
        )

    def on_upgrade_finished(self, ok, detail):
        self.append_log(f"升级{'完成' if ok else '失败'}: {detail}")
        self.statusBar().showMessage(detail, 10000)

    def closeEvent(self, event):
        if self.current_state == "UPGRADING":
            self.append_log("固件升级期间不能关闭程序")
            event.ignore()
            return
        self.recorder.stop()
        self.disconnect_requested.emit()
        super().closeEvent(event)
