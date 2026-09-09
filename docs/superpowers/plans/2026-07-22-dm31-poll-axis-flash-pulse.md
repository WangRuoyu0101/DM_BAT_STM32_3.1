# DM3.1 Poll Controls, Chart Axes, and Flash Pulse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add six polling switches and editable Y-axis bounds to the Qt host while making flash-control channel 1 a firmware-guaranteed 200 ms pulse with matching button behavior.

**Architecture:** Extend the existing one-request-per-tick worker with an enabled map, and update existing Qt settings/axes without new persistence or scheduling systems. Implement the pulse in `app_relay_control` using the existing 2 ms application tick; the UI timer is feedback only.

**Tech Stack:** STM32 HAL C, Python 3.9+, PySide6 Widgets/Charts, existing `unittest` suites and Makefile.

## Global Constraints

- Keep GPIO channel IDs and frame formats unchanged.
- Channel 1 HIGH starts/restarts a 100-tick (200 ms) pulse; LOW cancels it; channels 2–6 retain level semantics.
- Use the existing 2 ms application tick and main loop; no blocking delay or interrupt business logic.
- Six poll switches default on; disabled polls retain last values and re-enabled polls become immediately due.
- RTK polling off must not disable manual RTK sends.
- Existing five poll frequencies remain editable; RTK remains fixed at 20 Hz.
- Each chart has one shared integer Y axis; invalid ranges update none of the axes.
- Settings remain process-local; add no dependencies, config files, threads, or protocol frames.

---

### Task 1: Firmware-guaranteed flash-control pulse

**Files:**
- Modify: `STM32/tests/test_relay_control.py`
- Modify: `STM32/Core/Inc/app_relay_control.h`
- Modify: `STM32/Core/Src/app_relay_control.c`
- Modify: `STM32/Core/Src/app_uart5_slave.c`
- Modify: `STM32/Core/Src/main.c`

**Interfaces:**
- Consumes: the existing 2 ms `current_tick` passed through UART5 processing and the main loop.
- Produces: `App_RelayControl_Apply(const App_CommGpioControl *, uint32_t current_tick)` and `App_RelayControl_Service(uint32_t current_tick)`.

- [ ] **Step 1: Add a failing firmware source test**

Extend `test_relay_control_module_maps_channels_to_gpio_pins` to assert:

```python
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
self.assertIn("App_RelayControl_Service(current_tick);", main)
self.assertIn("App_RelayControl_Apply(&control, current_tick)", uart5_source)
```

Also assert source contains separate channel-1 LOW cancellation and HIGH restart branches, and no `HAL_Delay`.

- [ ] **Step 2: Verify RED**

Run: `python3 -m unittest STM32/tests/test_relay_control.py -v`

Expected: failure because the 100-tick pulse service and tick-aware apply signature do not exist.

- [ ] **Step 3: Implement the minimum non-blocking pulse**

In `app_relay_control.c`, add:

```c
#define APP_RELAY_CONTROL_FLASH_PULSE_TICKS 100U

static uint8_t s_flash_pulse_active = 0U;
static uint32_t s_flash_pulse_start_tick = 0U;
```

Change `App_RelayControl_Apply` to accept `current_tick`. After validation, special-case channel 1: LOW clears `s_flash_pulse_active`; HIGH sets it and stores `current_tick`; both still call `HAL_GPIO_WritePin`. Other channels keep the existing behavior.

Add:

```c
void App_RelayControl_Service(uint32_t current_tick)
{
  if ((s_flash_pulse_active != 0U) &&
      ((uint32_t)(current_tick - s_flash_pulse_start_tick) >= APP_RELAY_CONTROL_FLASH_PULSE_TICKS))
  {
    HAL_GPIO_WritePin(GPIOC, GPIO_PIN_5, GPIO_PIN_RESET);
    s_flash_pulse_active = 0U;
  }
}
```

Update both UART5 call sites to pass `current_tick`, remove the now-obsolete `(void)current_tick`, declare both signatures in the header, and call `App_RelayControl_Service(current_tick)` once per main-loop iteration before UART5 processing.

- [ ] **Step 4: Verify firmware tests and build**

```sh
python3 -m unittest STM32/tests/test_relay_control.py -v
python3 -m unittest discover -s STM32/tests
make -C STM32 app
```

Expected: focused test and all STM32 tests pass; application builds.

- [ ] **Step 5: Commit Task 1**

```sh
git add STM32/tests/test_relay_control.py STM32/Core/Inc/app_relay_control.h \
  STM32/Core/Src/app_relay_control.c STM32/Core/Src/app_uart5_slave.c STM32/Core/Src/main.c
git commit -m "feat: pulse flash control for 200 ms"
```

### Task 2: Worker polling enable map

**Files:**
- Modify: `QT_Host/tests/test_worker.py`
- Modify: `QT_Host/dm31_host/worker.py`

**Interfaces:**
- Consumes: current interval/deadline scheduler and `configure_polling` slot.
- Produces: `configure_polling(rates_hz: object, enabled: object, serial_timeout: float)` with six enabled flags.

- [ ] **Step 1: Add failing worker tests**

Update existing calls to include all enabled flags, then add one test that:

```python
enabled = {name: True for name in worker._intervals}
enabled["gpio"] = False
worker.configure_polling(rates, enabled, 0.2)
worker._deadlines = {name: float("inf") for name in worker._intervals}
worker._deadlines["gpio"] = 0.0
worker.poll_once()
self.assertEqual(host.gpio_query_count, 0)

enabled["gpio"] = True
worker.configure_polling(rates, enabled, 0.2)
self.assertEqual(worker._deadlines["gpio"], 0.0)
```

Also verify all flags false produces no request and `send_rtk()` still writes while RTK polling is false. Add fake-host query counters instead of a new abstraction.

- [ ] **Step 2: Verify RED**

Run:

```sh
PYTHONPATH=QT_Host:Linux_ROS_WS/src/stm32_jetson_serial_comm \
QT_QPA_PLATFORM=offscreen /tmp/dm31-qt-venv/bin/python \
-m unittest QT_Host/tests/test_worker.py -v
```

Expected: calls fail because `configure_polling` does not accept enabled flags and disabled items are still scheduled.

- [ ] **Step 3: Implement the enabled map**

Initialize:

```python
self._enabled = {name: True for name in self._intervals}
```

Change the slot to `@Slot(object, object, float)`. Validate `rates_hz` against the five non-RTK names, `enabled` against all six interval names, every flag is `bool`, and existing frequency/timeout constraints. Apply the maps only after every validation succeeds. Keep RTK at `0.05`, recreate its bridge after timeout changes, and reset deadlines to `0.0` so newly enabled polls are immediate.

In `poll_once()`, sort and inspect only names whose flag is true:

```python
enabled_names = (name for name in self._intervals if self._enabled[name])
for name in sorted(enabled_names, key=self._deadlines.__getitem__):
    ...
```

Do not reference `_enabled` from `send_rtk()`.

- [ ] **Step 4: Verify Task 2**

Run the Task 2 command and the complete Qt suite. Expected: all tests pass.

- [ ] **Step 5: Commit Task 2**

```sh
git add QT_Host/tests/test_worker.py QT_Host/dm31_host/worker.py
git commit -m "feat: add polling enable controls"
```

### Task 3: Qt switches, editable axes, and pulse button

**Files:**
- Modify: `QT_Host/tests/test_window.py`
- Modify: `QT_Host/dm31_host/window.py`
- Modify: `QT_Host/README.md`

**Interfaces:**
- Consumes: the Task 2 three-argument `configure_polling` slot and existing GPIO command result signal.
- Produces: six poll checkboxes, three Y-axis range editors, and one flash pulse button.

- [ ] **Step 1: Add failing window tests**

Update `FakeWorker.configure_polling` to accept `(rates, enabled, timeout)` and record the call. Assert:

- `window.poll_checks` contains the six worker names and defaults checked;
- applying settings passes five rates, six flags, and timeout;
- valid fan/ultrasonic/ADC inputs change the three axis ranges;
- one invalid group leaves all three prior ranges unchanged and writes a log message;
- `gpio_checks` contains only channels 2–6;
- clicking `flash_pulse_button` sends `(1, 1)`, changes the text to `脉冲中…`, and disables it;
- emitting `command_finished("GPIO 1", True, "OK")` restores it after `QTest.qWait(220)`;
- failure and disconnect restore it immediately.

- [ ] **Step 2: Verify RED**

Run:

```sh
PYTHONPATH=QT_Host:Linux_ROS_WS/src/stm32_jetson_serial_comm \
QT_QPA_PLATFORM=offscreen /tmp/dm31-qt-venv/bin/python \
-m unittest QT_Host/tests/test_window.py -v
```

Expected: missing poll switches, axis editors, and pulse button.

- [ ] **Step 3: Add polling switches to the existing settings group**

Change `settings_requested` to `Signal(object, object, float)`. Create `self.poll_checks` with checked checkboxes for the five rate rows plus an RTK row labeled fixed 20 Hz. `_apply_settings()` emits rates, enabled flags, and timeout together.

- [ ] **Step 4: Add three shared Y-axis editors**

Store the shared Y axes as `self.chart_axes_y` keyed by `fan`, `ultrasonic`, and `adc`. Add six integer `QSpinBox` inputs using the current default ranges and a single apply button. `_apply_y_axes()` first reads and validates all three pairs; if any minimum is not below its maximum, append `Y 轴范围无效：最小值必须小于最大值` and return without setting any axis. Otherwise call `axis.setRange(minimum, maximum)` for all three.

- [ ] **Step 5: Replace channel 1 checkbox with a pulse button**

Import `QTimer`. In the GPIO control grid, create `flash_pulse_button` for channel 1 and keep checkboxes only for channels 2–6. On click, set `脉冲中…`, disable it, and emit `(1, 1)`. In `on_command_finished`, for `GPIO 1`, start `QTimer.singleShot(200, self._reset_flash_pulse_button)` only on success; restore immediately on failure. Restore on every non-`APPLICATION` state. The reset method sets the original text and enables the button only when the control page is in application mode.

- [ ] **Step 6: Update README and verify all Qt tests**

Document six polling switches, per-chart Y ranges, and firmware-owned 200 ms flash pulse. Run the complete Qt suite and smoke test.

- [ ] **Step 7: Commit Task 3**

```sh
git add QT_Host/tests/test_window.py QT_Host/dm31_host/window.py QT_Host/README.md
git commit -m "feat: add polling switches and chart ranges"
```

### Task 4: Complete regression and sync verification

**Files:**
- No source changes expected.

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: verified firmware, host, Qt, and Git state.

- [ ] **Step 1: Run fresh complete verification**

```sh
python3 -m unittest discover -s STM32/tests
python3 -m unittest discover -s Linux_ROS_WS/src/stm32_jetson_serial_comm/tests
PYTHONPATH=QT_Host:Linux_ROS_WS/src/stm32_jetson_serial_comm \
QT_QPA_PLATFORM=offscreen /tmp/dm31-qt-venv/bin/python -m unittest discover -s QT_Host/tests
PYTHONPATH=QT_Host:Linux_ROS_WS/src/stm32_jetson_serial_comm \
QT_QPA_PLATFORM=offscreen /tmp/dm31-qt-venv/bin/python QT_Host/main.py --smoke-test
make -C STM32 app bootloader
cmp STM32/build/app/DM3.1_BAT_app.bin \
  Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin
git status --short
```

Expected: all tests pass, both firmware targets build, synced application binary matches, and status is clean.

- [ ] **Step 2: Record hardware boundary**

Do not claim the actual PC5 pulse width until measured on hardware. Required hardware acceptance is one 200 ms pulse per click, retrigger behavior, early LOW cancellation, and normal operation of channels 2–6.
