# CS1237 Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Acquire CS1237 data on PD11/PD14, expose query/channel selection through USB CDC/UART5, and convert/calibrate readings on Jetson.

**Architecture:** A focused STM32 module owns bit-banged CS1237 access and the latest snapshot. Existing application framing carries request/response messages. Jetson adds decoding, physical-unit conversion, calibration persistence, CLI controls, and ROS polling.

**Tech Stack:** STM32F407 HAL C, Make, Python 3 standard library, ROS2 Python, unittest/pytest.

## Global Constraints

- Default to internal temperature, 10 Hz, PGA 1, REF enabled.
- Differential/internal-short channels use PGA 128.
- PD11 is CLK and PD14 is bidirectional DIO.
- Use request/response communication; do not add unsolicited streaming.
- Keep all calibration and physical-unit conversion on Jetson.
- Add no dependencies.

---

### Task 1: STM32 CS1237 acquisition module

**Files:**
- Create: `STM32/Core/Inc/app_cs1237.h`
- Create: `STM32/Core/Src/app_cs1237.c`
- Create: `STM32/tests/test_cs1237_driver.py`
- Modify: `STM32/Core/Inc/main.h`
- Modify: `STM32/Core/Src/main.c`
- Modify: `STM32/Makefile`

**Interfaces:**
- Produces: `App_CS1237_Init(void)`, `App_CS1237_Run(void)`, `App_CS1237_SetChannel(App_CS1237_Channel)`, and `App_CS1237_GetSnapshot(App_CS1237_Snapshot *)`.
- Snapshot contains signed raw ADC, channel, valid flag, and error code.

- [ ] **Step 1: Write the failing structural/behavior test**

Add assertions that the module exists, maps CLK to PD11 and DIO to PD14,
builds temperature configuration with PGA1, builds CHA/INS with PGA128,
sign-extends bit 23, rejects channel 1, invalidates snapshots on channel
change, and ignores three settling conversions.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest STM32/tests/test_cs1237_driver.py -v`
Expected: FAIL because `app_cs1237.h` and `app_cs1237.c` do not exist.

- [ ] **Step 3: Implement the minimum driver**

Use HAL GPIO reads/writes and short cycle delays. Poll DIO in
`App_CS1237_Run`; never wait there for readiness. Use bounded waits only for
configuration write/read during initialization and explicit channel changes.
Store configuration and snapshot in module-static state.

- [ ] **Step 4: Integrate with application build and loop**

Add the source to `C_SOURCES`, define pin macros in `main.h`, initialize after
GPIO setup, and service the driver in the cooperative main loop.

- [ ] **Step 5: Run test and build**

Run: `python3 -m unittest STM32/tests/test_cs1237_driver.py -v`
Expected: PASS.

Run: `make -C STM32 app`
Expected: app ELF/HEX/BIN build successfully.

### Task 2: Firmware application protocol

**Files:**
- Modify: `STM32/Core/Inc/app_comm_protocol.h`
- Modify: `STM32/Core/Src/app_comm_protocol.c`
- Modify: `STM32/Core/Src/app_uart5_slave.c`
- Create: `STM32/tests/test_cs1237_protocol.py`

**Interfaces:**
- Consumes: CS1237 snapshot and channel-selection interfaces from Task 1.
- Produces: query `0x06`/response `0x86` and select `0x07`/response `0x87`.

- [ ] **Step 1: Write failing protocol tests**

Assert exact frame IDs, payload lengths, decode functions, signed little-endian
snapshot encoding, channel-selection result encoding, and handlers in the
shared UART5/USB endpoint.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest STM32/tests/test_cs1237_protocol.py -v`
Expected: FAIL because CS1237 frame IDs and handlers are absent.

- [ ] **Step 3: Add request decoding and responses**

Decode one-byte query payloads and two-byte channel requests. Query responses
contain `seq`, four raw ADC bytes, channel, valid, and error. Selection
responses contain `seq`, requested channel, and result. Invalid lengths use
the existing error response.

- [ ] **Step 4: Run protocol and regression tests**

Run: `python3 -m unittest discover -s STM32/tests -v`
Expected: all STM32 tests PASS.

### Task 3: Jetson protocol, conversion, and calibration

**Files:**
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/messages.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/serial_host.py`
- Create: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/cs1237.py`
- Create: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_cs1237.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_messages.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_serial_host.py`

**Interfaces:**
- Produces: `CS1237Status`, `CS1237ChannelResult`,
  `temperature_celsius(raw, reference_temperature=23.0, reference_adc=4100000)`,
  force two-point conversion, and JSON calibration load/save.

- [ ] **Step 1: Write failing decode and conversion tests**

Cover signed raw decode, malformed payload rejection, temperature reference
point identity, force zero/span conversion, zero-span rejection, missing-file
defaults, JSON round trip, and atomic replacement.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_cs1237.py Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_messages.py Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_serial_host.py -q`
Expected: FAIL because CS1237 host APIs are absent.

- [ ] **Step 3: Implement protocol and calibration**

Use `int.from_bytes(..., signed=True)` and Python's `json`, `pathlib`, and
`os.replace`. Represent incomplete force calibration explicitly and return no
newton value until zero and span are valid.

- [ ] **Step 4: Run focused tests**

Run the focused pytest command from Step 2.
Expected: PASS.

### Task 4: Jetson CLI/ROS polling, documentation, and final verification

**Files:**
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/serial_link_cli.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/serial_node_core.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/stm32_serial_node.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/README.md`
- Modify: `STM32/README.md`
- Modify relevant tests under `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/`

**Interfaces:**
- Consumes: host/query and conversion APIs from Task 3.
- Produces: query/select/calibration CLI behavior and 10 Hz ROS polling with raw and converted outputs.

- [ ] **Step 1: Write failing CLI/core/source tests**

Assert CLI options for CS1237 query, channel selection, zero capture, and known
force capture. Assert core polling and ROS parameters/topics are wired.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest Linux_ROS_WS/src/stm32_jetson_serial_comm/tests -q`
Expected: FAIL on missing CS1237 CLI/node behavior.

- [ ] **Step 3: Implement the minimal host UX**

Reuse the current serial link command and node timer model. Default CS1237 poll
rate is 10 Hz. Publish raw/status text and converted temperature or force only
when valid and calibrated. Document commands and channel values.

- [ ] **Step 4: Run complete verification**

Run: `python3 -m unittest discover -s STM32/tests -v`
Expected: all PASS.

Run: `python3 -m pytest Linux_ROS_WS/src/stm32_jetson_serial_comm/tests -q`
Expected: all PASS.

Run: `make -C STM32 app`
Expected: successful application build and firmware copy.
