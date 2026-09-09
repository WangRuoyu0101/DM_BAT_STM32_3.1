import csv
import tempfile
import unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace

from dm31_host.core import (
    CsvRecorder,
    PortChoice,
    Telemetry,
    append_bounded,
    find_matching_port,
    list_serial_ports,
)


def port(device, serial_number=None, vid=None, pid=None):
    return SimpleNamespace(
        device=device,
        description=f"STM32 {device}",
        hwid="USB",
        serial_number=serial_number,
        vid=vid,
        pid=pid,
    )


class CoreTest(unittest.TestCase):
    def test_ports_are_sorted_and_match_identity(self):
        choices = list_serial_ports(lambda: [port("COM9"), port("COM2", "ABC", 1, 2)])
        self.assertEqual([item.device for item in choices], ["COM2", "COM9"])
        original = choices[0]
        self.assertEqual(
            find_matching_port(original, lambda: [port("COM4", "ABC", 9, 9)]).device,
            "COM4",
        )
        without_serial = PortChoice("COM2", vid=1, pid=2)
        self.assertEqual(
            find_matching_port(without_serial, lambda: [port("COM5", None, 1, 2)]).device,
            "COM5",
        )
        self.assertIsNone(
            find_matching_port(
                without_serial,
                lambda: [port("COM5", None, 1, 2), port("COM6", None, 1, 2)],
            )
        )

    def test_append_bounded_keeps_newest_values(self):
        values = deque()
        for value in range(605):
            append_bounded(values, value)
        self.assertEqual(len(values), 600)
        self.assertEqual((values[0], values[-1]), (5, 604))

    def test_csv_recorder_writes_stable_snapshot_and_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.csv"
            recorder = CsvRecorder()
            recorder.start(path)
            recorder.write(Telemetry(sample_seq=7, link_ok=True, fan_level=2, fan1_rpm=3000))
            self.assertTrue(recorder.active)
            recorder.stop()
            self.assertFalse(recorder.active)

            with path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["sample_seq"], "7")
            self.assertEqual(rows[0]["link_ok"], "True")
            self.assertEqual(rows[0]["fan_level"], "2")
            self.assertEqual(rows[0]["fan1_rpm"], "3000")
            self.assertRegex(rows[0]["timestamp"], r"[+-]\d\d:\d\d$")
            self.assertIn("board_io_timestamp", rows[0])


if __name__ == "__main__":
    unittest.main()
