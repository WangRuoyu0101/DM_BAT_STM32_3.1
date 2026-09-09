# UART5 Slave Frame Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a UART5 slave debug status responder using a binary frame protocol.

**Architecture:** Add a focused `app_comm_protocol` module for reusable framing, CRC8 checksum, sequence-aware payload parsing, and byte-stream parsing. Keep `app_uart5_slave` responsible for UART5 receive/reply behavior, GPIO control responses, GPIO status responses, and status-frame payloads.

**Tech Stack:** STM32F407, STM32 HAL UART interrupt receive, existing Makefile and Python static tests.

---

### Task 1: Protocol Tests

**Files:**
- Create: `STM32/tests/test_comm_protocol_frame.py`
- Modify: `STM32/tests/test_uart5_slave_status.py`
- Modify: `STM32/tests/test_uart5_protocol_readme.py`

- [x] Test `AA 55 + frame_id + length + payload + CRC8` constants.
- [x] Test frame IDs `0x01`, `0x02`, `0x03`, `0x81`, `0x82`, `0x83`, and `0xE1`.
- [x] Test that UART5 no longer contains `STATUS?` text protocol strings.
- [x] Test that README documents binary frames.

### Task 2: Protocol Module

**Files:**
- Create: `STM32/Core/Inc/app_comm_protocol.h`
- Create: `STM32/Core/Src/app_comm_protocol.c`
- Modify: `STM32/Makefile`

- [x] Define frame constants and parser data structures.
- [x] Implement `App_CommProtocol_Encode`.
- [x] Implement `App_CommProtocol_ParseByte`.
- [x] Implement `CRC8(frame_id + length + payload)` with polynomial `0x07`.
- [x] Add `Core/Src/app_comm_protocol.c` to `C_SOURCES`.

### Task 3: UART5 Slave

**Files:**
- Modify: `STM32/Core/Inc/app_uart5_slave.h`
- Modify: `STM32/Core/Src/app_uart5_slave.c`

- [x] Feed received UART bytes to `App_CommProtocol_ParseByte`.
- [x] Respond to `0x01` status query with `0x81`.
- [x] Respond to `0x02` GPIO control request with `0x82`.
- [x] Respond to `0x03` GPIO status query with `0x83`.
- [x] Encode status payload as `seq + tick(uint32 little-endian) + status(uint8) + gpio_bitmap`.
- [x] Respond to command, checksum, and length errors with `0xE1` and include `seq + source_frame_id + error_code`.

### Task 4: Documentation

**Files:**
- Modify: `STM32/README.md`

- [x] Document UART5 serial settings.
- [x] Document frame format and CRC8 checksum.
- [x] Document frame IDs, seq, payloads, GPIO bitmap, and examples.
- [x] Document Jetson-side parsing guidance.

### Task 5: Verify

- [x] Run `python3 -m unittest STM32/tests/test_comm_protocol_frame.py STM32/tests/test_uart5_slave_status.py STM32/tests/test_uart5_protocol_readme.py STM32/tests/test_tim6_periodic_tick.py`.
- [x] Run `make -C STM32`.
- [x] Run `git diff --check -- STM32`.
