# DM3.1 Bootloader Fail-Safe Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the first and every later App installation recoverable through the Bootloader, with persistent image validity and observable idle status in the Qt host.

**Architecture:** Reserve Flash Sector 7 for an atomic App-validity record; invalidate it before erasing Sector 2–6 and commit its magic only after full image verification. Keep the existing command protocol, add one unsolicited status frame, teach the Python client to dispatch it without disturbing command responses, and let Qt detect and monitor Bootloader-only devices.

**Tech Stack:** STM32F407 HAL C, GNU Arm Embedded Makefile/linker scripts, Python 3 standard library, PySide6, unittest.

## Global Constraints

- App remains based at `0x08008000` and is limited to 352 KiB (`0x08008000–0x0805FFFF`).
- Sector 7 (`0x08060000–0x0807FFFF`) is metadata only; no App section may be linked there.
- Metadata magic is `0x41334D44`, format version is 1, and magic is written last.
- No metadata means no valid App; there is no legacy-vector trust path.
- `START` is non-destructive; the lock begins only after metadata invalidation succeeds during `ERASE`.
- Successful `VERIFY` stays in Bootloader until explicit `JUMP`; a reset after successful verification may boot the App.
- USB Bootloader status frame is `0x92` at a 1-second idle interval and must not transmit during a Flash operation.
- Do not add dependencies or unrelated abstractions.

---

### Task 1: Persistent App Validity and Flash Partition

**Files:**
- Modify: `STM32/Core/Inc/app_flash_layout.h`
- Modify: `STM32/STM32F407XX_APP_FLASH.ld`
- Modify: `STM32/Bootloader/Core/Inc/bootloader_flash.h`
- Modify: `STM32/Bootloader/Core/Src/bootloader_flash.c`
- Modify: `STM32/Bootloader/Core/Src/bootloader_jump.c`
- Modify: `STM32/Bootloader/Core/Inc/bootloader_config.h`
- Test: `STM32/tests/test_uart5_bootloader.py`

**Interfaces:**
- Produces: `Bootloader_FlashIsApplicationValid(void) -> uint8_t` for startup and `JUMP`.
- Produces: `Bootloader_FlashInvalidateMetadata(void) -> uint8_t` and `Bootloader_FlashCommitMetadata(uint32_t image_size, uint32_t image_crc32) -> uint8_t` for the upgrade flow.
- Produces: `Bootloader_FlashSession.erased` so `WRITE` and `VERIFY` cannot run before `ERASE`.

- [ ] **Step 1: Write failing layout and metadata source tests**

Update `test_uart5_bootloader.py` to require the exact layout and safety hooks:

```python
self.assertIn("#define APP_FLASH_SIZE (352U * 1024U)", header)
self.assertIn("#define APP_FLASH_END 0x08060000U", header)
self.assertIn("#define APP_METADATA_BASE 0x08060000U", header)
self.assertIn("#define APP_METADATA_MAGIC 0x41334D44U", header)
self.assertIn("FLASH (rx)      : ORIGIN = 0x8008000, LENGTH = 352K", app_ld)
self.assertIn("Bootloader_FlashInvalidateMetadata", flash_source)
self.assertIn("Bootloader_FlashCommitMetadata", flash_source)
self.assertIn("Bootloader_FlashIsApplicationValid", flash_source)
self.assertIn("FLASH_SECTOR_7", flash_source)
self.assertIn("session->erased", flash_source)
```

- [ ] **Step 2: Run the focused test and confirm failure**

Run: `python3 -m unittest STM32/tests/test_uart5_bootloader.py -v`

Expected: FAIL because the layout is still 480 KiB and metadata functions do not exist.

- [ ] **Step 3: Implement the minimal atomic metadata flow**

Change the shared layout to:

```c
#define APP_FLASH_BASE 0x08008000U
#define APP_FLASH_SIZE (352U * 1024U)
#define APP_FLASH_END 0x08060000U
#define APP_METADATA_BASE 0x08060000U
#define APP_METADATA_SIZE (128U * 1024U)
#define APP_METADATA_MAGIC 0x41334D44U
#define APP_METADATA_FORMAT_VERSION 1U
```

In `bootloader_flash.h`, add `erased` to the existing session and declare the three functions above. In `bootloader_flash.c`, use one five-word metadata record, the existing reflected CRC32 routine, and these rules:

```c
typedef struct {
  uint32_t magic;
  uint32_t format_version;
  uint32_t image_size;
  uint32_t image_crc32;
  uint32_t record_crc32;
} Bootloader_AppMetadata;

/* Invalidate: program magic to zero and verify it is no longer valid. */
/* Commit: erase Sector 7, program offsets 4..19, verify, program magic last. */
/* Valid: metadata fields + metadata CRC + vectors + full image CRC. */
```

Make `ERASE` invalidate metadata before erasing all five App sectors. Reject `WRITE` and `VERIFY` unless `session->erased != 0U`. Make `VERIFY` commit metadata only after the image CRC and vectors pass. Make `Bootloader_IsApplicationValid()` delegate to `Bootloader_FlashIsApplicationValid()`. Set `BOOTLOADER_VERSION` to `0x00020000U` and change the App linker length to 352K. Keep the implementation in the existing Flash module, so the Makefile source list does not change.

- [ ] **Step 4: Run tests and build both images**

Run: `python3 -m unittest STM32/tests/test_uart5_bootloader.py -v`

Expected: PASS.

Run: `make -C STM32 app bootloader`

Expected: both ELF/BIN targets build; App size remains below 352 KiB and the synchronized host BIN is refreshed.

- [ ] **Step 5: Commit**

```bash
git add STM32/Core/Inc/app_flash_layout.h STM32/STM32F407XX_APP_FLASH.ld STM32/Bootloader/Core/Inc/bootloader_flash.h STM32/Bootloader/Core/Src/bootloader_flash.c STM32/Bootloader/Core/Src/bootloader_jump.c STM32/Bootloader/Core/Inc/bootloader_config.h STM32/tests/test_uart5_bootloader.py Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin
git commit -m "feat: make bootloader app validity persistent"
```

### Task 2: Bootloader Runtime State and Idle Heartbeat

**Files:**
- Modify: `STM32/Bootloader/Core/Inc/bootloader_config.h`
- Modify: `STM32/Bootloader/Core/Src/main.c`
- Test: `STM32/tests/test_uart5_bootloader.py`

**Interfaces:**
- Consumes: `Bootloader_FlashIsApplicationValid()` and `Bootloader_FlashSession.next_offset` from Task 1.
- Produces: frame `BOOTLOADER_FRAME_ID_STATUS = 0x92` with eight-byte payload `[state, app_valid, last_error, 0, received_bytes_le32]`.

- [ ] **Step 1: Write failing state-report tests**

Add assertions requiring:

```python
self.assertIn("#define BOOTLOADER_FRAME_ID_STATUS 0x92U", config)
self.assertIn("#define BOOTLOADER_STATUS_REPORT_PERIOD_MS 1000U", config)
self.assertIn("BOOTLOADER_STATE_WAITING", source)
self.assertIn("BOOTLOADER_STATE_RECEIVING", source)
self.assertIn("BOOTLOADER_STATE_VERIFIED", source)
self.assertIn("BOOTLOADER_STATE_ERROR", source)
self.assertIn("Bootloader_ReportStatusIfDue", source)
self.assertIn("Bootloader_WriteLe32(&payload[4], s_session.next_offset);", source)
```

- [ ] **Step 2: Run the focused test and confirm failure**

Run: `python3 -m unittest STM32/tests/test_uart5_bootloader.py -v`

Expected: FAIL because status reporting is absent.

- [ ] **Step 3: Implement cached state and USB status reporting**

Add a four-value enum with exact wire values 0–3 and RAM globals for state, cached App validity, last error, pending report, and last report tick. At startup compute App validity once. If invalid, enable USB before the handshake decision and remain in Bootloader.

`Bootloader_ReportStatusIfDue(HAL_GetTick())` must only run from the main loop, after command polling:

```c
payload[0] = (uint8_t)s_state;
payload[1] = s_app_valid;
payload[2] = s_last_error;
payload[3] = 0U;
Bootloader_WriteLe32(&payload[4], s_session.next_offset);
(void)Bootloader_UsbCdcSendFrame(BOOTLOADER_FRAME_ID_STATUS, payload, sizeof(payload));
```

Set `RECEIVING` after successful `ERASE`, `VERIFIED` after successful `VERIFY`, and `ERROR` on failures. Refresh cached App validity after every `ERASE` result and successful `VERIFY`. Set the pending flag during state changes; actual transmission occurs only after the blocking Flash command and its ACK/ERROR have completed.

- [ ] **Step 4: Run tests and build Bootloader**

Run: `python3 -m unittest STM32/tests/test_uart5_bootloader.py -v && make -C STM32 bootloader`

Expected: tests pass and Bootloader links within 32 KiB.

- [ ] **Step 5: Commit**

```bash
git add STM32/Bootloader/Core/Inc/bootloader_config.h STM32/Bootloader/Core/Src/main.c STM32/tests/test_uart5_bootloader.py
git commit -m "feat: report bootloader runtime status"
```

### Task 3: Python Status Dispatch Without Response Corruption

**Files:**
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/bootloader.py`
- Test: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_bootloader.py`

**Interfaces:**
- Produces: immutable `BootloaderStatus(state, app_valid, last_error, received_bytes)`.
- Produces: `BootloaderClient(driver, status_callback=None)`, `hello(...)`, and `read_status(...)`.
- Preserves: `program_image(...)` API and command sequence.

- [ ] **Step 1: Write failing decode and interleaving tests**

Add this interleaving test:

```python
status_frame = pack_frame(0x92, bytes.fromhex("01 00 00 00 F5 00 00 00"))
statuses = []
driver = FakeDriver([status_frame, ack(0x11, 0x11)])
client = BootloaderClient(driver, status_callback=statuses.append)
result = client._request_ack(0x11, 0x11, b"\x11", 0.05, 0.01)
self.assertEqual(result.command, 0x11)
self.assertEqual(statuses[0].received_bytes, 245)
```

Also test exact eight-byte validation and that `hello()` returns `BootloaderInfo` after an interleaved status frame.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run: `python3 -m unittest Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_bootloader.py -v`

Expected: FAIL because `BootloaderStatus` and callback dispatch do not exist.

- [ ] **Step 3: Implement one response loop**

Add:

```python
@dataclass(frozen=True)
class BootloaderStatus:
    state: int
    app_valid: bool
    last_error: int
    received_bytes: int
```

Keep a monotonic deadline inside `_send_and_read`; while waiting, decode every `0x92`, invoke the optional callback, and continue until the requested response arrives or the original deadline expires. Expose `hello()` as a public wrapper around `_request_info` and `read_status()` for Qt's idle monitor. Do not add threads or queues.

- [ ] **Step 4: Run package tests**

Run: `python3 -m unittest discover -s Linux_ROS_WS/src/stm32_jetson_serial_comm/tests -v`

Expected: all package tests pass.

- [ ] **Step 5: Commit**

```bash
git add Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/bootloader.py Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_bootloader.py
git commit -m "feat: dispatch bootloader status frames"
```

### Task 4: Qt Bootloader Detection, Display, and Retry

**Files:**
- Modify: `QT_Host/dm31_host/worker.py`
- Modify: `QT_Host/dm31_host/window.py`
- Modify: `QT_Host/tests/test_worker.py`
- Modify: `QT_Host/tests/test_window.py`

**Interfaces:**
- Consumes: `BootloaderClient.hello`, `BootloaderClient.read_status`, and `BootloaderStatus` from Task 3.
- Produces: Worker signal `bootloader_status_changed(object)`.
- Produces: one upgrade-page status label containing state, App validity, error, and received bytes.

- [ ] **Step 1: Write failing Worker and Window tests**

Extend the existing fake Bootloader and Worker signal set. Verify:

```python
worker.connect_port(choice)
self.assertEqual(states[-1][0], "BOOTLOADER")

worker.bootloader_status_changed.emit(BootloaderStatus(1, False, 0, 245))
self.assertIn("RECEIVING", window.bootloader_status_label.text())
self.assertIn("245", window.bootloader_status_label.text())
```

Add a failed-upgrade assertion that the Worker keeps the Bootloader driver, restarts its timer in `BOOTLOADER`, and accepts another upgrade with `request_from_app=False`.

- [ ] **Step 2: Run focused Qt tests and confirm failure**

Run: `PYTHONPATH=QT_Host QT_QPA_PLATFORM=offscreen QT_Host/.venv/bin/python -m unittest QT_Host/tests/test_worker.py QT_Host/tests/test_window.py -v`

Expected: FAIL because Bootloader detection/status UI is absent.

- [ ] **Step 3: Implement mode probing and monitoring**

In `connect_port`, open the selected port and call Bootloader `hello()` with a short timeout. On `INFO`, retain the client, set `BOOTLOADER`, disable the App request checkbox through the existing state handler, and start the existing timer. On Bootloader probe failure, close and reopen at 115200 using the current App setup path.

In `poll_once`, branch on `BOOTLOADER`: call `read_status()` with a non-blocking short timeout, emit `bootloader_status_changed`, and ignore only `SerialTimeoutError`. During upgrade pass the same status callback into the Bootloader client. On failure keep the open Bootloader transport and restart monitoring; on success retain the existing App reconnection flow.

Add one `QLabel` above the progress bar. Render exact state names with cached values; do not create another page, model, or settings object.

- [ ] **Step 4: Run all Qt tests**

Run: `PYTHONPATH=QT_Host QT_QPA_PLATFORM=offscreen QT_Host/.venv/bin/python -m unittest discover -s QT_Host/tests -v`

Expected: all Qt tests pass.

- [ ] **Step 5: Commit**

```bash
git add QT_Host/dm31_host/worker.py QT_Host/dm31_host/window.py QT_Host/tests/test_worker.py QT_Host/tests/test_window.py
git commit -m "feat: monitor bootloader status in Qt host"
```

### Task 5: Documentation and Full Verification

**Files:**
- Modify: `STM32/README.md`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/README.md`
- Modify: `QT_Host/README.md`
- Modify: `STM32/tests/test_uart5_protocol_readme.py`

**Interfaces:**
- Documents: first App installation, 352 KiB limit, metadata validity, failure recovery, `0x92` payload, and Qt direct-Bootloader mode.

- [ ] **Step 1: Write failing documentation assertions**

Require the STM32 README to contain `352 KiB`, `0x08060000`, `BOOTLOADER_STATUS`, `每 1 秒`, and the no-metadata recovery rule. Require host and Qt READMEs to describe unchecking the running-App request for first installation.

- [ ] **Step 2: Run documentation tests and confirm failure**

Run: `python3 -m unittest STM32/tests/test_uart5_protocol_readme.py -v`

Expected: FAIL because the new layout and status frame are undocumented.

- [ ] **Step 3: Update the three existing READMEs**

Document the exact protocol and workflow from the approved spec. Remove stale 480 KiB claims. State explicitly that SWD App images without Sector 7 metadata are rejected and must be reflashed through Bootloader.

- [ ] **Step 4: Run complete verification**

Run: `python3 -m unittest discover -s STM32/tests -v`

Expected: all STM32 source/protocol tests pass.

Run: `python3 -m unittest discover -s Linux_ROS_WS/src/stm32_jetson_serial_comm/tests -v`

Expected: all Python package tests pass.

Run: `PYTHONPATH=QT_Host QT_QPA_PLATFORM=offscreen QT_Host/.venv/bin/python -m unittest discover -s QT_Host/tests -v`

Expected: all Qt tests pass.

Run: `make -C STM32 app bootloader && cmp STM32/build/app/DM3.1_BAT_app.bin Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin`

Expected: both firmware images build and `cmp` exits 0.

- [ ] **Step 5: Commit**

```bash
git add STM32/README.md Linux_ROS_WS/src/stm32_jetson_serial_comm/README.md QT_Host/README.md STM32/tests/test_uart5_protocol_readme.py Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin
git commit -m "docs: describe fail-safe bootloader recovery"
```
