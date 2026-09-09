"""Console entry point for STM32 bootloader updates."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from stm32_jetson_serial_comm.bootloader import BootloaderClient
from stm32_jetson_serial_comm.serial_driver import SerialDriver
from stm32_jetson_serial_comm.serial_link_cli import parse_seq


BOOTLOADER_DEFAULT_BAUDRATE = 460800
APP_REQUEST_DEFAULT_BAUDRATE = 115200
DEFAULT_BOOTLOADER_DEVICE = os.environ.get("STM32_BOOTLOADER_DEVICE", "/dev/ttyACM0")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="STM32 bootloader 上位机升级工具。")
    parser.add_argument("image", type=Path, help="应用固件 bin 文件，例如 build/app/DM3.1_BAT_app.bin")
    parser.add_argument("--device", default=DEFAULT_BOOTLOADER_DEVICE, help=f"串口设备，默认 {DEFAULT_BOOTLOADER_DEVICE}")
    parser.add_argument("--baudrate", type=int, default=BOOTLOADER_DEFAULT_BAUDRATE, help="波特率，默认 460800")
    parser.add_argument(
        "--app-baudrate",
        type=int,
        default=APP_REQUEST_DEFAULT_BAUDRATE,
        help="发送 --request-from-app 请求时的应用串口波特率，默认 115200",
    )
    parser.add_argument("--timeout", type=float, default=3.0, help="bootloader 单帧响应超时秒数")
    parser.add_argument("--erase-timeout", type=float, default=10.0, help="Flash 擦除响应超时秒数，默认 10")
    parser.add_argument("--serial-timeout", type=float, default=0.05, help="底层串口 read timeout 秒数")
    parser.add_argument("--seq", type=parse_seq, default=0, help="起始 seq，支持十进制或 0x 前缀")
    parser.add_argument(
        "--request-from-app",
        action="store_true",
        help="先向正在运行的应用发送 0x05 + wb88 请求，触发软件复位进入 bootloader",
    )
    parser.add_argument("--app-request-timeout", type=float, default=0.5, help="应用 0x85 响应等待秒数")
    parser.add_argument("--reset-wait", type=float, default=1.5, help="应用收到请求后等待重启进入 bootloader 的秒数")
    parser.add_argument("--no-jump", action="store_true", help="VERIFY 成功后停留在 bootloader，不发送 JUMP")
    parser.add_argument("--reset-after-verify", action="store_true", help="VERIFY 成功后发送 RESET，而不是 JUMP")
    parser.add_argument("--quiet", action="store_true", help="减少升级过程输出")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if args.no_jump and args.reset_after_verify:
        raise SystemExit("--no-jump 和 --reset-after-verify 不能同时使用")

    try:
        image = args.image.read_bytes()
    except OSError as exc:
        raise SystemExit(f"无法读取固件文件：{args.image}\n原始错误：{exc}") from exc

    if not image:
        raise SystemExit(f"固件文件为空：{args.image}")

    if args.request_from_app:
        with SerialDriver.open(args.device, args.app_baudrate, args.serial_timeout) as port:
            client = BootloaderClient(port)
            print("APP BOOTLOADER REQUEST")
            client.request_app_bootloader(
                seq=args.seq,
                timeout_seconds=args.app_request_timeout,
            )
        if args.reset_wait > 0.0:
            import time

            time.sleep(args.reset_wait)

    with SerialDriver.open(args.device, args.baudrate, args.serial_timeout) as port:
        client = BootloaderClient(port)
        progress = None if args.quiet else print
        info = client.program_image(
            image,
            seq_start=args.seq,
            jump=not args.no_jump and not args.reset_after_verify,
            reset=args.reset_after_verify,
            timeout_seconds=args.timeout,
            erase_timeout_seconds=args.erase_timeout,
            progress=progress,
        )

    if not args.quiet:
        print(
            "DONE "
            f"app_base=0x{info.app_base:08X} "
            f"app_size={info.app_size} "
            f"write_data_max={info.write_data_max} "
            f"version=0x{info.version:08X}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
