# DM3.1 Qt Settings Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the approved polling and chart-axis settings and restore them when the Qt host starts again.

**Architecture:** Keep persistence inside the existing `MainWindow`, because it already owns every relevant control. Use Qt's native `QSettings`; inject a settings object only for test isolation, and reuse the existing apply handlers for saving and Worker activation.

**Tech Stack:** Python 3.9+, PySide6 `QSettings`, `unittest`

## Global Constraints

- Persist only six polling switches, five polling rates, serial timeout, and three Y-axis ranges.
- Do not persist port selection, firmware path, pause/display state, or RTK display mode.
- Use `QSettings("DM3.1", "BATDebugHost")`; add no dependency or custom configuration file.
- Invalid persisted polling values fall back individually; any incomplete or invalid Y-axis set leaves all three default ranges unchanged.
- Do not auto-connect the serial device.

---

### Task 1: Persist and restore approved Qt settings

**Files:**
- Modify: `QT_Host/dm31_host/window.py`
- Modify: `QT_Host/tests/test_window.py`
- Modify: `QT_Host/README.md`

**Interfaces:**
- Consumes: existing `MainWindow._apply_settings()`, `MainWindow._apply_y_axes()`, `poll_checks`, `rate_inputs`, `timeout_input`, `y_axis_inputs`, and `chart_axes_y`.
- Produces: `MainWindow(worker, parent=None, settings=None)`, `_restore_settings() -> None`, and `_sync_settings() -> None`.

- [ ] **Step 1: Add failing persistence and invalid-data tests**

In `QT_Host/tests/test_window.py`, import `tempfile`, `Path`, and `QSettings`. Give every test an isolated INI file:

```python
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal

def setUp(self):
    self.directory = tempfile.TemporaryDirectory()
    self.settings = QSettings(
        str(Path(self.directory.name) / "settings.ini"),
        QSettings.IniFormat,
    )

def tearDown(self):
    self.settings.clear()
    self.directory.cleanup()
```

Pass `settings=self.settings` to every existing `MainWindow` construction. Add these tests:

```python
def test_applied_settings_restore_in_a_new_window(self):
    first = MainWindow(FakeWorker(), settings=self.settings)
    enabled = {
        "status": False, "gpio": True, "ultrasonic": False,
        "cs1237": True, "board_io": False, "rtk": True,
    }
    rates = {"status": 1.0, "gpio": 3.0, "ultrasonic": 4.0, "cs1237": 8.0, "board_io": 2.0}
    ranges = {"fan": (100, 9000), "ultrasonic": (10, 8000), "adc": (-1000, 1000)}
    for key, value in enabled.items():
        first.poll_checks[key].setChecked(value)
    for key, value in rates.items():
        first.rate_inputs[key].setValue(value)
    first.timeout_input.setValue(0.4)
    first._apply_settings()
    for key, (minimum, maximum) in ranges.items():
        first.y_axis_inputs[key][0].setValue(minimum)
        first.y_axis_inputs[key][1].setValue(maximum)
    first._apply_y_axes()
    first.close()

    worker = FakeWorker()
    restored = MainWindow(worker, settings=self.settings)
    self.assertEqual(
        {key: checkbox.isChecked() for key, checkbox in restored.poll_checks.items()},
        enabled,
    )
    self.assertEqual(
        {key: spin.value() for key, spin in restored.rate_inputs.items()},
        rates,
    )
    self.assertEqual(restored.timeout_input.value(), 0.4)
    for key, expected in ranges.items():
        self.assertEqual((restored.chart_axes_y[key].min(), restored.chart_axes_y[key].max()), expected)
    self.assertEqual(worker.poll_settings[-1][1], enabled)
    restored.close()

def test_invalid_saved_values_fall_back_without_partial_axis_restore(self):
    self.settings.setValue("poll/rate/status", "invalid")
    self.settings.setValue("poll/rate/gpio", 3.0)
    self.settings.setValue("chart/fan/minimum", 100)
    self.settings.sync()

    window = MainWindow(FakeWorker(), settings=self.settings)
    self.assertEqual(window.rate_inputs["status"].value(), 0.5)
    self.assertEqual(window.rate_inputs["gpio"].value(), 3.0)
    self.assertEqual(
        (window.chart_axes_y["fan"].min(), window.chart_axes_y["fan"].max()),
        (0, 12000),
    )
    window.close()
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd QT_Host
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest \
  tests.test_window.WindowTest.test_applied_settings_restore_in_a_new_window \
  tests.test_window.WindowTest.test_invalid_saved_values_fall_back_without_partial_axis_restore -v
```

Expected: both tests error because `MainWindow` does not accept `settings`.

- [ ] **Step 3: Add the minimal `QSettings` implementation**

In `QT_Host/dm31_host/window.py`, import `QSettings`, accept the injected object, restore after all widgets exist, and immediately activate the restored polling settings:

```python
from PySide6.QtCore import QPointF, QSettings, Qt, QTimer, Signal

def __init__(self, worker, parent=None, settings=None):
    super().__init__(parent)
    self.settings = settings if settings is not None else QSettings("DM3.1", "BATDebugHost")
    # existing initialization and widget construction stay unchanged
    self.setCentralWidget(root)
    self._restore_settings()
    self._apply_settings()
    self.refresh_ports()
    self.on_state_changed("DISCONNECTED", "")
```

Add restoration and sync helpers:

```python
def _restore_settings(self):
    for key, checkbox in self.poll_checks.items():
        default = checkbox.isChecked()
        try:
            checkbox.setChecked(self.settings.value(f"poll/enabled/{key}", default, type=bool))
        except (TypeError, ValueError):
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
    except (TypeError, ValueError):
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
```

Extend the two existing apply handlers without adding a settings wrapper class:

```python
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
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the Step 2 command again.

Expected: both tests pass.

- [ ] **Step 5: Document persistence and run the complete Qt checks**

Add this sentence to the `QT_Host/README.md` usage section:

```markdown
轮询开关、轮询频率、串口超时和三组曲线 Y 轴范围会保存到当前用户的系统配置中，并在下次启动时自动恢复；串口、固件路径和临时显示状态不会保存。
```

Run:

```bash
cd QT_Host
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen .venv/bin/python main.py --smoke-test
```

Expected: all tests pass and smoke test exits with status 0.

- [ ] **Step 6: Commit the implementation**

```bash
git add QT_Host/dm31_host/window.py QT_Host/tests/test_window.py QT_Host/README.md
git commit -m "feat: persist Qt host settings"
```
