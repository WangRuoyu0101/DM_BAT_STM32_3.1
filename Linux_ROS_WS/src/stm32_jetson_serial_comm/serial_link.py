#!/usr/bin/env python3
import sys

from stm32_jetson_serial_comm.serial_link_cli import format_bytes_hex, main, parse_hex_bytes


if __name__ == "__main__":
    sys.exit(main())
