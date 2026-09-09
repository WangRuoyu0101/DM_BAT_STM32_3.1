# RTK Overflow Recovery Design

## Problem

UM982 continuously emits NMEA sentences. When Jetson does not query RTK data,
the STM32 USART6 ring eventually fills and sets its sticky overflow flag.
`RtkBridge.read()` correctly reports that data was lost, but `stm32_rtk`
currently lets `RtkOverflowError` terminate the process after one read. New
UM982 bytes then refill the buffer before the next CLI invocation, so repeated
manual retries cannot reliably recover.

## Behavior

- Before sending an RTK command, `stm32_rtk` drains stale STM32 RTK data until
  one read returns empty. Overflow during this drain is reported once to
  stderr and draining continues.
- During normal timed reads and `--listen`, overflow is reported once per CLI
  invocation to stderr and reading continues.
- Overflowed data is not presented as valid data. The existing STM32
  cumulative diagnostics remain unchanged.
- `Ctrl+C` continues to exit quietly with status 130.
- `RtkBridge.read()` retains its exception contract so other library callers
  can choose their own loss policy.

The pre-drain is used only before `--send-text` or `--send-hex`; listen-only
mode immediately enters its normal recovery loop. No STM32 firmware or wire
protocol change is required.

## Validation

CLI unit tests simulate repeated overflow followed by empty/data responses and
verify that the process continues, warns once, drains before writing, emits
subsequent bytes, and still handles `KeyboardInterrupt`.
