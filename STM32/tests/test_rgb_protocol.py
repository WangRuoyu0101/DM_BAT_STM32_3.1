from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RgbProtocolTest(unittest.TestCase):
    def test_rgb_protocol_behavior_harness(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "rgb_protocol_harness"
            subprocess.run(
                [
                    "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "tests/c"),
                    "-I", str(ROOT / "Core/Inc"),
                    str(ROOT / "tests/c/rgb_protocol_harness.c"),
                    str(ROOT / "Core/Src/app_comm_protocol.c"),
                    str(ROOT / "Core/Src/app_rgb_led.c"),
                    str(ROOT / "Core/Src/app_rgb_protocol.c"),
                    "-o", str(executable),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    unittest.main()
