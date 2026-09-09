# Communication Reliability Design

## Goal

Improve the existing STM32–Jetson request/response link without changing its
wire framing or introducing unsolicited STM32 reports:

1. retain USB CDC responses while the USB endpoint is busy;
2. raise the application payload limit from 32 to 250 bytes;
3. expose communication fault and queue diagnostics through the existing
   status query.

## Request/response behavior

The STM32 application already sends protocol frames only while handling a
received UART5 or USB CDC request. TIM6 schedules internal sampling and
housekeeping only; it does not publish frames. This behavior remains unchanged:
there is no periodic or unsolicited STM32-to-Jetson application report.

## USB CDC transmit queue

`App_Uart5Slave_SendFrame()` continues to encode every response once. USB
responses are copied into a fixed two-entry FIFO, each entry sized for one
maximum application frame. The main loop submits the oldest queued frame
through `CDC_Transmit_FS()`:

- `USBD_OK`: mark that frame in flight and retain its buffer until the USB CDC
  transmit-complete callback removes it;
- `USBD_BUSY`: retain it and retry on the next main-loop pass;
- other result: discard it and increment the USB transmit error counter.

If both entries are occupied, the newest response is rejected and the queue
overflow counter is incremented. UART5 transmission remains synchronous and
unchanged. No dynamic allocation, retry delay, or blocking wait is added.

The queue exists in the application layer rather than generated USB files, so
CubeMX regeneration does not overwrite it.

## Protocol and RTK payload expansion

The frame remains:

`AA 55 | frame_id | uint8 length | payload | CRC8`

`APP_COMM_MAX_PAYLOAD_SIZE` becomes 250 on STM32, matching the existing Jetson
parser limit. Consequently:

- maximum encoded frame size is 255 bytes;
- RTK write data becomes at most 249 bytes (`seq + data`);
- RTK read data becomes at most 248 bytes (`seq + flags + data`);
- the Jetson RTK write chunk size becomes 249 bytes.

All existing short frames remain byte-for-byte compatible. The bootloader
protocol is outside this change and retains its current limits.

## Diagnostics

The existing status response (`0x81`) keeps its first seven bytes unchanged and
appends little-endian cumulative diagnostics:

| Offset | Size | Meaning |
|---|---:|---|
| 0 | 7 | Existing `seq`, tick, status, and GPIO bitmap |
| 7 | 4 | USB CDC `USBD_BUSY` retry count |
| 11 | 4 | USB transmit queue overflow count |
| 15 | 4 | USB transmit failure count |
| 19 | 4 | USART6 receive overflow byte count |
| 23 | 4 | USART6 HAL error callback count |
| 27 | 2 | USART6 receive FIFO high-water mark |

Counters saturate at their integer maximum rather than wrapping. The RTK
read-response overflow flag remains available and unchanged. Querying status
does not clear diagnostics.

The Jetson decoder accepts both the legacy 7-byte status payload and the new
29-byte payload. Legacy payloads report zero diagnostics, allowing a newly
built Jetson package to communicate with older firmware. CLI status output
prints the diagnostic values only when the extended payload is present.

## USB CDC baud rate

The CDC line coding remains 115200. For USB Full Speed CDC this value is host
metadata, not the physical USB transfer rate, so raising it does not increase
throughput. Real UART5 and USART6 baud rates are not changed by this work.

## Validation

- STM32 protocol tests cover 250-byte encode/parse and reject 251-byte payloads.
- STM32 source-level tests cover FIFO retention on busy, overflow accounting,
  FIFO ordering, and extended status layout.
- RTK tests cover 249-byte writes, 248-byte reads, cumulative overflow/error
  diagnostics, and high-water tracking.
- Jetson tests cover the expanded RTK chunks and both legacy and extended
  status decoding.
- The full STM32 and Jetson unit suites pass, followed by a clean firmware
  build.
