# DM3.1 P0 Hardware Adaptation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing DM2.1 firmware electrically safe and functional on the DM3.1 board for the changed CS1237 and relay-control pins.

**Architecture:** Keep the existing six-channel UART5 GPIO protocol and relay-control module. Remap channel `0x01` to `FLASH_CTR/PC5`, channel `0x05` to `FLASH/PB1`, move CS1237 to `PB14/PD8`, and leave PA7 as an input until fan support is implemented separately.

**Tech Stack:** STM32F407 HAL C, STM32CubeMX `.ioc`, Python `unittest` source-contract tests, ROS-independent Python host utilities.

## Global Constraints

- Do not add dependencies or a new protocol frame.
- GPIO channel IDs and bitmap positions remain `0x01` through `0x06`.
- Relay and optocoupler outputs must initialize low.
- PA7 must never be configured or driven as an output in DM3.1 P0.
- Fan PWM/tachometer behavior, KEY1/KEY2, and RGB are out of scope.

---

### Task 1: Move CS1237 to PB14 and PD8

**Files:**
- Modify: `STM32/tests/test_cs1237_driver.py`
- Modify: `STM32/Core/Inc/main.h`
- Modify: `STM32/Core/Src/main.c`
- Modify: `STM32/DM2.1_BAT.ioc`

**Interfaces:**
- Produces: `CS1237_CLK_Pin=GPIO_PIN_14/GPIOB`, `CS1237_DIO_Pin=GPIO_PIN_8/GPIOD`.
- Preserves: `App_CS1237_*` API and dynamic DIO direction switching.

- [ ] **Step 1: Write the failing pin-contract test**

Replace the old pin assertions with:

```python
self.assertIn("CS1237_CLK_Pin GPIO_PIN_14", main_h)
self.assertIn("CS1237_CLK_GPIO_Port GPIOB", main_h)
self.assertIn("CS1237_DIO_Pin GPIO_PIN_8", main_h)
self.assertIn("CS1237_DIO_GPIO_Port GPIOD", main_h)
self.assertIn("PB14.GPIO_Label=CS1237_CLK", ioc)
self.assertIn("PD8.GPIO_Label=CS1237_DIO", ioc)
self.assertNotIn("PD11.GPIO_Label=CS1237_CLK", ioc)
self.assertNotIn("PD14.GPIO_Label=CS1237_DIO", ioc)
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python3 -m unittest STM32/tests/test_cs1237_driver.py -v`

Expected: FAIL because the current definitions are PD11/PD14.

- [ ] **Step 3: Apply the minimum pin migration**

Update `main.h`, `MX_GPIO_Init`, and `.ioc` so PB14 starts low as an output and PD8 starts as an input. Remove PD11/PD14 CS1237 configuration.

- [ ] **Step 4: Run the test and verify GREEN**

Run: `python3 -m unittest STM32/tests/test_cs1237_driver.py -v`

Expected: PASS.

### Task 2: Remove motor-X outputs and map the new flash outputs

**Files:**
- Modify: `STM32/tests/test_relay_control.py`
- Modify: `STM32/tests/test_comm_protocol_frame.py`
- Modify: `STM32/Core/Inc/app_comm_protocol.h`
- Modify: `STM32/Core/Src/app_relay_control.c`
- Modify: `STM32/Core/Src/main.c`
- Modify: `STM32/DM2.1_BAT.ioc`

**Interfaces:**
- Produces: channel `0x01` = `APP_COMM_GPIO_CHANNEL_FLASH_CTR` on PC5.
- Produces: channel `0x05` = `APP_COMM_GPIO_CHANNEL_FLASH` on PB1.
- Preserves: channels `0x02`, `0x03`, `0x04`, `0x06` and bitmap ordering.

- [ ] **Step 1: Write failing relay and safety assertions**

Assert these mappings and safety properties:

```python
self.assertIn("{APP_COMM_GPIO_CHANNEL_FLASH_CTR, GPIOC, GPIO_PIN_5}", source)
self.assertIn("{APP_COMM_GPIO_CHANNEL_FLASH, GPIOB, GPIO_PIN_1}", source)
self.assertNotIn("MOROTX", source)
self.assertNotIn("RESERVED", source)
self.assertNotIn("HAL_GPIO_WritePin(GPIOA, GPIO_PIN_7", main)
self.assertNotIn("GPIO_PIN_4|LED_RUN_Pin", main)
self.assertIn("GPIO_PIN_5|LED_RUN_Pin", main)
self.assertIn("PA7.Signal=GPIO_Input", ioc)
self.assertNotIn("PC4.Signal=GPIO_Output", ioc)
self.assertIn("PC5.Signal=GPIO_Output", ioc)
```

Update protocol assertions to require:

```python
#define APP_COMM_GPIO_CHANNEL_FLASH_CTR 0x01U
#define APP_COMM_GPIO_CHANNEL_FLASH 0x05U
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m unittest STM32/tests/test_relay_control.py STM32/tests/test_comm_protocol_frame.py -v`

Expected: FAIL on the old MOTORX/RESERVED mappings.

- [ ] **Step 3: Implement the six-channel remap**

Rename the two constants, map PC5/PB1, initialize PC5 and PB1 low, configure PA7 as input, and remove PC4 output configuration.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python3 -m unittest STM32/tests/test_relay_control.py STM32/tests/test_comm_protocol_frame.py -v`

Expected: PASS.

### Task 3: Synchronize Jetson names and documentation

**Files:**
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_gpio_cli.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_serial_node_core.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/gpio_cli.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/serial_node_core.py`
- Modify: `STM32/tests/test_uart5_protocol_readme.py`
- Modify: `STM32/README.md`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/README.md`

**Interfaces:**
- CLI names: `flash_ctr`, `led`, `bee`, `motor`, `flash`, `sound`.
- Wire IDs remain `0x01` through `0x06`.

- [ ] **Step 1: Write failing host-name tests**

Add assertions that `flash_ctr` maps to `0x01`, `flash` maps to `0x05`, and formatted bitmap output uses the same names. Update README tests to require `SIGNAL-FLASH-CTR/PC5` and `SIGNAL-FLASH/PB1` and reject the two old names.

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m unittest Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_gpio_cli.py Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_serial_node_core.py STM32/tests/test_uart5_protocol_readme.py -v`

Expected: FAIL because host names and documentation still use `morotx_sw` and `reserved`.

- [ ] **Step 3: Rename host-visible channels and tables**

Change only channel names and documentation; keep numeric IDs, response parsing, and frame layout unchanged.

- [ ] **Step 4: Run focused and full verification**

Run:

```sh
python3 -m unittest discover -s STM32/tests -v
python3 -m unittest discover -s Linux_ROS_WS/src/stm32_jetson_serial_comm/tests -v
make -C STM32 app
```

Expected: all tests PASS and the STM32 application builds successfully.
