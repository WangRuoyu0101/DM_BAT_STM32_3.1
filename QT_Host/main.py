#!/usr/bin/env python3
"""DM3.1 Qt debug host entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


QT_ROOT = Path(__file__).resolve().parent
REPO_PACKAGE = QT_ROOT.parent / "Linux_ROS_WS/src/stm32_jetson_serial_comm"
for source in (QT_ROOT, REPO_PACKAGE):
    if source.is_dir() and str(source) not in sys.path:
        sys.path.insert(0, str(source))

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from dm31_host.window import MainWindow
from dm31_host.worker import SerialWorker


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="DM3.1 STM32 Qt 调试上位机")
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication([])
    worker = SerialWorker()
    window = MainWindow(worker)

    if args.smoke_test:
        window.close()
        return 0

    thread = QThread()
    worker.moveToThread(thread)
    thread.finished.connect(worker.deleteLater)
    app.aboutToQuit.connect(thread.quit)
    thread.start()
    window.show()
    result = app.exec()
    thread.wait(3000)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
