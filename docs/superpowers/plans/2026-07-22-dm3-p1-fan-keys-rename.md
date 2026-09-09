# DM3.1 P1 Fan, Keys, and Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four-level fan control, dual RPM measurement, debounced keys, Jetson access, and rename all current project artifacts from DM2.1_BAT to DM3.1_BAT.

**Architecture:** One `app_board_io` module owns TIM2 PWM, TIM3 capture state, and key debounce. Two new request/response pairs extend the existing USB CDC/UART5 protocol; Jetson reuses the current message and request infrastructure. Existing build variables perform the artifact and firmware-copy rename from one `TARGET` change.

**Tech Stack:** STM32F407 HAL C, STM32CubeMX `.ioc`, Make, Python 3 standard library/unittest, ROS2 Python package.

## Global Constraints

- Fan levels are exactly 1=25%, 2=50%, 3=75%, 4=100%; power-on default is level 2.
- PA5 is shared 25 kHz PWM; PA6/PA7 are independent tach inputs with a configurable 2 pulses/revolution default.
- PE15/PE13 use pull-ups, active-low input, and 20 ms debounce.
- Existing protocol IDs and GPIO channel IDs remain unchanged.
- RGB/PB13 is not configured.
- Current artifacts use `DM3.1_BAT`; historical DM2.1 baseline references are not rewritten.
- No new third-party dependencies.

---

### Task 1: Rename current project artifacts and firmware path

**Files:**
- Rename: `STM32/DM2.1_BAT.ioc` -> `STM32/DM3.1_BAT.ioc`
- Rename/generated replacement: `Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/DM2.1_BAT_app.bin` -> `Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin`
- Modify: `STM32/Makefile`
- Modify: `STM32/tests/test_cs1237_driver.py`
- Modify: `STM32/tests/test_relay_control.py`
- Modify: `STM32/tests/test_tim6_periodic_tick.py`
- Modify: `STM32/tests/test_uart5_slave_status.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_firmware_sync.py`
- Modify: `STM32/README.md`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/README.md`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/README.md`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/bootloader_cli.py`

**Interfaces:**
- Produces: `STM32/DM3.1_BAT.ioc`, `build/app/DM3.1_BAT_app.bin`, `firmware/DM3.1_BAT_app.bin`.
- Preserves: build targets `app`, `bootloader`, and the existing firmware copy rule.

- [ ] **Step 1: Update tests first**

Change `.ioc` readers to `DM3.1_BAT.ioc` and add firmware assertions:

```python
self.assertIn("TARGET = DM3.1_BAT", makefile)
self.assertIn("DM3.1_BAT_app.bin", makefile_output_contract)
self.assertFalse((firmware_dir / "DM2.1_BAT_app.bin").exists())
```

- [ ] **Step 2: Run rename tests and verify RED**

Run: `python3 -m unittest STM32/tests/test_cs1237_driver.py STM32/tests/test_relay_control.py STM32/tests/test_tim6_periodic_tick.py Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_firmware_sync.py -v`

Expected: FAIL because `DM3.1_BAT.ioc` and the new target do not exist.

- [ ] **Step 3: Apply the minimum rename**

Rename the `.ioc`, set:

```make
TARGET = DM3.1_BAT
```

and change CubeMX values to:

```text
ProjectManager.ProjectFileName=DM3.1_BAT.ioc
ProjectManager.ProjectName=DM3.1_BAT
```

Update current README/CLI examples, remove the old generated firmware, and let `make app` create the new one.

- [ ] **Step 4: Verify GREEN**

Run the focused tests again; expected PASS.

### Task 2: Add TIM2/TIM3 board IO firmware

**Files:**
- Create: `STM32/Core/Inc/app_board_io.h`
- Create: `STM32/Core/Src/app_board_io.c`
- Create: `STM32/tests/test_board_io.py`
- Modify: `STM32/Core/Src/main.c`
- Modify: `STM32/Core/Src/stm32f4xx_hal_msp.c`
- Modify: `STM32/Core/Src/stm32f4xx_it.c`
- Modify: `STM32/Core/Inc/stm32f4xx_it.h`
- Modify: `STM32/Core/Inc/main.h`
- Modify: `STM32/DM3.1_BAT.ioc`
- Modify: `STM32/Makefile`

**Interfaces:**
- Produces: `App_BoardIO_Init`, `App_BoardIO_SetFanLevel`, `App_BoardIO_Run`, `App_BoardIO_TachCapture`, `App_BoardIO_GetSnapshot`.
- Produces: `App_BoardIO_Snapshot {fan_level, fan1_rpm, fan2_rpm, key_bitmap}`.

- [ ] **Step 1: Write `test_board_io.py` before production code**

The test must require these contracts:

```python
self.assertIn("APP_BOARD_IO_DEFAULT_FAN_LEVEL 2U", source)
self.assertIn("APP_BOARD_IO_FAN_PULSES_PER_REV 2U", source)
self.assertIn("APP_BOARD_IO_KEY_DEBOUNCE_TICKS 10U", source)
self.assertIn("APP_BOARD_IO_TACH_TIMEOUT_TICKS 750U", source)
self.assertIn("HAL_TIM_PWM_Start", source)
self.assertIn("HAL_TIM_IC_Start_IT", source)
self.assertIn("App_BoardIO_Run(current_tick);", main)
self.assertIn("TIM2.Prescaler=0", ioc)
self.assertIn("TIM2.Period=3359", ioc)
self.assertIn("TIM3.Prescaler=839", ioc)
self.assertIn("PE13.GPIO_Label=KEY2", ioc)
self.assertIn("PE15.GPIO_Label=KEY1", ioc)
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python3 -m unittest STM32/tests/test_board_io.py -v`

Expected: FAIL because `app_board_io` does not exist.

- [ ] **Step 3: Add the minimal module and timer wiring**

Use this public snapshot and result shape:

```c
typedef struct {
  uint8_t fan_level;
  uint16_t fan1_rpm;
  uint16_t fan2_rpm;
  uint8_t key_bitmap;
} App_BoardIO_Snapshot;

HAL_StatusTypeDef App_BoardIO_Init(TIM_HandleTypeDef *pwm_timer, TIM_HandleTypeDef *tach_timer);
uint8_t App_BoardIO_SetFanLevel(uint8_t level);
void App_BoardIO_Run(uint32_t current_tick);
void App_BoardIO_TachCapture(TIM_HandleTypeDef *timer);
void App_BoardIO_GetSnapshot(App_BoardIO_Snapshot *snapshot);
```

TIM capture ISR stores timestamps only. `Run()` computes RPM, applies the 750-tick timeout, and debounces keys. `SetFanLevel()` rejects values outside 1..4 without changing the prior level.

- [ ] **Step 4: Run board IO test and full STM32 tests**

Run: `python3 -m unittest STM32/tests/test_board_io.py -v && python3 -m unittest discover -s STM32/tests`

Expected: PASS.

### Task 3: Extend STM32 application protocol

**Files:**
- Modify: `STM32/tests/test_comm_protocol_frame.py`
- Modify: `STM32/tests/test_uart5_slave_status.py`
- Modify: `STM32/Core/Inc/app_comm_protocol.h`
- Modify: `STM32/Core/Src/app_comm_protocol.c`
- Modify: `STM32/Core/Src/app_uart5_slave.c`

**Interfaces:**
- Produces: IDs `0x0A/0x8A` and `0x0B/0x8B`.
- Consumes: `App_BoardIO_SetFanLevel()` and `App_BoardIO_GetSnapshot()`.

- [ ] **Step 1: Add failing protocol assertions**

Require:

```c
#define APP_COMM_FRAME_ID_FAN_CONTROL_REQUEST 0x0AU
#define APP_COMM_FRAME_ID_BOARD_IO_QUERY 0x0BU
#define APP_COMM_FRAME_ID_FAN_CONTROL_RESPONSE 0x8AU
#define APP_COMM_FRAME_ID_BOARD_IO_RESPONSE 0x8BU
```

and dispatch/source assertions for `App_CommProtocol_DecodeFanControlRequest`, `App_CommProtocol_DecodeBoardIOQuery`, `App_BoardIO_SetFanLevel`, and the 7-byte board IO response.

- [ ] **Step 2: Verify RED**

Run: `python3 -m unittest STM32/tests/test_comm_protocol_frame.py STM32/tests/test_uart5_slave_status.py -v`

Expected: FAIL because the new IDs and dispatch branches are missing.

- [ ] **Step 3: Implement minimum decode and response paths**

Use request payloads `seq+level` and `seq`; responses `seq+level+result` and `seq+level+rpm1LE+rpm2LE+keys`. Invalid levels return result `0x02`.

- [ ] **Step 4: Verify GREEN**

Run focused and complete STM32 tests; expected PASS.

### Task 4: Add Jetson message, host, and CLI support

**Files:**
- Create: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/fan_cli.py`
- Create: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_fan_cli.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/messages.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/serial_host.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_messages.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_serial_host.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/setup.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_setup_entry_points.py`

**Interfaces:**
- Produces: `FanControlResult`, `BoardIOStatus`, `SerialHost.set_fan_level()`, `SerialHost.query_board_io()`.
- Produces CLI: `stm32_fan set 1|2|3|4` and `stm32_fan status`.

- [ ] **Step 1: Write failing decoder, host, CLI, and entry-point tests**

Decoder example:

```python
self.assertEqual(
    decode_board_io_status(bytes([7, 2, 0xD0, 0x07, 0xB8, 0x0B, 0x03])),
    BoardIOStatus(seq=7, fan_level=2, fan1_rpm=2000, fan2_rpm=3000, key_bitmap=3),
)
```

Note: the response is 7 bytes, matching `seq+level+2+2+keys`.

- [ ] **Step 2: Verify RED**

Run the four focused Jetson tests; expected import/assertion failures for missing features.

- [ ] **Step 3: Implement with existing request helpers**

Reuse `SerialHost.request()` and existing CLI device/baudrate/timeout arguments. Do not add a separate transport layer.

- [ ] **Step 4: Verify GREEN**

Run focused tests and all Jetson tests; expected PASS.

### Task 5: Publish board IO in ROS and finish docs/build verification

**Files:**
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/serial_node_core.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/stm32_serial_node.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_serial_node_core.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_stm32_serial_node_source.py`
- Modify: `STM32/README.md`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/README.md`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/README.md`
- Modify: `docs/DM3.1硬件变更与代码适配清单.md`

**Interfaces:**
- Publishes: `/stm32/fan_rpm`, `/stm32/fan_level`, `/stm32/key_bitmap`, `/stm32/board_io_text`.

- [ ] **Step 1: Write failing ROS source and core tests**

Require `poll_board_io()`, the four topic names, and human text containing level, both RPM values, and key bitmap.

- [ ] **Step 2: Verify RED**

Run: `python3 -m unittest Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_serial_node_core.py Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_stm32_serial_node_source.py -v`

- [ ] **Step 3: Add the minimum polling/publication path and update docs**

Reuse the existing nonblocking serial lock and timer pattern. Update current build, bootloader, synchronization, fan, key, and CLI examples to DM3.1 names.

- [ ] **Step 4: Full clean verification**

Run:

```sh
python3 -m unittest discover -s STM32/tests
python3 -m unittest discover -s Linux_ROS_WS/src/stm32_jetson_serial_comm/tests
make -C STM32 clean
make -C STM32 app
make -C STM32 bootloader
```

Verify:

```sh
test -f STM32/build/app/DM3.1_BAT_app.bin
test -f STM32/build/bootloader/DM3.1_BAT_bootloader.bin
test -f Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin
test ! -e Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/DM2.1_BAT_app.bin
```

Expected: all tests and builds pass; only DM3.1 current artifacts remain.
