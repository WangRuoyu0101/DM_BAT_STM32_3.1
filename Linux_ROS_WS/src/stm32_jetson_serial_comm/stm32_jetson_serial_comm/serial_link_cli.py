"""Console entry point for raw serial link testing."""

from __future__ import annotations

import argparse
from dataclasses import replace
import math
import os
import re
import sys

from stm32_jetson_serial_comm.cs1237 import (
    force_newtons,
    load_calibration,
    save_calibration,
    temperature_celsius,
)
from stm32_jetson_serial_comm.serial_driver import SerialDriver, read_for_seconds
from stm32_jetson_serial_comm.serial_host import SerialHost
from stm32_jetson_serial_comm.serial_node_core import SerialNodeCore


DEFAULT_DEVICE = os.environ.get("STM32_SERIAL_DEVICE", "/dev/ttyACM0")
DEFAULT_BAUDRATE = 115200
LOOPBACK_TEST_PATTERN = bytes.fromhex("AA 55 5A A5 00 FF 13 37")
CS1237_CHANNELS = {"cha": 0, "force": 0, "temp": 2, "temperature": 2, "ins": 3}
CS1237_CHANNEL_NAMES = {0: "CHA", 2: "TEM", 3: "INS"}


def parse_hex_bytes(text: str) -> bytes:
    """Parse strings like 'AA 55, 0x01 02' into bytes."""
    cleaned = text.strip()
    if not cleaned:
        return b""

    tokens = [part for part in re.split(r"[\s,]+", cleaned) if part]
    values = []
    for token in tokens:
        raw = token[2:] if token.lower().startswith("0x") else token
        if len(raw) != 2 or not re.fullmatch(r"[0-9a-fA-F]{2}", raw):
            raise ValueError(f"invalid hex byte: {token!r}")
        values.append(int(raw, 16))
    return bytes(values)


def format_bytes_hex(data: bytes) -> str:
    return " ".join(f"{value:02X}" for value in data)


def format_status_query(status) -> str:
    return SerialNodeCore._format_status_text(status)


def format_gpio_query(gpio) -> str:
    return SerialNodeCore._format_gpio_text(gpio)


def format_ultrasonic_query(ultrasonic) -> str:
    return SerialNodeCore._format_ultrasonic_text(ultrasonic)


def format_cs1237_query(status) -> str:
    base = (
        f"CS1237 channel={CS1237_CHANNEL_NAMES.get(status.channel, status.channel)} "
        f"raw={status.raw_adc} valid={'yes' if status.valid else 'no'} error={status.error}"
    )
    if not status.valid:
        return base
    calibration = load_calibration()
    if status.channel == 2:
        return f"{base} temperature={temperature_celsius(status.raw_adc, calibration):.2f} C"
    if status.channel == 0:
        try:
            return f"{base} force={force_newtons(status.raw_adc, calibration):.3f} N"
        except ValueError:
            return f"{base} force=UNCALIBRATED"
    return base


def parse_cs1237_channel(text: str) -> int:
    try:
        return CS1237_CHANNELS[text.lower()]
    except KeyError as exc:
        raise argparse.ArgumentTypeError("channel must be cha, temp, or ins") from exc


def parse_seq(text: str) -> int:
    value = int(text, 0)
    if not 0 <= value <= 0xFF:
        raise argparse.ArgumentTypeError("seq must be between 0x00 and 0xFF")
    return value


def run_loopback_test(
    port,
    pattern: bytes = LOOPBACK_TEST_PATTERN,
    timeout_seconds: float = 1.0,
    monotonic_step=None,
) -> tuple[bool, str]:
    port.write(pattern)
    rx_data = read_for_seconds(
        port,
        timeout_seconds,
        chunk_size=len(pattern),
        monotonic_step=monotonic_step,
    )

    if rx_data == pattern:
        return True, f"回环测试通过：{format_bytes_hex(pattern)}"

    if not rx_data:
        return False, "回环测试失败：未收到回环数据"

    return False, (
        "回环测试失败："
        f"TX {format_bytes_hex(pattern)}，"
        f"RX {format_bytes_hex(rx_data)}"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Jetson 串口链路测试工具：发送/接收原始十六进制字节。"
    )
    parser.add_argument("--device", default=DEFAULT_DEVICE, help=f"串口设备，默认 {DEFAULT_DEVICE}")
    parser.add_argument("--baudrate", type=int, default=DEFAULT_BAUDRATE, help="波特率，默认 115200")
    parser.add_argument("--timeout", type=float, default=0.1, help="串口 read timeout 秒数")
    parser.add_argument("--send-hex", help="要发送的十六进制字节，例如：AA 55 01 02")
    parser.add_argument("--read-seconds", type=float, default=1.0, help="发送后持续读取的秒数")
    parser.add_argument("--listen", action="store_true", help="不发送，只持续读取并打印")
    parser.add_argument("--query-status", action="store_true", help="发送 0x01 状态查询并解析 0x81 响应")
    parser.add_argument("--query-gpio", action="store_true", help="发送 0x03 GPIO 状态查询并解析 0x83 响应")
    parser.add_argument("--query-ultrasonic", action="store_true", help="发送 0x04 超声波查询并解析 0x84 响应")
    parser.add_argument("--cs1237-query", action="store_true", help="查询 CS1237 最新采样值")
    parser.add_argument("--cs1237-set-channel", choices=CS1237_CHANNELS, help="切换 CS1237 通道：cha/temp/ins")
    parser.add_argument("--cs1237-calibrate-zero", action="store_true", help="用当前 CHA 采样记录力传感器零点")
    parser.add_argument("--cs1237-calibrate-force", type=float, metavar="NEWTONS", help="用当前 CHA 采样记录已知力标定点")
    parser.add_argument("--cs1237-calibrate-temperature", type=float, metavar="CELSIUS", help="用当前 TEM 采样记录已知温度标定点")
    parser.add_argument("--loopback-test", action="store_true", help="短接 RXD/TXD 后发送固定字节并检查是否原样收到")
    parser.add_argument("--seq", type=parse_seq, default=0, help="业务查询序号，支持十进制或 0x 前缀")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    business_query_count = sum([
        args.query_status,
        args.query_gpio,
        args.query_ultrasonic,
        args.cs1237_query,
        args.cs1237_set_channel is not None,
        args.cs1237_calibrate_zero,
        args.cs1237_calibrate_force is not None,
        args.cs1237_calibrate_temperature is not None,
    ])
    if business_query_count > 1:
        raise SystemExit("一次只能指定一个业务查询参数")

    if args.loopback_test and (args.listen or args.send_hex is not None or business_query_count != 0):
        raise SystemExit("--loopback-test 不能与 --send-hex、--listen 或业务查询同时使用")

    if not args.listen and args.send_hex is None and business_query_count == 0 and not args.loopback_test:
        raise SystemExit("请指定 --send-hex 或 --listen")

    tx_data = parse_hex_bytes(args.send_hex) if args.send_hex is not None else b""

    with SerialDriver.open(args.device, args.baudrate, args.timeout) as port:
        print(f"OPEN {args.device} {args.baudrate} 8N1")

        if business_query_count:
            host = SerialHost(port)
            if args.query_status:
                print(format_status_query(host.query_status(seq=args.seq, timeout_seconds=args.read_seconds)))
            elif args.query_gpio:
                print(format_gpio_query(host.query_gpio(seq=args.seq, timeout_seconds=args.read_seconds)))
            elif args.query_ultrasonic:
                print(format_ultrasonic_query(host.query_ultrasonic(seq=args.seq, timeout_seconds=args.read_seconds)))
            elif args.cs1237_query:
                print(format_cs1237_query(host.query_cs1237(seq=args.seq, timeout_seconds=args.read_seconds)))
            elif args.cs1237_set_channel is not None:
                channel = CS1237_CHANNELS[args.cs1237_set_channel]
                result = host.set_cs1237_channel(
                    channel,
                    seq=args.seq,
                    timeout_seconds=args.read_seconds,
                )
                name = CS1237_CHANNEL_NAMES[channel]
                print(f"CS1237 channel={name} result={result.result}")
            elif args.cs1237_calibrate_temperature is not None:
                known_temperature = args.cs1237_calibrate_temperature
                if not math.isfinite(known_temperature) or not -40.0 <= known_temperature <= 85.0:
                    raise SystemExit("标定温度必须在 -40 至 85 C")
                status = host.query_cs1237(seq=args.seq, timeout_seconds=args.read_seconds)
                if status.channel != 2 or not status.valid or status.raw_adc == 0:
                    raise SystemExit("温度标定要求 TEM 通道存在非零有效采样")
                calibration = replace(
                    load_calibration(),
                    temperature_reference_c=known_temperature,
                    temperature_reference_adc=status.raw_adc,
                )
                save_calibration(calibration)
                print(
                    f"CS1237 temperature calibration saved: "
                    f"raw={status.raw_adc} temperature={known_temperature} C"
                )
            elif args.cs1237_calibrate_zero or args.cs1237_calibrate_force is not None:
                status = host.query_cs1237(seq=args.seq, timeout_seconds=args.read_seconds)
                if status.channel != 0 or not status.valid:
                    raise SystemExit("力标定要求 CHA 通道存在有效采样")
                calibration = load_calibration()
                if args.cs1237_calibrate_zero:
                    calibration = replace(calibration, force_zero_adc=status.raw_adc)
                    print(f"CS1237 force zero saved: raw={status.raw_adc}")
                else:
                    if calibration.force_zero_adc is None:
                        raise SystemExit("请先执行 --cs1237-calibrate-zero")
                    if args.cs1237_calibrate_force == 0:
                        raise SystemExit("已知力不能为 0 N")
                    calibration = replace(
                        calibration,
                        force_span_adc=status.raw_adc,
                        force_span_newtons=args.cs1237_calibrate_force,
                    )
                    print(
                        f"CS1237 force span saved: raw={status.raw_adc} "
                        f"force={args.cs1237_calibrate_force} N"
                    )
                save_calibration(calibration)
            return 0

        if args.loopback_test:
            ok, message = run_loopback_test(port, timeout_seconds=args.read_seconds)
            print(message)
            return 0 if ok else 1

        if tx_data:
            port.write(tx_data)
            print(f"TX {len(tx_data)} bytes: {format_bytes_hex(tx_data)}")

        while True:
            rx_data = read_for_seconds(port, args.read_seconds)
            if rx_data:
                print(f"RX {len(rx_data)} bytes: {format_bytes_hex(rx_data)}")
            elif not args.listen:
                print("RX timeout: no data")

            if not args.listen:
                break

    return 0


if __name__ == "__main__":
    sys.exit(main())
