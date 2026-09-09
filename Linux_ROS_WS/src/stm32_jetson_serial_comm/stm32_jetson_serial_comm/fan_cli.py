"""Set or inspect the DM3.1 dual-fan interface."""

from __future__ import annotations

import argparse
import sys

from stm32_jetson_serial_comm.serial_driver import SerialDriver
from stm32_jetson_serial_comm.serial_host import SerialHost
from stm32_jetson_serial_comm.serial_link_cli import DEFAULT_BAUDRATE, DEFAULT_DEVICE, parse_seq


FAN_PERCENT = {1: 25, 2: 50, 3: 75, 4: 100}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DM3.1 风扇四档控制与状态查询")
    subparsers = parser.add_subparsers(dest="command", required=True)
    set_parser = subparsers.add_parser("set", help="设置 1/2/3/4 档")
    set_parser.add_argument("level", type=int, choices=FAN_PERCENT)
    subparsers.add_parser("status", help="查询档位、双路转速与按键")
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--baudrate", type=int, default=DEFAULT_BAUDRATE)
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument("--seq", type=parse_seq, default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    with SerialDriver.open(args.device, args.baudrate, args.timeout) as port:
        host = SerialHost(port)
        if args.command == "set":
            response = host.set_fan_level(args.level, seq=args.seq, timeout_seconds=args.timeout)
        else:
            status = host.query_board_io(seq=args.seq, timeout_seconds=args.timeout)

    if args.command == "set":
        result = "OK" if response.result == 0 else f"ERROR(0x{response.result:02X})"
        print(f"FAN level {response.level} ({FAN_PERCENT.get(response.level, 0)}%): {result}")
        return 0 if response.result == 0 else 1

    print(
        f"FAN level={status.fan_level} ({FAN_PERCENT.get(status.fan_level, 0)}%) "
        f"rpm1={status.fan1_rpm} rpm2={status.fan2_rpm} keys=0x{status.key_bitmap:02X}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
