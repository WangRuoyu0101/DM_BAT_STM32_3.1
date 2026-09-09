"""Short CLI for controlling STM32 GPIO channels from Jetson."""

from __future__ import annotations

import argparse
import sys

from stm32_jetson_serial_comm.serial_driver import SerialDriver
from stm32_jetson_serial_comm.serial_host import SerialHost
from stm32_jetson_serial_comm.serial_link_cli import DEFAULT_BAUDRATE, DEFAULT_DEVICE, parse_seq


GPIO_CHANNELS = {
    "flash_ctr": 0x01,
    "led": 0x02,
    "bee": 0x03,
    "motor": 0x04,
    "flash": 0x05,
    "sound": 0x06,
}

GPIO_LEVELS = {
    "off": 0,
    "low": 0,
    "0": 0,
    "on": 1,
    "high": 1,
    "1": 1,
}

GPIO_RESULT_LABELS = {
    0x00: "OK",
    0x01: "INVALID_CHANNEL",
    0x02: "INVALID_LEVEL",
    0x03: "LENGTH_ERROR",
}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="STM32 GPIO 短命令控制工具，例如：stm32_gpio led on"
    )
    parser.add_argument("channel", choices=sorted(GPIO_CHANNELS), help="GPIO 通道名")
    parser.add_argument("level", choices=sorted(GPIO_LEVELS), help="输出状态：on/off/high/low/1/0")
    parser.add_argument("--device", default=DEFAULT_DEVICE, help=f"串口设备，默认 {DEFAULT_DEVICE}")
    parser.add_argument("--baudrate", type=int, default=DEFAULT_BAUDRATE, help="波特率，默认 115200")
    parser.add_argument("--timeout", type=float, default=0.5, help="响应等待时间，单位秒")
    parser.add_argument("--seq", type=parse_seq, default=0, help="请求序号，支持十进制或 0x 前缀")
    return parser


def format_result(result: int) -> str:
    label = GPIO_RESULT_LABELS.get(result, "UNKNOWN")
    return f"{label}(0x{result:02X})"


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    channel_id = GPIO_CHANNELS[args.channel]
    level = GPIO_LEVELS[args.level]

    with SerialDriver.open(args.device, args.baudrate, args.timeout) as port:
        host = SerialHost(port)
        response = host.control_gpio(
            channel_id=channel_id,
            level=level,
            seq=args.seq,
            timeout_seconds=args.timeout,
        )

    level_text = "ON" if level else "OFF"
    print(f"GPIO {args.channel} -> {level_text}: {format_result(response.result)}")
    return 0 if response.result == 0x00 else 1


if __name__ == "__main__":
    sys.exit(main())
