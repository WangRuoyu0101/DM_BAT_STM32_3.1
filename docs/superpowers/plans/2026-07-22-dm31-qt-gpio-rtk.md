# DM3.1 Qt GPIO Overview and RTK Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the GPIO bitmap in the Qt overview with six named states and add a bounded UM982 RTK text/HEX terminal as the fifth page.

**Architecture:** Keep `SerialWorker` as the only USB owner and reuse the existing `RtkBridge`, text encoder, and HEX parser. RTK reads join the current one-request-per-tick scheduler; the window only sends commands and renders bounded received bytes.

**Tech Stack:** Python 3.9+, PySide6 Widgets, existing `stm32_jetson_serial_comm`, stdlib `bytearray`, `unittest`.

## Global Constraints

- Keep all Qt-specific implementation and tests under `QT_Host/`.
- Do not add dependencies, serial ports, threads, subprocesses, or protocol implementations.
- Reuse `RtkBridge`, `encode_text_command()`, and `parse_hex_bytes()`.
- RTK reads default to 50 ms and share the existing serial worker scheduler.
- Pausing affects display only; the worker continues draining RTK data.
- Retain at most the newest 65,536 received bytes.
- Disable RTK send/read outside `APPLICATION` state and during upgrades.
- This workspace has no `.git`; omit commit steps.

---

### Task 1: SerialWorker RTK bridge integration

**Files:**
- Modify: `QT_Host/tests/test_worker.py`
- Modify: `QT_Host/dm31_host/worker.py`

**Interfaces:**
- Consumes: `RtkBridge(host, timeout_seconds)`, `RtkBridge.read() -> bytes`, `RtkBridge.write(data: bytes) -> None`.
- Produces: `rtk_received = Signal(bytes)`, `send_rtk(data: bytes) -> None`, and scheduled `_poll_rtk()`.

- [ ] **Step 1: Write failing worker tests**

Extend the fake RTK bridge to record writes and return `b"$GNGGA\r\n"` once. Assert that connecting constructs the bridge, `_poll_rtk()` emits those bytes, `send_rtk(b"LOG VERSION\r\n")` calls `write()`, and both operations produce visible errors when the bridge raises `RtkOverflowError` or when the worker is disconnected.

Use constructor injection consistent with the existing factories:

```python
worker = SerialWorker(
    driver_factory=driver_factory,
    host_factory=Host,
    bootloader_factory=Bootloader,
    rtk_factory=RtkBridgeFake,
    port_source=ports,
    sleep=lambda _seconds: None,
)
```

- [ ] **Step 2: Verify the new tests fail**

Run:

```sh
PYTHONPATH=QT_Host:Linux_ROS_WS/src/stm32_jetson_serial_comm \
QT_QPA_PLATFORM=offscreen \
/tmp/dm31-qt-venv/bin/python -m unittest QT_Host/tests/test_worker.py -v
```

Expected: failure because `rtk_factory`, `rtk_received`, and `send_rtk` do not exist.

- [ ] **Step 3: Implement the minimum worker integration**

Import `RtkBridge` and `RtkOverflowError`. Add `rtk_factory=RtkBridge` to the constructor, `_rtk = None`, `"rtk": 0.05` to `_intervals`, and:

```python
rtk_received = Signal(bytes)

def _poll_rtk(self):
    data = self._rtk.read()
    if data:
        self.rtk_received.emit(data)

@Slot(bytes)
def send_rtk(self, data):
    if self._state != "APPLICATION" or self._rtk is None:
        self.command_finished.emit("RTK 发送", False, "设备未连接")
        return
    try:
        self._rtk.write(data)
        self.command_finished.emit("RTK 发送", True, f"{len(data)} bytes")
    except (Exception, SystemExit) as exc:
        self.command_finished.emit("RTK 发送", False, str(exc))
```

Create `_rtk` whenever `_host` is created and clear it in `_close_driver()`. In `poll_once()`, treat `RtkOverflowError` as a logged RTK error while retaining the application connection; keep the existing disconnect behavior for transport errors.

Because `configure_polling()` currently expects all interval keys, keep RTK fixed at 50 ms by excluding `rtk` from the user-supplied rate-key comparison and preserving it when updating `_intervals`.

- [ ] **Step 4: Verify Task 1**

Run the Task 1 test command. Expected: all worker tests pass.

### Task 2: Six GPIO overview values and fifth RTK page

**Files:**
- Modify: `QT_Host/tests/test_window.py`
- Modify: `QT_Host/dm31_host/window.py`

**Interfaces:**
- Consumes: `GPIO_CHANNELS`, `worker.rtk_received`, `worker.send_rtk(bytes)`, `encode_text_command(str) -> bytes`, and `parse_hex_bytes(str) -> bytes`.
- Produces: six `gpio_<channel>` overview labels and the fifth `RTK` tab.

- [ ] **Step 1: Write the failing window test**

Add `rtk_received = Signal(bytes)` and `send_rtk()` to `FakeWorker`. Assert five tab names, feed `gpio_bitmap=0b001011`, and verify the six labels show the matching “开启/关闭” values. Assert RTK text and HEX sends emit `b"LOG VERSION\r\n"` and parsed bytes respectively, received data renders in both modes, and after appending more than 65,536 bytes only the newest 65,536 remain.

The tab assertion becomes:

```python
self.assertEqual(
    [window.tabs.tabText(i) for i in range(window.tabs.count())],
    ["总览", "实时曲线", "控制", "RTK", "固件升级与日志"],
)
```

- [ ] **Step 2: Verify the new window test fails**

Run:

```sh
PYTHONPATH=QT_Host:Linux_ROS_WS/src/stm32_jetson_serial_comm \
QT_QPA_PLATFORM=offscreen \
/tmp/dm31-qt-venv/bin/python -m unittest QT_Host/tests/test_window.py -v
```

Expected: failure because the fifth tab and per-channel GPIO labels do not exist.

- [ ] **Step 3: Replace the bitmap with six labels**

Build the connection group from `GPIO_CHANNELS`:

```python
gpio_rows = tuple((f"gpio_{channel}", name) for name, channel in GPIO_CHANNELS)
grid.addWidget(self._value_group("连接与 GPIO", (("link", "链路"),) + gpio_rows), 0, 0)
```

In `on_telemetry()`, render each label:

```python
for _name, channel in GPIO_CHANNELS:
    text = "--" if telemetry.gpio_bitmap is None else (
        "开启" if telemetry.gpio_bitmap & (1 << (channel - 1)) else "关闭"
    )
    self.values[f"gpio_{channel}"].setText(text)
```

- [ ] **Step 4: Add the minimal RTK page**

Add `rtk_send_requested = Signal(bytes)`, connect it to `worker.send_rtk`, and connect `worker.rtk_received` to `_on_rtk_received`. Build one page containing text input/send, HEX input/send, a text/HEX mode combo, pause/clear buttons, and a read-only `QPlainTextEdit`.

Use existing parsers directly:

```python
def _send_rtk_text(self):
    command = self.rtk_text_input.text()
    if command:
        self.rtk_send_requested.emit(encode_text_command(command))

def _send_rtk_hex(self):
    try:
        data = parse_hex_bytes(self.rtk_hex_input.text())
        if not data:
            raise ValueError("HEX 数据不能为空")
        self.rtk_send_requested.emit(data)
    except ValueError as exc:
        self.append_log(f"RTK HEX: {exc}")
```

Keep a bounded byte buffer and render from it:

```python
RTK_DISPLAY_LIMIT = 65536

def _on_rtk_received(self, data):
    self.rtk_buffer.extend(data)
    del self.rtk_buffer[:-RTK_DISPLAY_LIMIT]
    if not self.rtk_paused.isChecked():
        self._render_rtk()
```

Text mode uses `bytes(self.rtk_buffer).decode("ascii", errors="replace")`; HEX mode uses `bytes(self.rtk_buffer).hex(" ").upper()`. `on_state_changed()` enables the RTK page only in `APPLICATION` state.

- [ ] **Step 5: Verify Task 2 and all Qt tests**

Run:

```sh
PYTHONPATH=QT_Host:Linux_ROS_WS/src/stm32_jetson_serial_comm \
QT_QPA_PLATFORM=offscreen \
/tmp/dm31-qt-venv/bin/python -m unittest discover -s QT_Host/tests -v
```

Expected: all Qt tests pass.

### Task 3: Documentation and complete regression verification

**Files:**
- Modify: `QT_Host/README.md`

**Interfaces:**
- Consumes: the implemented five-tab UI.
- Produces: concise RTK usage and hardware acceptance instructions.

- [ ] **Step 1: Update usage documentation**

Document the six GPIO overview states, RTK ASCII/HEX send, text/HEX receive, pause semantics, 64 KiB display bound, and the requirement for a real UM982/STM32 hardware test.

- [ ] **Step 2: Run fresh complete verification**

```sh
python3 -m unittest discover -s STM32/tests
python3 -m unittest discover -s Linux_ROS_WS/src/stm32_jetson_serial_comm/tests
PYTHONPATH=QT_Host:Linux_ROS_WS/src/stm32_jetson_serial_comm \
QT_QPA_PLATFORM=offscreen \
/tmp/dm31-qt-venv/bin/python -m unittest discover -s QT_Host/tests
PYTHONPATH=QT_Host:Linux_ROS_WS/src/stm32_jetson_serial_comm \
QT_QPA_PLATFORM=offscreen \
/tmp/dm31-qt-venv/bin/python QT_Host/main.py --smoke-test
```

Expected: 52 STM32 tests, 91 Jetson/host tests, all Qt tests, and the smoke test pass.

- [ ] **Step 3: Record the hardware boundary**

Do not claim UM982 throughput or Windows/Linux USB behavior was verified without hardware. The remaining acceptance check is sustained RTK receive, overflow visibility, ASCII/HEX send, and coexistence with normal polling on a real board.
