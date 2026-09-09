# DM3.1 Qt Debug Host Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PySide6 internal debug host under root-level `QT_Host/` that directly controls, monitors, records, charts, and upgrades one DM3.1 STM32 over USB CDC.

**Architecture:** A Qt Widgets main thread owns presentation only. One `SerialWorker` in a `QThread` exclusively owns the existing pyserial `SerialDriver`, `SerialHost`, and `BootloaderClient`; it serializes polling, controls, and upgrade operations through Qt signals. Pure-Python helpers handle port identity, bounded samples, telemetry snapshots, and CSV so they remain easy to test.

**Tech Stack:** Python 3.9+, PySide6 Widgets/Charts, pyserial, existing `stm32_jetson_serial_comm`, stdlib `csv`, `unittest`.

## Global Constraints

- Put every Qt-specific source, test, dependency, and deployment file under root `QT_Host/`.
- Reuse `SerialDriver`, `SerialHost`, message dataclasses, and `BootloaderClient`; do not add a second protocol implementation or use `QSerialPort`.
- Support macOS development and separate Windows/Linux builds; do not claim macOS artifacts are portable.
- Support one STM32 connection only.
- Normal defaults: app 115200 baud, bootloader 460800 baud, status 0.5 Hz, GPIO 1 Hz, ultrasonic 5 Hz, CS1237 10 Hz, board IO 2 Hz.
- Pause normal polling and controls during firmware upgrade.
- Keep charts bounded to 600 samples by default.
- Use stdlib CSV/text logging; no database, Matplotlib, QML, plugin framework, or theme framework.
- Preserve configurable poll rates, serial timeout, and existing CS1237 calibration.
- This workspace has no `.git`; skip commit commands while retaining all verification steps.

---

### Task 1: Subproject foundation, port discovery, bounded data, and CSV

**Files:**
- Create: `QT_Host/requirements.txt`
- Create: `QT_Host/dm31_host/__init__.py`
- Create: `QT_Host/dm31_host/core.py`
- Create: `QT_Host/tests/test_core.py`

**Interfaces:**
- Consumes: `serial.tools.list_ports.comports()`.
- Produces: `PortChoice`, `list_serial_ports()`, `find_matching_port()`, `Telemetry`, `append_bounded()`, and `CsvRecorder`.

- [ ] **Step 1: Write failing pure-Python tests**

Test exact behavior: port choices sort by device; matching prefers serial number then VID/PID; `append_bounded()` retains the newest 600 values; `CsvRecorder` writes a stable header, timezone-aware timestamp, telemetry fields, and closes cleanly.

- [ ] **Step 2: Verify red state**

Run: `PYTHONPATH=QT_Host python3 -m unittest QT_Host/tests/test_core.py -v`

Expected: import failure for `dm31_host.core`.

- [ ] **Step 3: Implement minimum core**

Use these public signatures:

```python
@dataclass(frozen=True)
class PortChoice:
    device: str
    description: str = ""
    hwid: str = ""
    vid: int | None = None
    pid: int | None = None
    serial_number: str | None = None

def list_serial_ports(source=None) -> list[PortChoice]: ...
def find_matching_port(original: PortChoice, source=None) -> PortChoice | None: ...
def append_bounded(values: deque, value, limit: int = 600) -> None: ...

@dataclass
class Telemetry:
    sample_seq: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now().astimezone())
    link_ok: bool = False
    gpio_bitmap: int | None = None
    fan_level: int | None = None
    fan1_rpm: int | None = None
    fan2_rpm: int | None = None
    key_bitmap: int | None = None
    ultrasonic_front_mm: int | None = None
    ultrasonic_left_mm: int | None = None
    ultrasonic_right_mm: int | None = None
    ultrasonic_valid_bitmap: int | None = None
    ultrasonic_error_bitmap: int | None = None
    cs1237_raw: int | None = None
    cs1237_channel: int | None = None
    cs1237_valid: bool | None = None
    cs1237_error: int | None = None

class CsvRecorder:
    def start(self, path: str | Path) -> None: ...
    def write(self, telemetry: Telemetry) -> None: ...
    def stop(self) -> None: ...
    @property
    def active(self) -> bool: ...
```

- [ ] **Step 4: Verify green state**

Run the Task 1 command. Expected: all tests pass.

### Task 2: Shared bootloader image-size safety

**Files:**
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/bootloader.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_bootloader.py`

**Interfaces:**
- Consumes: `BootloaderInfo.app_size` returned by the existing HELLO exchange.
- Produces: `BootloaderClient.program_image()` raises `ValueError` before START when `len(image) > info.app_size`.

- [ ] **Step 1: Add a failing test**

Use the existing fake bootloader driver to return INFO with an application size smaller than the selected image. Assert `ValueError` contains both sizes and that no START frame is sent.

- [ ] **Step 2: Verify red state**

Run: `python3 -m unittest Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_bootloader.py -v`

Expected: oversized image proceeds to START instead of raising.

- [ ] **Step 3: Add one shared guard**

Immediately after `_request_info()`:

```python
if len(image) > info.app_size:
    raise ValueError(f"image size {len(image)} exceeds application area {info.app_size}")
```

- [ ] **Step 4: Verify green state**

Run the Task 2 command and the full existing Jetson test suite.

### Task 3: Serial worker and upgrade state machine

**Files:**
- Create: `QT_Host/dm31_host/worker.py`
- Create: `QT_Host/tests/test_worker.py`

**Interfaces:**
- Consumes: `PortChoice`, `Telemetry`, `find_matching_port()`, `SerialDriver`, `SerialHost`, and `BootloaderClient`.
- Produces: `SerialWorker(QObject)` with state, telemetry, log, command-result, progress, and completion signals.

- [ ] **Step 1: Write failing worker tests with fake driver/host/bootloader factories**

Check: connect/disconnect; each poll copies decoded fields into one persistent `Telemetry`; fan/GPIO/CS1237 controls emit the actual result; upgrade stops the poll timer, requests bootloader, reopens at 460800, reports progress, and returns to application mode; failure emits error and never resumes a half-open timer.

- [ ] **Step 2: Verify red state**

Run: `PYTHONPATH=QT_Host:Linux_ROS_WS/src/stm32_jetson_serial_comm QT_QPA_PLATFORM=offscreen python3 -m unittest QT_Host/tests/test_worker.py -v`

Expected: import failure for `dm31_host.worker`.

- [ ] **Step 3: Implement one QObject worker**

Public state and slots:

```python
class SerialWorker(QObject):
    state_changed = Signal(str, str)
    telemetry_changed = Signal(object)
    log_message = Signal(str)
    command_finished = Signal(str, bool, str)
    upgrade_progress = Signal(str, int)
    upgrade_finished = Signal(bool, str)

    @Slot(object)
    def connect_port(self, choice: PortChoice) -> None: ...
    @Slot()
    def disconnect_port(self) -> None: ...
    @Slot()
    def poll_once(self) -> None: ...
    @Slot(int, int)
    def set_gpio(self, channel_id: int, level: int) -> None: ...
    @Slot(int)
    def set_fan(self, level: int) -> None: ...
    @Slot(int)
    def set_cs1237_channel(self, channel: int) -> None: ...
    @Slot(str, bool)
    def upgrade(self, image_path: str, request_from_app: bool = True) -> None: ...
```

Use one 50 ms `QTimer` and monotonic deadlines to select at most one due query per tick. Store all factories as constructor arguments with production defaults; this is test injection, not a generalized backend abstraction.

- [ ] **Step 4: Verify green state**

Run Task 3 tests, then Task 1 and Task 3 together.

### Task 4: Qt Widgets dashboard, controls, charts, CSV, and firmware page

**Files:**
- Create: `QT_Host/dm31_host/window.py`
- Create: `QT_Host/main.py`
- Create: `QT_Host/tests/test_window.py`

**Interfaces:**
- Consumes: all `SerialWorker` signals/slots, `list_serial_ports()`, `Telemetry`, `CsvRecorder`, and `append_bounded()`.
- Produces: `MainWindow(QMainWindow)` and executable `QT_Host/main.py`.

- [ ] **Step 1: Write one failing offscreen UI smoke test**

Create `QApplication`, construct `MainWindow` with a fake worker, assert four tab names (`总览`, `实时曲线`, `控制`, `固件升级与日志`), assert connect/CSV/upgrade controls exist, feed one `Telemetry`, and assert displayed RPM and bounded chart samples update.

- [ ] **Step 2: Verify red state**

Run: `PYTHONPATH=QT_Host:Linux_ROS_WS/src/stm32_jetson_serial_comm QT_QPA_PLATFORM=offscreen python3 -m unittest QT_Host/tests/test_window.py -v`

Expected: import failure for `dm31_host.window`.

- [ ] **Step 3: Implement minimum four-tab window**

Build widgets in Python, without `.ui` or generated resource files. The top connection row owns port refresh/selection/connect/disconnect/status. Overview uses labels. Charts use three `QChartView` instances and bounded `QLineSeries`. Controls use existing six GPIO IDs, four fan buttons, and CS1237 channel buttons. Firmware page selects `.bin`, starts upgrade, displays progress, and includes one read-only `QPlainTextEdit`. CSV start/stop uses `QFileDialog` and `CsvRecorder`.

`main.py` adds the existing package source directory to `sys.path` only when running from the repository checkout, creates `QApplication`, moves `SerialWorker` to `QThread`, connects shutdown, and shows `MainWindow`.

- [ ] **Step 4: Verify green state**

Run Task 4 tests and all `QT_Host/tests`.

### Task 5: Usage, deployment, and complete verification

**Files:**
- Create: `QT_Host/README.md`
- Create: `QT_Host/pysidedeploy.spec`
- Modify: `docs/superpowers/specs/2026-07-22-dm31-qt-debug-host-design.md` only if implementation reveals a factual mismatch.

**Interfaces:**
- Consumes: `QT_Host/main.py` and dependencies.
- Produces: repeatable macOS development setup plus separate Windows/Linux packaging instructions.

- [ ] **Step 1: Document exact setup and execution**

Include virtual environment creation, `pip install -r QT_Host/requirements.txt`, `python QT_Host/main.py`, USB naming on all three operating systems, and `pyside6-deploy -c QT_Host/pysidedeploy.spec`. State explicitly that Windows and Linux artifacts are built and tested on their own platforms.

- [ ] **Step 2: Install dependencies in an isolated environment and run verification**

Run:

```sh
python3 -m unittest discover -s STM32/tests
python3 -m unittest discover -s Linux_ROS_WS/src/stm32_jetson_serial_comm/tests
PYTHONPATH=QT_Host:Linux_ROS_WS/src/stm32_jetson_serial_comm QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s QT_Host/tests
PYTHONPATH=QT_Host:Linux_ROS_WS/src/stm32_jetson_serial_comm QT_QPA_PLATFORM=offscreen python3 QT_Host/main.py --smoke-test
```

Expected: all suites pass; smoke test constructs and closes the window without entering the long-running event loop.

- [ ] **Step 3: Manual acceptance boundary**

Record that actual USB CDC, 30-minute chart stability, firmware upgrade, and Windows/Linux packaged executable checks require the corresponding hardware/platform and are not replaced by offscreen tests.
