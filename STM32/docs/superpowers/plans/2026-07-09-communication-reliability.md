# Communication Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make USB CDC responses reliable under endpoint backpressure, expand RTK transfers to the protocol limit, and expose communication diagnostics without unsolicited STM32 reports.

**Architecture:** Keep the existing request/response protocol and main-loop processing. Add a two-entry USB transmit FIFO inside `app_uart5_slave.c`, derive RTK chunk limits from the 250-byte application payload, and append cumulative diagnostics to the existing status response while retaining legacy Jetson decoding.

**Tech Stack:** STM32F4 HAL/C11, USB Device CDC, Python 3 standard library `unittest`, ROS2 Python package.

## Global Constraints

- STM32 sends no unsolicited application frames.
- Application frame format and CRC8 remain unchanged.
- `APP_COMM_MAX_PAYLOAD_SIZE` is exactly 250 bytes.
- USB CDC line coding, UART5, and USART6 baud rates remain unchanged.
- No dynamic allocation or new dependency.
- `STM32/docs/UM982模块板说明书.pdf` is an untracked user file and must not be staged.

---

### Task 1: Expand application and RTK payloads

**Files:**
- Modify: `STM32/Core/Inc/app_comm_protocol.h`
- Modify: `STM32/Core/Src/app_uart5_slave.c`
- Modify: `STM32/tests/test_comm_protocol_frame.py`
- Modify: `STM32/tests/test_rtk_bridge.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/rtk_bridge.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_rtk_bridge.py`

**Interfaces:**
- Produces: 250-byte application payload; RTK request chunks of 249 bytes and responses containing 248 data bytes.

- [ ] **Step 1: Write failing boundary tests**

Update STM32 tests to require:

```python
self.assertIn("#define APP_COMM_MAX_PAYLOAD_SIZE 250U", header)
self.assertIn("#define APP_COMM_RTK_WRITE_DATA_MAX 249U", header)
self.assertIn("#define APP_COMM_RTK_READ_DATA_MAX 248U", header)
```

Update Jetson RTK tests to send 250 bytes and require host request payload
lengths of 250 and 2 bytes, proving a 249+1 split.

- [ ] **Step 2: Verify RED**

Run:

```bash
python3 -m unittest STM32/tests/test_comm_protocol_frame.py STM32/tests/test_rtk_bridge.py Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_rtk_bridge.py -v
```

Expected: failures show STM32 limits are 32/31/30 and Jetson chunks are 31.

- [ ] **Step 3: Implement minimal constants**

Set:

```c
#define APP_COMM_MAX_PAYLOAD_SIZE 250U
#define APP_COMM_RTK_WRITE_DATA_MAX (APP_COMM_MAX_PAYLOAD_SIZE - 1U)
#define APP_COMM_RTK_READ_DATA_MAX (APP_COMM_MAX_PAYLOAD_SIZE - 2U)
```

Set Jetson `RTK_WRITE_CHUNK_SIZE = 249`. Existing encode, parse, and RTK loops
already use these constants and need no new abstraction.

- [ ] **Step 4: Verify GREEN**

Run the command from Step 2. Expected: all selected tests pass.

### Task 2: Queue USB CDC responses

**Files:**
- Modify: `STM32/Core/Src/app_uart5_slave.c`
- Modify: `STM32/tests/test_uart5_slave_status.py`

**Interfaces:**
- Produces: private two-entry FIFO and main-loop pump; UART5 behavior unchanged.

- [ ] **Step 1: Write failing queue tests**

Require two frame slots, head/count/in-flight state, copied encoded frames,
and this pump behavior:

```c
result = CDC_Transmit_FS(frame->data, frame->length);
if (result == USBD_OK) { /* retain until transmit-complete callback */ }
else if (result == USBD_BUSY) { /* count and retain */ }
else { /* count failure and dequeue */ }
```

Also require queue-full accounting and a pump call from
`App_Uart5Slave_Process()`.

- [ ] **Step 2: Verify RED**

Run:

```bash
python3 -m unittest STM32/tests/test_uart5_slave_status.py -v
```

Expected: failures identify the missing FIFO and pump.

- [ ] **Step 3: Implement the FIFO**

Add a private frame type containing `uint16_t length` and a 255-byte byte
array, plus exactly two static entries. USB `SendFrame` enqueues a copied
encoded frame. The process function attempts only the oldest queued frame
once per pass, applying the `USBD_OK`/`USBD_BUSY`/failure behavior above. The
USB transmit-complete callback releases a successfully submitted frame.
Use saturating increment helpers for counters.

- [ ] **Step 4: Verify GREEN**

Run the command from Step 2. Expected: all tests pass.

### Task 3: Add cumulative diagnostics and backward-compatible Jetson decoding

**Files:**
- Modify: `STM32/Core/Inc/app_rtk_bridge.h`
- Modify: `STM32/Core/Src/app_rtk_bridge.c`
- Modify: `STM32/Core/Src/app_uart5_slave.c`
- Modify: `STM32/tests/test_rtk_bridge.py`
- Modify: `STM32/tests/test_uart5_slave_status.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/messages.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/serial_link_cli.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_messages.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_serial_link.py`

**Interfaces:**
- Produces: `App_RtkBridgeDiagnostics` getter and an extended 29-byte status payload.
- Preserves: decoding of the legacy seven-byte payload.

- [ ] **Step 1: Write failing diagnostics tests**

Require an STM32 snapshot type:

```c
typedef struct {
  uint32_t overflow_bytes;
  uint32_t uart_errors;
  uint16_t rx_high_water;
} App_RtkBridgeDiagnostics;
```

Require status offsets 7, 11, 15, 19, 23, and 27 as specified by the design.
In Python, require `decode_slave_status()` to accept both 7 and 29 bytes and
populate optional diagnostics with zero for legacy firmware.

- [ ] **Step 2: Verify RED**

Run:

```bash
python3 -m unittest STM32/tests/test_rtk_bridge.py STM32/tests/test_uart5_slave_status.py Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_messages.py Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_serial_link.py -v
```

Expected: failures identify absent counters and extended fields.

- [ ] **Step 3: Implement STM32 diagnostics**

Track saturating USART6 overflow-byte and error-callback counters and the
maximum `(head - tail)` occupancy. Add a getter that snapshots them with IRQs
masked. Append these values and the USB counters to the status response using
explicit little-endian byte assignments.

- [ ] **Step 4: Implement Jetson decoding and display**

Extend `SlaveStatus` with defaulted diagnostic integer fields and an
`extended` boolean. Decode exactly 7 or 29 bytes. Preserve the existing status
text and append diagnostic key/value fields only when `extended` is true.

- [ ] **Step 5: Verify GREEN**

Run the command from Step 2. Expected: all selected tests pass.

### Task 4: Full verification and delivery

**Files:**
- Modify only if a verification failure exposes an in-scope defect.

- [ ] **Step 1: Run all unit tests**

```bash
python3 -m unittest discover -s STM32/tests -v
python3 -m unittest discover -s Linux_ROS_WS/src/stm32_jetson_serial_comm/tests -v
```

Expected: zero failures and zero errors.

- [ ] **Step 2: Clean-build firmware**

```bash
make -C STM32 clean
make -C STM32 GCC_PATH=/Users/lion/58WorkSpace/CodeWorkSpace/DM2.1_BAT/STM32/toolchains/arm-none-eabi-15.2/bin app
```

Expected: exit code 0 and generated application binary.

- [ ] **Step 3: Inspect and commit**

```bash
git diff --check
git status --short
git add <only implementation, tests, and plan files>
git commit -m "feat: improve STM32 communication reliability"
```

Do not add the UM982 PDF.
