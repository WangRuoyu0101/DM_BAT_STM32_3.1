"""Console bridge for UM982 commands, NMEA output, and RTCM bytes."""

from __future__ import annotations

import argparse
import os
import sys
import time

from stm32_jetson_serial_comm.rtk_bridge import RtkBridge, RtkOverflowError
from stm32_jetson_serial_comm.serial_driver import SerialDriver
from stm32_jetson_serial_comm.serial_host import SerialHost
from stm32_jetson_serial_comm.serial_link_cli import parse_hex_bytes


DEFAULT_DEVICE = os.environ.get("STM32_SERIAL_DEVICE", "/dev/ttyACM0")


def encode_text_command(command: str) -> bytes:
    return command.rstrip("\r\n").encode("ascii") + b"\r\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="UM982 RTK framed bridge")
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=0.2)
    send = parser.add_mutually_exclusive_group()
    send.add_argument("--send-text", help="send an ASCII UM982 command with CRLF")
    send.add_argument("--send-hex", help="send arbitrary hexadecimal bytes")
    parser.add_argument("--listen", action="store_true", help="continuously output received bytes")
    parser.add_argument("--read-seconds", type=float, default=0.0, help="read after sending")
    parser.add_argument("--poll-interval", type=float, default=0.01)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.send_text is None and args.send_hex is None and not args.listen:
        raise SystemExit("specify --send-text, --send-hex, or --listen")
    if args.read_seconds < 0 or args.poll_interval <= 0:
        raise SystemExit("read-seconds must be >= 0 and poll-interval must be > 0")

    data = None
    overflow_warned = False

    def warn_overflow() -> None:
        nonlocal overflow_warned
        if not overflow_warned:
            print("warning: STM32 RTK receive overflow; stale data was discarded", file=sys.stderr)
            overflow_warned = True

    if args.send_text is not None:
        data = encode_text_command(args.send_text)
    elif args.send_hex is not None:
        data = parse_hex_bytes(args.send_hex)
        if not data:
            raise SystemExit("--send-hex must not be empty")

    try:
        with SerialDriver.open(args.device, args.baudrate, args.timeout) as port:
            bridge = RtkBridge(SerialHost(port), timeout_seconds=args.timeout)
            if data is not None:
                while True:
                    try:
                        if not bridge.read():
                            break
                    except RtkOverflowError:
                        warn_overflow()
                bridge.write(data)

            deadline = time.monotonic() + args.read_seconds
            while args.listen or time.monotonic() < deadline:
                try:
                    received = bridge.read()
                except RtkOverflowError:
                    warn_overflow()
                    continue
                if received:
                    sys.stdout.buffer.write(received)
                    sys.stdout.buffer.flush()
                else:
                    time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
