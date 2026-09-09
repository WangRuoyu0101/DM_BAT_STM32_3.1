# TIM6 Periodic Tick Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 10 ms TIM6 interrupt that increments a shared software tick and use independent tick deadlines to toggle LED-RUN every 500 ms.

**Architecture:** TIM6 generates only the base 10 ms time event. The HAL period-elapsed callback increments a `volatile uint32_t` counter; application tasks run from the main loop and retain their own previous-tick values, so no task clears or consumes another task's timing state.

**Tech Stack:** STM32F407 HAL, STM32CubeMX `.ioc`, TIM6 basic timer, GCC Makefile, Python standard-library structural tests.

---

## File Structure

- `DM2.1_BAT.ioc`: Persist TIM6, prescaler, period and NVIC configuration for future CubeMX regeneration.
- `Core/Src/main.c`: Own TIM6 handle/initialization, shared tick, timer start, callback and LED scheduler.
- `Core/Src/stm32f4xx_hal_msp.c`: Enable/disable TIM6 peripheral clock and configure its NVIC entry.
- `Core/Src/stm32f4xx_it.c`: Route `TIM6_DAC_IRQHandler()` to the HAL timer handler.
- `Core/Inc/stm32f4xx_it.h`: Declare the TIM6 interrupt handler.
- `Core/Inc/stm32f4xx_hal_conf.h`: Enable the HAL TIM module.
- `Makefile`: Compile `stm32f4xx_hal_tim.c` and `stm32f4xx_hal_tim_ex.c`.
- `tests/test_tim6_periodic_tick.py`: Verify the CubeMX configuration and generated-code interrupt/scheduler wiring.

### Task 1: Add failing structural tests

**Files:**
- Create: `tests/test_tim6_periodic_tick.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Tim6PeriodicTickTests(unittest.TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_ioc_defines_10_ms_tim6_interrupt(self):
        ioc = self.read("DM2.1_BAT.ioc")
        self.assertIn("Mcu.IP11=TIM6", ioc)
        self.assertIn("TIM6.Prescaler=8399", ioc)
        self.assertIn("TIM6.Period=99", ioc)
        self.assertIn("NVIC.TIM6_DAC_IRQn=true", ioc)

    def test_tim6_irq_is_routed_through_hal(self):
        interrupts = self.read("Core/Src/stm32f4xx_it.c")
        self.assertIn("extern TIM_HandleTypeDef htim6;", interrupts)
        self.assertIn("void TIM6_DAC_IRQHandler(void)", interrupts)
        self.assertIn("HAL_TIM_IRQHandler(&htim6);", interrupts)

    def test_timer_callback_only_increments_shared_tick(self):
        main = self.read("Core/Src/main.c")
        self.assertIn("volatile uint32_t g_periodic_tick = 0U;", main)
        self.assertIn("if (htim->Instance == TIM6)", main)
        self.assertIn("g_periodic_tick++;", main)

    def test_led_task_runs_every_50_ticks_in_main_loop(self):
        main = self.read("Core/Src/main.c")
        self.assertIn("#define LED_RUN_PERIOD_TICKS 50U", main)
        self.assertIn("(uint32_t)(current_tick - led_last_tick)", main)
        self.assertIn(
            "HAL_GPIO_TogglePin(LED_RUN_GPIO_Port, LED_RUN_Pin);",
            main,
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
python3 -m unittest tests/test_tim6_periodic_tick.py -v
```

Expected: four failures because TIM6 and the shared tick scheduler do not exist.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_tim6_periodic_tick.py
git commit -m "test: specify TIM6 periodic tick behavior"
```

### Task 2: Persist TIM6 in CubeMX configuration

**Files:**
- Modify: `DM2.1_BAT.ioc`

- [ ] **Step 1: Add TIM6 to the MCU peripheral list**

Add TIM6 after the existing USB entries and increase the peripheral count:

```ini
Mcu.IP11=TIM6
Mcu.IPNb=12
```

- [ ] **Step 2: Enable the TIM6 interrupt**

Add:

```ini
NVIC.TIM6_DAC_IRQn=true\:5\:0\:false\:false\:true\:true\:true\:true
```

Use preemption priority 5 so the 10 ms scheduler tick remains below the existing USB interrupt priority 0.

- [ ] **Step 3: Add the TIM6 parameters**

Add:

```ini
TIM6.IPParameters=Prescaler,Period
TIM6.Period=99
TIM6.Prescaler=8399
```

- [ ] **Step 4: Add TIM6 initialization ordering**

Append `MX_TIM6_Init` before USB initialization in `ProjectManager.functionlistsort`:

```ini
9-MX_TIM6_Init-TIM6-false-HAL-true,10-MX_USB_DEVICE_Init-USB_DEVICE-false-HAL-false
```

- [ ] **Step 5: Re-run the structural tests**

Run:

```bash
python3 -m unittest tests/test_tim6_periodic_tick.py -v
```

Expected: the `.ioc` test passes; code-wiring tests still fail.

- [ ] **Step 6: Commit the CubeMX configuration**

```bash
git add DM2.1_BAT.ioc
git commit -m "config: add TIM6 10ms update interrupt"
```

### Task 3: Add generated-style TIM6 HAL wiring

**Files:**
- Modify: `Core/Inc/stm32f4xx_hal_conf.h`
- Modify: `Core/Inc/stm32f4xx_it.h`
- Modify: `Core/Src/main.c`
- Modify: `Core/Src/stm32f4xx_hal_msp.c`
- Modify: `Core/Src/stm32f4xx_it.c`
- Modify: `Makefile`

- [ ] **Step 1: Enable the HAL TIM module**

In `Core/Inc/stm32f4xx_hal_conf.h`, replace:

```c
/* #define HAL_TIM_MODULE_ENABLED */
```

with:

```c
#define HAL_TIM_MODULE_ENABLED
```

- [ ] **Step 2: Add TIM6 source files to the Makefile**

After the UART source entry, add:

```make
Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim.c \
Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim_ex.c \
```

- [ ] **Step 3: Add the TIM6 handle and initialization prototype**

In `Core/Src/main.c`, add:

```c
TIM_HandleTypeDef htim6;
```

and:

```c
static void MX_TIM6_Init(void);
```

- [ ] **Step 4: Initialize TIM6**

Call `MX_TIM6_Init()` after `MX_GPIO_Init()` and add:

```c
static void MX_TIM6_Init(void)
{
  htim6.Instance = TIM6;
  htim6.Init.Prescaler = 8399;
  htim6.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim6.Init.Period = 99;
  htim6.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim6) != HAL_OK)
  {
    Error_Handler();
  }
}
```

- [ ] **Step 5: Configure TIM6 MSP and NVIC**

Add to `Core/Src/stm32f4xx_hal_msp.c`:

```c
void HAL_TIM_Base_MspInit(TIM_HandleTypeDef* htim_base)
{
  if (htim_base->Instance == TIM6)
  {
    __HAL_RCC_TIM6_CLK_ENABLE();
    HAL_NVIC_SetPriority(TIM6_DAC_IRQn, 5, 0);
    HAL_NVIC_EnableIRQ(TIM6_DAC_IRQn);
  }
}

void HAL_TIM_Base_MspDeInit(TIM_HandleTypeDef* htim_base)
{
  if (htim_base->Instance == TIM6)
  {
    __HAL_RCC_TIM6_CLK_DISABLE();
    HAL_NVIC_DisableIRQ(TIM6_DAC_IRQn);
  }
}
```

- [ ] **Step 6: Route the TIM6 interrupt**

Declare in `Core/Inc/stm32f4xx_it.h`:

```c
void TIM6_DAC_IRQHandler(void);
```

Add to `Core/Src/stm32f4xx_it.c`:

```c
extern TIM_HandleTypeDef htim6;

void TIM6_DAC_IRQHandler(void)
{
  HAL_TIM_IRQHandler(&htim6);
}
```

- [ ] **Step 7: Start the timer interrupt with error handling**

In `main()` after `MX_TIM6_Init()`:

```c
if (HAL_TIM_Base_Start_IT(&htim6) != HAL_OK)
{
  Error_Handler();
}
```

- [ ] **Step 8: Re-run tests**

Run:

```bash
python3 -m unittest tests/test_tim6_periodic_tick.py -v
```

Expected: IRQ-routing test passes; shared-tick and LED scheduling tests still fail.

- [ ] **Step 9: Commit HAL wiring**

```bash
git add Core/Inc/stm32f4xx_hal_conf.h Core/Inc/stm32f4xx_it.h Core/Src/main.c Core/Src/stm32f4xx_hal_msp.c Core/Src/stm32f4xx_it.c Makefile
git commit -m "feat: wire TIM6 periodic interrupt"
```

### Task 4: Add the shared tick and LED task

**Files:**
- Modify: `Core/Src/main.c`

- [ ] **Step 1: Define the LED period and shared tick**

In CubeMX user-code sections, add:

```c
#define LED_RUN_PERIOD_TICKS 50U
```

and:

```c
volatile uint32_t g_periodic_tick = 0U;
```

- [ ] **Step 2: Increment only the tick in the HAL callback**

Add in `/* USER CODE BEGIN 4 */`:

```c
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
  if (htim->Instance == TIM6)
  {
    g_periodic_tick++;
  }
}
```

- [ ] **Step 3: Add independent LED task state**

At the beginning of `main()` in `USER CODE BEGIN 1`, add:

```c
uint32_t led_last_tick = 0U;
```

- [ ] **Step 4: Schedule LED-RUN from the main loop**

Inside the main loop user-code section, add:

```c
uint32_t current_tick = g_periodic_tick;

if ((uint32_t)(current_tick - led_last_tick) >= LED_RUN_PERIOD_TICKS)
{
  led_last_tick = current_tick;
  HAL_GPIO_TogglePin(LED_RUN_GPIO_Port, LED_RUN_Pin);
}
```

- [ ] **Step 5: Run the full structural tests**

Run:

```bash
python3 -m unittest tests/test_tim6_periodic_tick.py -v
```

Expected: four tests pass.

- [ ] **Step 6: Commit scheduling behavior**

```bash
git add Core/Src/main.c
git commit -m "feat: schedule LED heartbeat from periodic tick"
```

### Task 5: Verify the firmware

**Files:**
- Verify: all modified firmware and configuration files

- [ ] **Step 1: Verify timer calculations**

Run:

```bash
python3 -c 'timer_hz=84000000; psc=8399; arr=99; print(timer_hz // (psc + 1) // (arr + 1))'
```

Expected:

```text
100
```

- [ ] **Step 2: Run structural tests**

Run:

```bash
python3 -m unittest tests/test_tim6_periodic_tick.py -v
```

Expected: four tests pass.

- [ ] **Step 3: Perform a clean firmware build**

Run:

```bash
make clean
make
```

Expected: exit code 0, no compiler warnings, and fresh `.elf`, `.hex`, and `.bin` files under `build/`.

- [ ] **Step 4: Inspect the final diff**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors introduced by hand-written files; only the intended firmware/configuration changes remain.

- [ ] **Step 5: Optional hardware verification**

Flash `build/DM2.1_BAT.bin`. Confirm PC10 toggles every 500 ms and LED-RUN completes one on/off cycle per second. Add a temporary second task with a different local `last_tick` to confirm one task does not consume another task's schedule.
