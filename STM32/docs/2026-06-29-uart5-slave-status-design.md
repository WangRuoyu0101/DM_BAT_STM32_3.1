# UART5 Slave Frame Protocol Design

## Goal

Use UART5 as a debug slave node so a Jetson master can query and display the STM32 node status through a binary frame protocol.

## Protocol

Each packet uses this layout:

```text
Header + Frame ID + Length + Payload + CRC8
AA 55    1 byte     1 byte   N bytes   1 byte
```

The checksum is CRC8 with polynomial `0x07`, initial value `0x00`, over `frame_id + length + payload`. The `AA 55` header is not included in the checksum. Every host request payload starts with `seq`, and every response echoes that `seq`.

## Frame IDs

| ID | Direction | Payload | Meaning |
| --- | --- | --- | --- |
| `0x01` | Jetson to STM32 | `seq` | Query slave status |
| `0x02` | Jetson to STM32 | `seq + channel_id + level` | Control relay GPIO level |
| `0x03` | Jetson to STM32 | `seq` | Query relay GPIO bitmap |
| `0x81` | STM32 to Jetson | `seq + tick(uint32 little-endian) + status(uint8) + gpio_bitmap` | Status response |
| `0x82` | STM32 to Jetson | `seq + channel_id + result` | GPIO control response |
| `0x83` | STM32 to Jetson | `seq + gpio_bitmap` | GPIO bitmap response |
| `0xE1` | STM32 to Jetson | `seq + source_frame_id + error_code` | Error response |

The status query frame is:

```text
AA 55 01 01 10 0E
```

## Architecture

The binary protocol lives in a separate reusable application module:

- `Core/Inc/app_comm_protocol.h`
- `Core/Src/app_comm_protocol.c`

UART5 slave behavior lives in:

- `Core/Inc/app_uart5_slave.h`
- `Core/Src/app_uart5_slave.c`

`main.c` initializes the UART5 slave after `MX_UART5_Init()` and calls `App_Uart5Slave_Run(current_tick)` from the existing main loop. The UART receive complete callback only feeds bytes to the protocol parser and re-arms UART reception. The main loop formats and transmits response frames.

## Error Handling

If UART5 receive interrupt startup fails during initialization, `main.c` calls `Error_Handler()`. Unknown frame IDs return `0xE1` with error code `0x01`, checksum errors return error code `0x02`, and oversized payload lengths return error code `0x03`. Length or command errors include the original `seq` and source frame ID when the parser has enough bytes to identify them.

## Testing

Static tests verify that the protocol module defines the frame layout, CRC8 and parser states; that the UART5 slave uses binary frames instead of text commands; that the Makefile builds the protocol and relay-control sources; and that the Chinese protocol README documents the frame format, `seq`, GPIO control, GPIO status query, and error context.
