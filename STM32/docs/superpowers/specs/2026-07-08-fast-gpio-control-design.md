# Fast GPIO Control Design

## Goal

Reduce the delay between a complete UART5 GPIO control request being received and the controlled GPIO pin changing state.

The optimization target is the GPIO output edge timing on STM32. UART5 response frame latency is secondary and should not drive risky interrupt-context behavior.

## Current Behavior

The application main loop runs user tasks in this order:

1. `App_UltrasonicManager_Run(current_tick)`
2. `App_Uart5Slave_Run(current_tick)`
3. `App_StatusLed_Run(current_tick)`

UART5 receive interrupts parse incoming bytes and set a frame-ready flag when a complete frame is available. The GPIO command itself is applied later in `App_Uart5Slave_Run()`.

Because ultrasonic scheduling runs before UART5 service, a complete GPIO control frame can wait behind ultrasonic work. In particular, ultrasonic trigger sends currently use blocking `HAL_UART_Transmit()` calls.

## Proposed Behavior

Add a fast GPIO service entry point:

```c
void App_Uart5Slave_RunFastGpio(uint32_t current_tick);
```

The main loop will call it before ultrasonic scheduling:

```c
current_tick = App_PeriodicTick_Get();
App_Uart5Slave_RunFastGpio(current_tick);
App_UltrasonicManager_Run(current_tick);
App_Uart5Slave_Run(current_tick);
```

`App_Uart5Slave_RunFastGpio()` will:

1. Return immediately if UART5 is not initialized or a bootloader reset is pending.
2. Atomically inspect and consume a ready UART5 frame only when it is a GPIO control request.
3. Decode the GPIO control request and call `App_RelayControl_Apply()` immediately.
4. Send the normal GPIO control response after applying the pin.

If the ready frame is not a GPIO control request, the fast service leaves it untouched for `App_Uart5Slave_Run()`.

## Concurrency

The UART5 receive interrupt and main loop share `s_rx_frame`, `s_frame_ready`, and error flags. The fast service will use the same short IRQ-disabled critical section pattern already used by `App_Uart5Slave_Run()`.

The fast service must not clear unrelated frame or error state. It only consumes `s_frame_ready` when the cached frame is `APP_COMM_FRAME_ID_GPIO_CONTROL_REQUEST`.

## Error Handling

For malformed GPIO control payloads, the fast service will preserve existing response semantics: decode failure or invalid channel/level still produces a GPIO control response with the corresponding result code.

Protocol checksum and length parser errors remain handled by the normal UART5 service path.

## Non-Goals

- Do not execute GPIO control in UART interrupt context.
- Do not convert ultrasonic UART transmit to interrupt or DMA mode in this change.
- Do not change UART5 protocol frame formats.
- Do not change bootloader request behavior.

## Test Strategy

Update the existing Python source-structure tests to verify:

1. The header declares `App_Uart5Slave_RunFastGpio()`.
2. The main loop calls `App_Uart5Slave_RunFastGpio(current_tick)` before `App_UltrasonicManager_Run(current_tick)`.
3. The fast GPIO service only consumes GPIO control frames and still calls `App_RelayControl_Apply()`.
4. The normal UART5 service keeps the existing non-GPIO command handling.
