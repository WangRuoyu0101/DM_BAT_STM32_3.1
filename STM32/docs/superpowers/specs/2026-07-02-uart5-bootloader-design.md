# UART5 Bootloader Design

## Goal

Add a dedicated UART5 bootloader for the STM32F407 power-board firmware. The bootloader runs before the application, accepts firmware updates from the Jetson host over UART5, protects its own Flash sectors, and jumps to the application when no update is requested.

## Current Context

- MCU: STM32F407VETx with 512 KB Flash and 128 KB SRAM plus 64 KB CCMRAM.
- UART5 is already wired and configured as 115200 8N1 on PC12 TX and PD2 RX.
- The current application is linked at `0x08000000` and uses the full 512 KB Flash region.
- The existing UART5 protocol uses `AA 55 + frame_id + length + payload + CRC8`.
- The current build uses one Makefile target for the application image.

## Flash Layout

The bootloader owns the first 32 KB of Flash:

| Region | Address range | STM32F407 sectors | Size | Purpose |
| --- | --- | --- | --- | --- |
| Bootloader | `0x08000000` - `0x08007FFF` | sector 0, sector 1 | 32 KB | UART5 bootloader |
| Application | `0x08008000` - `0x0807FFFF` | sector 2 and above | 480 KB | Main firmware |

The bootloader must never erase or write below `0x08008000`.

## Boot Flow

1. Reset enters the bootloader at `0x08000000`.
2. Bootloader initializes HAL, system clock, GPIO needed for status indication, and UART5.
3. Bootloader waits 2000 ms for a UART5 bootloader handshake.
4. If a valid upgrade handshake arrives, bootloader enters update mode.
5. If no handshake arrives, bootloader validates the application vector table at `0x08008000`.
6. If the application is valid, bootloader deinitializes peripherals, sets MSP from the application vector table, and jumps to the application reset handler.
7. If the application is invalid, bootloader remains in update mode until a valid image is written.

Application validity checks:

- Initial stack pointer must be inside SRAM: `0x20000000` - `0x2001FFFF`.
- Reset handler must point inside application Flash: `0x08008000` - `0x0807FFFF`.

## UART5 Bootloader Protocol

The bootloader protocol keeps the existing binary frame style:

```text
AA 55 + frame_id + length + payload + CRC8
```

CRC8 uses the existing polynomial `0x07`, initial value `0x00`, and covers `frame_id + length + payload`.

Bootloader frame IDs:

| Frame ID | Direction | Payload | Purpose |
| --- | --- | --- | --- |
| `0x10` | Jetson -> STM32 | `seq` | Enter bootloader / HELLO |
| `0x90` | STM32 -> Jetson | `seq + app_base + app_size + page_size + version` | Bootloader info |
| `0x11` | Jetson -> STM32 | `seq + image_size + image_crc32` | Start update session |
| `0x12` | Jetson -> STM32 | `seq` | Erase application region |
| `0x13` | Jetson -> STM32 | `seq + offset(uint32) + data` | Write application data chunk |
| `0x14` | Jetson -> STM32 | `seq` | Verify full written image |
| `0x15` | Jetson -> STM32 | `seq` | Jump to application |
| `0x16` | Jetson -> STM32 | `seq` | Reset MCU |
| `0x91` | STM32 -> Jetson | `seq + command + status` | Command ACK |
| `0xE2` | STM32 -> Jetson | `seq + command + error_code` | Bootloader error |

Write chunks use a maximum data payload that fits the existing parser limit. If the shared protocol limit remains 32 bytes, each `WRITE` carries 1 byte seq, 4 bytes offset, and up to 27 bytes data. If the bootloader gets a dedicated larger parser, the chunk payload may grow to 256 bytes, but the first implementation should prefer the smaller shared format to reduce risk.

## Update Session

The Jetson host sends:

1. `HELLO` to keep the bootloader from jumping to the app.
2. `START` with total image size and expected CRC32.
3. `ERASE` to erase application sectors.
4. Repeated `WRITE` frames with monotonic offsets.
5. `VERIFY` to compare received size and CRC32 against the `START` metadata.
6. `RESET` or `JUMP` after verification succeeds.

The bootloader rejects writes when:

- No update session is active.
- Offset plus data length exceeds the announced image size.
- Target address falls outside application Flash.
- Offset is not the expected next offset.
- Flash programming fails.

## Application Changes

The main application needs a relocated linker script:

- Flash origin changes from `0x08000000` to `0x08008000`.
- Flash length changes from 512 KB to 480 KB.

The application also sets the vector table offset early during startup:

```c
SCB->VTOR = 0x08008000U;
```

This must happen before interrupts are enabled for application peripherals.

## Build System

Keep the existing application source layout and add explicit targets:

- `make bootloader`: builds the bootloader image linked at `0x08000000`.
- `make app`: builds the relocated application image linked at `0x08008000`.
- `make all`: may continue to build the application for developer convenience, but the produced image name must make the address clear.

Generated images should use distinct names such as:

- `build/bootloader/DM2.1_BAT_bootloader.bin`
- `build/app/DM2.1_BAT_app.bin`

## Components

- `Bootloader/Core/Src/main.c`: minimal reset entry, UART5 wait loop, update state machine, jump logic.
- `Bootloader/Core/Inc/bootloader_config.h`: Flash base, sizes, timeout, version, protocol limits.
- `Bootloader/Core/Src/bootloader_protocol.c`: frame parsing and response helpers.
- `Bootloader/Core/Src/bootloader_flash.c`: erase, program, range checks, CRC32 verification.
- `STM32F407XX_APP_FLASH.ld`: relocated application linker script.
- `STM32F407XX_BOOT_FLASH.ld`: 32 KB bootloader linker script.
- `STM32/README.md`: host-facing protocol and flashing sequence.

## Error Handling

Bootloader error responses include the request `seq`, command ID, and an error code:

| Error | Meaning |
| --- | --- |
| `0x01` | Unknown command |
| `0x02` | CRC8 frame checksum error |
| `0x03` | Length error |
| `0x04` | Invalid address or range |
| `0x05` | Session state error |
| `0x06` | Flash erase/program failure |
| `0x07` | Image CRC32 verification failure |
| `0x08` | Application vector table invalid |

If the bootloader detects an invalid application at reset, it does not send unsolicited UART data; it waits for host commands.

## Testing

Add text-level tests first, matching the style already used under `STM32/tests`:

- Flash layout constants define bootloader base `0x08000000`, app base `0x08008000`, and app size 480 KB.
- Bootloader linker script limits Flash to 32 KB.
- Application linker script starts Flash at `0x08008000`.
- Application startup sets `SCB->VTOR` to the app base.
- Makefile exposes `bootloader` and `app` targets with distinct output paths.
- Bootloader protocol documents all frame IDs and error codes.
- Flash write code rejects addresses below the application base.
- Jump code validates stack pointer and reset handler ranges before jumping.

Then verify with:

- Existing STM32 Python tests.
- `make app`.
- `make bootloader`.

Board validation will be manual: flash bootloader once with SWD, transfer the relocated app over UART5, verify reset/jump behavior, then confirm normal application UART5 protocol still works after boot.

## Out of Scope

- Cryptographic image signatures.
- Dual-bank rollback.
- Compression.
- Encryption.
- Automatic host-side retry policy beyond ACK/error responses.
