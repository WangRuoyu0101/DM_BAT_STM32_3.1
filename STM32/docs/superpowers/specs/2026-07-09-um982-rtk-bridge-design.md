# UM982 RTK Framed Bridge Design

## Goal

Bridge arbitrary bidirectional data between Jetson and a UM982 RTK device on
STM32 USART6 while preserving the existing USB CDC application protocol.
The bridge must carry UM982 ASCII commands, NMEA 0183 output, and RTCM binary
correction data without interpreting or modifying the bytes.

## Hardware and serial settings

The existing USART6 mapping is used:

| Signal | STM32 | Direction |
| --- | --- | --- |
| UM982 RXD | PC6 / USART6 TX | STM32 to UM982 |
| UM982 TXD | PC7 / USART6 RX | UM982 to STM32 |
| GND | GND | Common ground |

USART6 remains `115200 8N1` with no flow control, matching the UM982 board
manual's default baud rate. UM982 TX and RX are TTL signals and must be
cross-connected. PPS is outside this feature.

## Architecture

The single USB CDC interface continues to carry the existing
`AA 55 + frame_id + length + payload + CRC8` protocol. RTK data is encapsulated
in new application frames, so it cannot be confused with GPIO, ultrasonic,
CS1237, or bootloader-request traffic.

`app_rtk_bridge.c` owns USART6 reception and buffering. Reception uses the
existing HAL single-byte interrupt pattern. The callback only appends the byte
to a fixed 1024-byte ring buffer and rearms reception; it does not parse NMEA
or RTCM.

Jetson polls buffered RTK data. STM32 never sends unsolicited USB frames, which
keeps USB response ownership host-driven and prevents response interleaving.

Jetson-to-UM982 chunks use the existing blocking HAL UART transmit call. A
chunk contains at most 31 UART bytes and takes about 2.7 ms at 115200 baud.
This is bounded and does not justify DMA.

## Application protocol

The existing maximum application payload remains 32 bytes.

### Write RTK data

- Request frame ID: `0x08`
- Request payload: `seq + data` where data contains 1 to 31 arbitrary bytes
- Response frame ID: `0x88`
- Response payload: `seq + result + accepted_length`

The data bytes are passed to USART6 unchanged. An empty data field is rejected
as a length error. Result values distinguish success and UART transmit failure.

### Read RTK data

- Request frame ID: `0x09`
- Request payload: `seq`
- Response frame ID: `0x89`
- Response payload: `seq + flags + data` where data contains 0 to 30 bytes

`flags bit0` reports that the USART6 receive ring overflowed since the previous
read response. The flag is sticky until reported, then cleared. When no bytes
are buffered, a valid response with no data is returned.

The 30-byte read size is chosen because `seq + flags` consumes two bytes of the
existing 32-byte payload. Read order is FIFO and wrap-around is transparent.

## Error handling

- A full receive ring drops the newly received byte and sets the sticky
  overflow flag; already buffered bytes remain intact.
- USART6 receive-complete and UART error callbacks both rearm the one-byte
  receive interrupt.
- Invalid RTK frame lengths use the existing application length error response.
- UART transmit failure is returned in the `0x88` result without pretending the
  data was accepted.
- Jetson raises a protocol error for an unexpected frame ID, malformed response,
  nonzero write result, or reported overflow.

## Jetson API and CLI

`RtkBridge` uses the existing `SerialHost` transport:

- `write(data)` splits arbitrary bytes into 31-byte chunks and checks each
  acknowledgement.
- `read()` requests one chunk and returns the bytes plus flags.
- Sequence numbers wrap at one byte.

A new `stm32_rtk` console entry point provides:

- `--send-text "GPGGA 1"`: UTF-8 encode and append `\r\n`.
- `--send-text "saveconfig"`: send the UM982 save command.
- `--send-hex "D3 ..."`: send arbitrary binary bytes such as RTCM.
- `--listen`: repeatedly read and write returned bytes unchanged to stdout.
- `--read-seconds N`: continue reading for a bounded interval after sending.

Text mode appends exactly one CRLF. Binary mode never alters data. The CLI does
not parse NMEA sentences; NMEA business parsing remains a separate future
layer.

## UM982 usage

The manual states that a new module may not output messages until configured.
Typical commands through the bridge are:

```text
GPGGA 1
unlog gpgga
saveconfig
```

`GPGGA 1` enables GGA on the current UM982 port. `GPGGA COM2 1` targets COM2.
`saveconfig` is required for output configuration to survive restart. NMEA is
ASCII text, while RTCM is binary and may appear unreadable in text tools.

## Verification

- Firmware tests check frame IDs, payload limits, USART6 initialization and
  IRQ wiring, ring FIFO/wrap/overflow behavior, callback rearming, USB CDC
  coexistence, and application-loop integration.
- Jetson tests check arbitrary binary transparency, 31-byte fragmentation,
  response validation, CRLF behavior, empty reads, overflow reporting, and
  console-script registration.
- Run all STM32 and Jetson unit tests.
- Build the STM32 application.
- Hardware acceptance:
  1. Send `GPGGA 1`, then `saveconfig`.
  2. Listen and observe intact `$GPGGA` or `$GNGGA` NMEA lines.
  3. Confirm existing status and CS1237 queries still work on the same USB CDC.
