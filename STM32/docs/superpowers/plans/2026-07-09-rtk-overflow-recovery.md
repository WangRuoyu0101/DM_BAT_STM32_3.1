# RTK Overflow Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `stm32_rtk` operational when continuous UM982 output has overflowed the STM32 receive ring.

**Architecture:** Preserve `RtkBridge.read()` loss reporting. Add CLI-only warning/retry logic and drain stale bytes before sending a new command.

**Tech Stack:** Python 3 standard library, `unittest`, existing ROS2 console entry point.

## Global Constraints

- Do not change STM32 firmware or the wire protocol.
- Print at most one overflow warning per CLI invocation.
- Preserve quiet `Ctrl+C` exit status 130.
- Add no dependency.

---

### Task 1: Recover from RTK overflow in the CLI

**Files:**
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/rtk_cli.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_rtk_cli.py`

**Interfaces:**
- Consumes: `RtkOverflowError` from `RtkBridge.read()`.
- Produces: private stale-data drain and warning-once behavior.

- [ ] **Step 1: Write failing tests**

Mock `RtkBridge.read()` with:

```python
[RtkOverflowError("overflow"), b"", b"$command,...OK\r\n", b""]
```

Verify overflow does not escape, stderr receives one warning, the empty
response ends pre-drain before `write()`, and later data reaches stdout.
Add a listen test with two overflow exceptions followed by
`KeyboardInterrupt`, asserting one warning and exit status 130.

- [ ] **Step 2: Verify RED**

Run:

```bash
python3 -m unittest Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_rtk_cli.py -v
```

Expected: `RtkOverflowError` escapes from `main()`.

- [ ] **Step 3: Implement the minimum recovery**

Import `RtkOverflowError`. Add one local warning closure that prints once to
stderr. Before `bridge.write(data)`, repeatedly call `bridge.read()` until it
returns empty; catch overflow and continue. In the normal read loop, catch
overflow, warn, and continue without sleeping.

- [ ] **Step 4: Verify GREEN and regressions**

Run:

```bash
python3 -m unittest Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_rtk_cli.py -v
python3 -m unittest discover -s Linux_ROS_WS/src/stm32_jetson_serial_comm/tests -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Stage only the CLI, its tests, and this plan. Commit:

```bash
git commit -m "fix: recover RTK CLI from receive overflow"
```
