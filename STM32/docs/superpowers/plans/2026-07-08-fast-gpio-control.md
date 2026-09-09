# Fast GPIO Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply UART5 GPIO control requests before ultrasonic scheduling can delay the GPIO output change.

**Architecture:** Add a fast UART5 GPIO service that runs at the start of the main loop. It only consumes ready GPIO control frames; all other UART5 frames remain handled by the existing normal UART5 service.

**Tech Stack:** STM32 HAL C firmware, Python source-structure tests, Makefile build.

## Global Constraints

- Do not execute GPIO control in UART interrupt context.
- Do not convert ultrasonic UART transmit to interrupt or DMA mode in this change.
- Do not change UART5 protocol frame formats.
- Do not change bootloader request behavior.
- Preserve existing UART5 response semantics for GPIO control requests.

---

### Task 1: Add Failing Tests For Fast GPIO Service

**Files:**
- Modify: `STM32/tests/test_uart5_slave_status.py`
- Test: `STM32/tests/test_uart5_slave_status.py`

**Interfaces:**
- Consumes: existing `App_Uart5Slave_Run(uint32_t current_tick)`
- Produces: test expectations for `void App_Uart5Slave_RunFastGpio(uint32_t current_tick);`

- [ ] **Step 1: Write the failing test**

Add tests that assert:

```python
def test_fast_gpio_service_is_declared(self):
    header = self.uart5_header.read_text(encoding="utf-8")
    self.assertIn("void App_Uart5Slave_RunFastGpio(uint32_t current_tick);", header)

def test_main_loop_services_fast_gpio_before_ultrasonic(self):
    main = self.main_source.read_text(encoding="utf-8")
    fast_index = main.index("App_Uart5Slave_RunFastGpio(current_tick);")
    ultrasonic_index = main.index("App_UltrasonicManager_Run(current_tick);")
    self.assertLess(fast_index, ultrasonic_index)

def test_fast_gpio_service_consumes_only_gpio_control_frame(self):
    source = self.uart5_source.read_text(encoding="utf-8")
    fast_handler = source[source.index("void App_Uart5Slave_RunFastGpio"):source.index("void App_Uart5Slave_Run(uint32_t current_tick)")]
    self.assertIn("APP_COMM_FRAME_ID_GPIO_CONTROL_REQUEST", fast_handler)
    self.assertIn("App_RelayControl_Apply(&control)", fast_handler)
    self.assertIn("s_frame_ready = 0U;", fast_handler)
    self.assertIn("return;", fast_handler)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest STM32/tests/test_uart5_slave_status.py -q`

Expected: FAIL because `App_Uart5Slave_RunFastGpio` is not declared or called yet.

- [ ] **Step 3: Commit is skipped until implementation passes**

No commit after red; continue to Task 2.

---

### Task 2: Implement Fast GPIO Service

**Files:**
- Modify: `STM32/Core/Inc/app_uart5_slave.h`
- Modify: `STM32/Core/Src/app_uart5_slave.c`
- Modify: `STM32/Core/Src/main.c`
- Test: `STM32/tests/test_uart5_slave_status.py`

**Interfaces:**
- Consumes: `App_RelayControl_Apply(const App_CommGpioControl *control)`, `App_CommProtocol_DecodeGpioControlRequest(const App_CommFrame *frame, App_CommGpioControl *control)`
- Produces: `void App_Uart5Slave_RunFastGpio(uint32_t current_tick);`

- [ ] **Step 1: Add declaration**

Add to `STM32/Core/Inc/app_uart5_slave.h`:

```c
void App_Uart5Slave_RunFastGpio(uint32_t current_tick);
```

- [ ] **Step 2: Add fast service implementation**

Add before `App_Uart5Slave_Run()` in `STM32/Core/Src/app_uart5_slave.c`:

```c
void App_Uart5Slave_RunFastGpio(uint32_t current_tick)
{
  App_CommFrame frame;
  uint8_t frame_ready = 0U;
  uint32_t primask;
  (void)current_tick;

  if ((s_uart5 == NULL) || (s_bootloader_reset_pending != 0U))
  {
    return;
  }

  primask = __get_PRIMASK();
  __disable_irq();
  frame = s_rx_frame;
  frame_ready = s_frame_ready;
  if ((frame_ready != 0U) && (frame.frame_id == APP_COMM_FRAME_ID_GPIO_CONTROL_REQUEST))
  {
    s_frame_ready = 0U;
  }
  else
  {
    frame_ready = 0U;
  }
  __set_PRIMASK(primask);

  if (frame_ready == 0U)
  {
    return;
  }

  App_CommGpioControl control;
  uint8_t result;

  result = App_CommProtocol_DecodeGpioControlRequest(&frame, &control);
  if (result == APP_COMM_CONTROL_RESULT_OK)
  {
    result = App_RelayControl_Apply(&control);
  }

  App_Uart5Slave_SendControlResponse(control.seq, control.channel_id, result);
}
```

- [ ] **Step 3: Reorder main loop**

In `STM32/Core/Src/main.c`, call the fast service immediately after reading `current_tick`:

```c
uint32_t current_tick = App_PeriodicTick_Get();
App_Uart5Slave_RunFastGpio(current_tick);
App_UltrasonicManager_Run(current_tick);
App_Uart5Slave_Run(current_tick);
```

- [ ] **Step 4: Run targeted tests**

Run: `python -m pytest STM32/tests/test_uart5_slave_status.py STM32/tests/test_relay_control.py -q`

Expected: PASS.

- [ ] **Step 5: Build firmware**

Run: `make -C STM32 app`

Expected: build completes and produces `STM32/build/app/DM2.1_BAT_app.elf`.

- [ ] **Step 6: Commit**

```bash
git add STM32/Core/Inc/app_uart5_slave.h STM32/Core/Src/app_uart5_slave.c STM32/Core/Src/main.c STM32/tests/test_uart5_slave_status.py STM32/docs/superpowers/plans/2026-07-08-fast-gpio-control.md
git commit -m "Speed up GPIO control service"
```
