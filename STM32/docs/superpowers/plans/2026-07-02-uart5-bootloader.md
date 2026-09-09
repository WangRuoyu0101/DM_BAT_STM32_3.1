# UART5 Bootloader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dedicated UART5 bootloader at `0x08000000` and relocate the main application to `0x08008000`.

**Architecture:** Keep all implementation inside `STM32/`. Add a small bootloader source tree with isolated config, protocol, Flash, and jump modules. Relocate the existing app through a new linker script plus `SCB->VTOR` setup, and extend the Makefile with separate bootloader/app outputs.

**Tech Stack:** STM32F407 HAL, GCC Makefile build, Python unittest text-structure tests, UART5 115200 8N1, Flash HAL APIs.

---

## File Map

- Create `STM32/tests/test_uart5_bootloader.py`: text-level TDD coverage for Flash layout, linker scripts, Makefile targets, bootloader modules, docs, range checks, vector validation, and app VTOR relocation.
- Create `STM32/Core/Inc/app_flash_layout.h`: shared app/bootloader address constants.
- Modify `STM32/Core/Src/system_stm32f4xx.c`: enable app vector-table relocation through `SCB->VTOR = APP_FLASH_BASE;`.
- Create `STM32/STM32F407XX_APP_FLASH.ld`: relocated application linker script.
- Create `STM32/STM32F407XX_BOOT_FLASH.ld`: 32 KB bootloader linker script.
- Create `STM32/Bootloader/Core/Inc/bootloader_config.h`: bootloader constants and protocol IDs.
- Create `STM32/Bootloader/Core/Inc/bootloader_protocol.h` and `STM32/Bootloader/Core/Src/bootloader_protocol.c`: frame parsing/encoding using CRC8.
- Create `STM32/Bootloader/Core/Inc/bootloader_flash.h` and `STM32/Bootloader/Core/Src/bootloader_flash.c`: app range checks, sector erase, word programming, image CRC32, session tracking.
- Create `STM32/Bootloader/Core/Inc/bootloader_jump.h` and `STM32/Bootloader/Core/Src/bootloader_jump.c`: vector validation and app jump.
- Create `STM32/Bootloader/Core/Src/main.c`: minimal HAL/UART5 bootloader loop.
- Create `STM32/Bootloader/Core/Src/system_stm32f4xx.c`: bootloader system source copied from app-compatible CMSIS source.
- Modify `STM32/Makefile`: add `app`, `bootloader`, address-specific outputs, and bootloader source list.
- Update `STM32/README.md`: protocol and host update sequence.

## Task 1: Add Failing Bootloader Structure Tests

**Files:**
- Create: `STM32/tests/test_uart5_bootloader.py`

- [ ] **Step 1: Write the failing test**

Create tests that assert all planned STM32-only files and key strings exist:

```python
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Uart5BootloaderTests(unittest.TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_flash_layout_constants_define_bootloader_and_app_regions(self):
        header = self.read("Core/Inc/app_flash_layout.h")

        self.assertIn("#define APP_FLASH_BOOT_BASE 0x08000000U", header)
        self.assertIn("#define APP_FLASH_BOOT_SIZE (32U * 1024U)", header)
        self.assertIn("#define APP_FLASH_BASE 0x08008000U", header)
        self.assertIn("#define APP_FLASH_SIZE (480U * 1024U)", header)
        self.assertIn("#define APP_FLASH_END 0x08080000U", header)
        self.assertIn("#define APP_SRAM_BASE 0x20000000U", header)
        self.assertIn("#define APP_SRAM_END 0x20020000U", header)

    def test_linker_scripts_partition_flash(self):
        boot_ld = self.read("STM32F407XX_BOOT_FLASH.ld")
        app_ld = self.read("STM32F407XX_APP_FLASH.ld")

        self.assertIn("FLASH (rx)      : ORIGIN = 0x8000000, LENGTH = 32K", boot_ld)
        self.assertIn("FLASH (rx)      : ORIGIN = 0x8008000, LENGTH = 480K", app_ld)
        self.assertIn("RAM (xrw)      : ORIGIN = 0x20000000, LENGTH = 128K", boot_ld)
        self.assertIn("RAM (xrw)      : ORIGIN = 0x20000000, LENGTH = 128K", app_ld)

    def test_application_sets_vector_table_to_relocated_base(self):
        system = self.read("Core/Src/system_stm32f4xx.c")

        self.assertIn('#include "app_flash_layout.h"', system)
        self.assertIn("SCB->VTOR = APP_FLASH_BASE;", system)

    def test_makefile_builds_distinct_app_and_bootloader_images(self):
        makefile = self.read("Makefile")

        self.assertIn("APP_BUILD_DIR = build/app", makefile)
        self.assertIn("BOOT_BUILD_DIR = build/bootloader", makefile)
        self.assertIn("APP_LDSCRIPT = STM32F407XX_APP_FLASH.ld", makefile)
        self.assertIn("BOOT_LDSCRIPT = STM32F407XX_BOOT_FLASH.ld", makefile)
        self.assertRegex(makefile, r"^app:\s+\\$\\(APP_BUILD_DIR\\)/\\$\\(TARGET\\)_app\\.elf", re.MULTILINE)
        self.assertRegex(makefile, r"^bootloader:\s+\\$\\(BOOT_BUILD_DIR\\)/\\$\\(TARGET\\)_bootloader\\.elf", re.MULTILINE)
        self.assertIn("Bootloader/Core/Src/main.c", makefile)
        self.assertIn("Bootloader/Core/Src/bootloader_flash.c", makefile)
        self.assertIn("Bootloader/Core/Src/bootloader_protocol.c", makefile)
        self.assertIn("Bootloader/Core/Src/bootloader_jump.c", makefile)

    def test_bootloader_config_defines_protocol_and_limits(self):
        config = self.read("Bootloader/Core/Inc/bootloader_config.h")

        self.assertIn("#define BOOTLOADER_UART_BAUDRATE 115200U", config)
        self.assertIn("#define BOOTLOADER_HANDSHAKE_TIMEOUT_MS 2000U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_HELLO 0x10U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_INFO 0x90U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_START 0x11U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_ERASE 0x12U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_WRITE 0x13U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_VERIFY 0x14U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_JUMP 0x15U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_RESET 0x16U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_ACK 0x91U", config)
        self.assertIn("#define BOOTLOADER_FRAME_ID_ERROR 0xE2U", config)
        self.assertIn("#define BOOTLOADER_MAX_PAYLOAD_SIZE 32U", config)
        self.assertIn("#define BOOTLOADER_WRITE_DATA_MAX 27U", config)

    def test_bootloader_protocol_uses_binary_frames_and_crc8(self):
        header = self.read("Bootloader/Core/Inc/bootloader_protocol.h")
        source = self.read("Bootloader/Core/Src/bootloader_protocol.c")

        self.assertIn("Bootloader_ProtocolEncode", header)
        self.assertIn("Bootloader_ProtocolParseByte", header)
        self.assertIn("BOOTLOADER_FRAME_HEADER0", source)
        self.assertIn("BOOTLOADER_FRAME_HEADER1", source)
        self.assertIn("BOOTLOADER_CRC8_POLY", source)
        self.assertIn("crc ^= byte;", source)

    def test_bootloader_flash_protects_boot_region_and_verifies_crc32(self):
        header = self.read("Bootloader/Core/Inc/bootloader_flash.h")
        source = self.read("Bootloader/Core/Src/bootloader_flash.c")

        self.assertIn("Bootloader_FlashIsAppRange", header)
        self.assertIn("Bootloader_FlashStartSession", header)
        self.assertIn("Bootloader_FlashWrite", header)
        self.assertIn("Bootloader_FlashVerify", header)
        self.assertIn("address < APP_FLASH_BASE", source)
        self.assertIn("end_address > APP_FLASH_END", source)
        self.assertIn("APP_FLASH_BASE + offset", source)
        self.assertIn("Bootloader_FlashCrc32", source)

    def test_bootloader_jump_validates_vectors_before_jump(self):
        header = self.read("Bootloader/Core/Inc/bootloader_jump.h")
        source = self.read("Bootloader/Core/Src/bootloader_jump.c")

        self.assertIn("Bootloader_IsApplicationValid", header)
        self.assertIn("Bootloader_JumpToApplication", header)
        self.assertIn("stack_pointer >= APP_SRAM_BASE", source)
        self.assertIn("stack_pointer < APP_SRAM_END", source)
        self.assertIn("reset_handler >= APP_FLASH_BASE", source)
        self.assertIn("reset_handler < APP_FLASH_END", source)
        self.assertIn("__set_MSP(stack_pointer);", source)
        self.assertIn("app_reset_handler();", source)

    def test_bootloader_main_initializes_uart5_and_dispatches_commands(self):
        source = self.read("Bootloader/Core/Src/main.c")

        self.assertIn("UART_HandleTypeDef huart5;", source)
        self.assertIn("MX_UART5_Init", source)
        self.assertIn("GPIO_AF8_UART5", source)
        self.assertIn("BOOTLOADER_HANDSHAKE_TIMEOUT_MS", source)
        self.assertIn("Bootloader_HandleFrame", source)
        self.assertIn("Bootloader_JumpToApplication", source)

    def test_bootloader_readme_documents_host_protocol(self):
        readme = self.read("README.md")

        self.assertIn("# UART5 Bootloader Protocol", readme)
        self.assertIn("0x08000000", readme)
        self.assertIn("0x08008000", readme)
        self.assertIn("HELLO", readme)
        self.assertIn("START", readme)
        self.assertIn("ERASE", readme)
        self.assertIn("WRITE", readme)
        self.assertIn("VERIFY", readme)
        self.assertIn("JUMP", readme)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest STM32/tests/test_uart5_bootloader.py -v`

Expected: FAIL because files such as `Core/Inc/app_flash_layout.h` and bootloader files do not exist.

## Task 2: Add Flash Layout, Linker Scripts, and App Relocation

**Files:**
- Create: `STM32/Core/Inc/app_flash_layout.h`
- Create: `STM32/STM32F407XX_APP_FLASH.ld`
- Create: `STM32/STM32F407XX_BOOT_FLASH.ld`
- Modify: `STM32/Core/Src/system_stm32f4xx.c`

- [ ] **Step 1: Implement layout header**

Add shared constants:

```c
#ifndef APP_FLASH_LAYOUT_H
#define APP_FLASH_LAYOUT_H

#include <stdint.h>

#define APP_FLASH_BOOT_BASE 0x08000000U
#define APP_FLASH_BOOT_SIZE (32U * 1024U)
#define APP_FLASH_BASE 0x08008000U
#define APP_FLASH_SIZE (480U * 1024U)
#define APP_FLASH_END 0x08080000U

#define APP_SRAM_BASE 0x20000000U
#define APP_SRAM_END 0x20020000U

#endif /* APP_FLASH_LAYOUT_H */
```

- [ ] **Step 2: Add linker scripts**

Copy the existing linker script twice. In `STM32F407XX_APP_FLASH.ld`, set `FLASH` to `ORIGIN = 0x8008000, LENGTH = 480K`. In `STM32F407XX_BOOT_FLASH.ld`, set `FLASH` to `ORIGIN = 0x8000000, LENGTH = 32K`.

- [ ] **Step 3: Relocate app vector table**

Modify `system_stm32f4xx.c` to include `app_flash_layout.h` and assign:

```c
SCB->VTOR = APP_FLASH_BASE;
```

inside `SystemInit()` before it returns.

- [ ] **Step 4: Run test to verify this slice passes**

Run: `python3 -m unittest STM32/tests/test_uart5_bootloader.py -v`

Expected: remaining failures only for Makefile, bootloader modules, and docs.

## Task 3: Add Bootloader Config and Protocol

**Files:**
- Create: `STM32/Bootloader/Core/Inc/bootloader_config.h`
- Create: `STM32/Bootloader/Core/Inc/bootloader_protocol.h`
- Create: `STM32/Bootloader/Core/Src/bootloader_protocol.c`

- [ ] **Step 1: Add config constants**

Define UART settings, frame IDs, payload limits, ACK/error codes, and include `app_flash_layout.h`.

- [ ] **Step 2: Add protocol types**

Create `Bootloader_Frame`, parser state/result enums, and declarations for init, encode, parse, and little-endian helpers.

- [ ] **Step 3: Implement CRC8 frame parser and encoder**

Use the same `AA 55 + frame_id + length + payload + CRC8` behavior as the app protocol, with `BOOTLOADER_MAX_PAYLOAD_SIZE = 32U`.

- [ ] **Step 4: Run test**

Run: `python3 -m unittest STM32/tests/test_uart5_bootloader.py -v`

Expected: protocol tests pass; failures remain for Flash, jump, main, Makefile, docs.

## Task 4: Add Flash Session and Jump Logic

**Files:**
- Create: `STM32/Bootloader/Core/Inc/bootloader_flash.h`
- Create: `STM32/Bootloader/Core/Src/bootloader_flash.c`
- Create: `STM32/Bootloader/Core/Inc/bootloader_jump.h`
- Create: `STM32/Bootloader/Core/Src/bootloader_jump.c`

- [ ] **Step 1: Implement Flash API**

Add `Bootloader_FlashStartSession`, `Bootloader_FlashEraseApplication`, `Bootloader_FlashWrite`, `Bootloader_FlashVerify`, and `Bootloader_FlashIsAppRange`. Reject addresses below `APP_FLASH_BASE` and above `APP_FLASH_END`.

- [ ] **Step 2: Implement jump API**

Add vector validation and app jump using `HAL_DeInit()`, `SysTick->CTRL = 0`, `__disable_irq()`, `SCB->VTOR = APP_FLASH_BASE`, `__set_MSP(stack_pointer)`, and reset-handler call.

- [ ] **Step 3: Run test**

Run: `python3 -m unittest STM32/tests/test_uart5_bootloader.py -v`

Expected: Flash and jump tests pass; failures remain for main, Makefile, docs.

## Task 5: Add Bootloader Main and Build Targets

**Files:**
- Create: `STM32/Bootloader/Core/Src/main.c`
- Create: `STM32/Bootloader/Core/Src/system_stm32f4xx.c`
- Modify: `STM32/Makefile`

- [ ] **Step 1: Add bootloader main**

Implement minimal HAL init, clock config, GPIO clocks for UART5 PC12/PD2, `MX_UART5_Init`, receive loop, 2000 ms handshake window, command dispatch, ACK/error replies, Flash write flow, verify, reset, and jump.

- [ ] **Step 2: Add bootloader system source**

Use a small CMSIS-compatible `SystemInit()` that enables FPU and leaves VTOR at boot Flash base.

- [ ] **Step 3: Extend Makefile**

Add `APP_BUILD_DIR`, `BOOT_BUILD_DIR`, `APP_LDSCRIPT`, `BOOT_LDSCRIPT`, `APP_SOURCES`, `BOOT_SOURCES`, `app`, and `bootloader` targets. Keep outputs distinct.

- [ ] **Step 4: Run test**

Run: `python3 -m unittest STM32/tests/test_uart5_bootloader.py -v`

Expected: all tests pass except docs if README is not added yet.

## Task 6: Add Bootloader README and Full Verification

**Files:**
- Update: `STM32/README.md`

- [ ] **Step 1: Add README**

Document Flash layout, serial settings, frame format, frame IDs, error codes, and update sequence.

- [ ] **Step 2: Run STM32 Python tests**

Run: `python3 -m unittest discover STM32/tests -v`

Expected: PASS.

- [ ] **Step 3: Build relocated app**

Run: `make -C STM32 app`

Expected: app ELF/HEX/BIN are generated under `STM32/build/app`.

- [ ] **Step 4: Build bootloader**

Run: `make -C STM32 bootloader`

Expected: bootloader ELF/HEX/BIN are generated under `STM32/build/bootloader`.

- [ ] **Step 5: Inspect git scope**

Run: `git status --short`

Expected: changed files are all under `STM32/`.
