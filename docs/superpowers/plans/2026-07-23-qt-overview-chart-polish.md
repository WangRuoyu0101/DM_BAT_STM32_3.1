# Qt Overview and Live Chart Titles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 美化 Qt 总览页，并让三组曲线标题持续显示最新遥测值。

**Architecture:** 保留现有 `MainWindow` 和遥测更新入口。使用 Qt 样式表与标签动态属性完成卡片和状态着色，直接复用总览标签已经格式化的文本生成曲线标题。

**Tech Stack:** Python 3、PySide6 Widgets、PySide6 QtCharts、unittest

## Global Constraints

- 不改变通信、轮询和 `Telemetry` 数据结构。
- 不增加依赖、自定义绘制控件、主题系统、动画或外部图标。
- 暂停曲线时仍更新实时值标题；清空历史点不清除标题。
- 只修改 `QT_Host/dm31_host/window.py` 和 `QT_Host/tests/test_window.py`。

---

### Task 1: 总览卡片与实时曲线标题

**Files:**
- Modify: `QT_Host/tests/test_window.py`
- Modify: `QT_Host/dm31_host/window.py`

**Interfaces:**
- Consumes: `MainWindow.on_telemetry(telemetry: Telemetry) -> None`
- Produces: `MainWindow.charts: dict[str, QChart]`、动态标签属性 `status`（`good`、`bad`、`neutral`）

- [ ] **Step 1: 写入失败测试**

在现有 `WindowTest` 中新增一个测试：

```python
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
    self.assertEqual(window.charts["fan"].title(),
                     "风扇转速｜风扇 1 3200 RPM · 风扇 2 3150 RPM")
    self.assertEqual(window.charts["ultrasonic"].title(),
                     "超声波距离｜前 850 mm · 左 620 mm · 右 700 mm")
    self.assertEqual(window.charts["adc"].title(),
                     "CS1237 原始值｜ADC 123456")
    self.assertEqual(len(window.chart_samples["fan1"]), 0)
    window.close()
```

同时将 `QGroupBox` 加入测试文件的 QtWidgets import。

- [ ] **Step 2: 运行测试确认失败**

Run:

```sh
cd QT_Host
env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:../Linux_ROS_WS/src/stm32_jetson_serial_comm .venv/bin/python -m unittest tests.test_window.WindowTest.test_overview_cards_and_chart_titles_show_live_status -v
```

Expected: FAIL，因为 `MainWindow` 尚无 `overview` 和 `charts`。

- [ ] **Step 3: 实现最小界面改动**

在 `MainWindow.__init__()` 增加 `self.charts = {}`；构建总览后保存 `self.overview`。为总览页设置 `overviewPage`，四个 `QGroupBox` 设置 `overviewCard`，值标签设置 `overviewValue`，并在总览页应用一份浅色卡片样式表。

新增共享更新方法，避免在每个状态分支重复刷新样式：

```python
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
        f"超声波距离｜前 {self.values['front'].text()} · 左 {self.values['left'].text()} · 右 {self.values['right'].text()}"
    )
    self.charts["adc"].setTitle(
        f"CS1237 原始值｜ADC {self.values['adc_raw'].text()}"
    )
```

在 `_chart()` 中保存 `self.charts[axis_key] = chart` 并生成带 `--` 的初始标题。在 `on_telemetry()` 中使用 `_set_overview_value()` 更新语义状态，完成所有总览值更新后调用 `_update_chart_titles()`，再执行现有 `_plot()`；这样暂停仅阻止绘图。

- [ ] **Step 4: 运行聚焦测试确认通过**

Run: Step 2 的相同命令。

Expected: 1 test, OK。

- [ ] **Step 5: 运行完整 Qt 验证**

Run:

```sh
cd QT_Host
env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:../Linux_ROS_WS/src/stm32_jetson_serial_comm .venv/bin/python -m unittest discover -s tests -v
env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:../Linux_ROS_WS/src/stm32_jetson_serial_comm .venv/bin/python main.py --smoke-test
```

Expected: 所有测试通过，smoke test 退出码为 0。

- [ ] **Step 6: 提交实现**

```sh
git add QT_Host/dm31_host/window.py QT_Host/tests/test_window.py
git commit -m "feat: polish Qt overview and chart titles"
```
