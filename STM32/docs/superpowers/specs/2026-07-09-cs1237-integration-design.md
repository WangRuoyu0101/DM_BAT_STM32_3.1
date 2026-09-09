# CS1237 Integration Design

## Goal

Add CS1237 acquisition to the STM32 application using the fly-wired pins
PD11 (CLK) and PD14 (DIO), expose acquisition and runtime channel selection
through the existing USB CDC/UART5 protocol, and convert readings to
channel-appropriate units on Jetson.

## Hardware and acquisition

- PD11 is a push-pull output and remains low while idle.
- PD14 is normally an input. It is temporarily changed to push-pull output
  only while writing the CS1237 configuration register.
- The default configuration is the internal temperature channel, 10 Hz,
  PGA 1, with REF enabled.
- The temperature channel always uses PGA 1 as required by the datasheet.
  Differential and internal-short channels use PGA 128. All channels use
  10 Hz.
- The reserved reset channel value is rejected by both firmware and host.
- The main loop polls DIO without waiting. When DIO is low, it clocks out the
  24-bit conversion, sign-extends it to `int32_t`, and stores a snapshot.
- After initialization or a channel change, the first three 10 Hz conversion
  periods are treated as settling time. The previous sample is invalidated
  immediately and no new sample is marked valid until settling completes.
- Configuration writes are read back and verified. A timeout or verification
  mismatch is retained in the snapshot as an error and does not stop other
  application tasks.

DMA is intentionally not used. PD11 and PD14 are not a matching SPI pin pair,
and timer-driven GPIO DMA would add substantial complexity for roughly 24
clock pulses at 10 Hz.

## Firmware structure

`Core/Inc/app_cs1237.h` and `Core/Src/app_cs1237.c` own GPIO direction changes,
configuration register access, ADC reads, channel selection, settling state,
and the latest snapshot. The public interface provides initialization,
non-blocking main-loop service, channel selection, and snapshot retrieval.

`main.c` initializes the module after GPIO setup and calls its service
function from the existing cooperative main loop.

`app_uart5_slave.c` remains the shared application-protocol endpoint for UART5
and USB CDC. It handles CS1237 requests by calling only the public driver
interface.

## Application protocol

The existing `AA 55 + frame_id + length + payload + CRC8` framing remains
unchanged.

### Query

- Request frame ID: `0x06`
- Request payload: `seq`
- Response frame ID: `0x86`
- Response payload:
  - `seq`: `uint8`
  - `raw_adc`: signed 32-bit little-endian
  - `channel`: `uint8`
  - `valid`: `uint8`
  - `error`: `uint8`

### Select channel

- Request frame ID: `0x07`
- Request payload: `seq + channel`
- Response frame ID: `0x87`
- Response payload: `seq + channel + result`

Channel values are `CHA=0`, `TEM=2`, and `INS=3`. Value `1` and values above
`3` are rejected. Result values distinguish success, invalid channel,
configuration timeout, and readback verification failure.

Communication is request/response rather than unsolicited streaming. The
STM32 continuously maintains the latest snapshot; the Jetson ROS2 node polls
it periodically, nominally at 10 Hz. This keeps all serial ownership in the
existing host-driven model and avoids unsolicited ADC frames interleaving
with GPIO and ultrasonic responses.

## Jetson conversion and calibration

The Python host layer decodes both new responses and provides query and
channel-selection methods. CLI options expose both operations.

The ROS2 node periodically queries CS1237 and publishes the raw reading,
channel, validity/error state, and converted value when available.

- `TEM`: convert to degrees Celsius using the datasheet single-point formula
  `T = Yb * (273.15 + A) / Ya - 273.15`. Defaults are `A=23.0` degrees Celsius
  and `Ya=4100000`, matching the supplied reference code.
- `CHA`: convert to newtons using a Jetson-side two-point calibration. The
  operator first captures zero, then applies a known force in newtons and
  captures the loaded reading.
- `INS`: diagnostic raw value only; it has no physical-unit conversion.

Calibration is stored on Jetson at
`~/.config/stm32_jetson_serial_comm/cs1237_calibration.json`. The file stores
the temperature reference point and force zero/span parameters. Writes use a
temporary file followed by an atomic replace to avoid leaving truncated
calibration data after interruption.

If force calibration is incomplete or invalid, the host reports an
uncalibrated state with the raw ADC value and does not emit a fabricated
newton value.

## Error handling

- Firmware snapshot validity is false during settling and after acquisition
  or configuration errors.
- Protocol requests with invalid lengths use the existing application error
  response.
- Invalid channels receive a channel-selection response with a nonzero result.
- Jetson rejects malformed payloads and non-finite or zero-span calibration.
- Missing calibration files use temperature defaults and an uncalibrated force
  state.

## Verification

- Firmware-focused tests check pin mapping, configuration construction,
  24-bit sign extension, settling behavior, protocol IDs/payloads, main-loop
  integration, and shared USB CDC/UART5 routing.
- Python tests check message decoding, query/channel host operations,
  temperature conversion, two-point force conversion, invalid calibration,
  and calibration persistence using a temporary path.
- Run the full STM32 and Jetson Python test suites.
- Build the STM32 application with `make -C STM32 app`.
- Hardware acceptance: select `TEM`, observe stable valid raw values and a
  plausible Celsius result, then select `INS` and confirm the reported channel
  and diagnostic raw value change after settling.
