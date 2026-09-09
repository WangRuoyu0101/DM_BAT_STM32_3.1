#!/usr/bin/env python3
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]


class FirmwareSyncTest(unittest.TestCase):
    def test_package_has_firmware_drop_directory(self):
        firmware_dir = PACKAGE_ROOT / "firmware"

        self.assertTrue(firmware_dir.is_dir())
        self.assertTrue((firmware_dir / "README.md").is_file())
        self.assertTrue((firmware_dir / ".gitignore").is_file())

    def test_dm31_application_image_replaces_dm21_name(self):
        firmware_dir = PACKAGE_ROOT / "firmware"
        makefile = (REPO_ROOT / "STM32/Makefile").read_text()

        self.assertIn("TARGET = DM3.1_BAT", makefile)
        self.assertTrue((firmware_dir / "DM3.1_BAT_app.bin").is_file())
        self.assertFalse((firmware_dir / "DM2.1_BAT_app.bin").exists())

    def test_sync_script_pushes_package_firmware_directory(self):
        sync_script = (REPO_ROOT / "Linux_ROS_WS/scripts/sync_to_jetson.sh").read_text()

        self.assertIn('${LOCAL_WS}/src/', sync_script)
        self.assertIn('${REMOTE_HOST}:${REMOTE_WS}/src/', sync_script)
        self.assertNotIn("firmware/", sync_script)


if __name__ == "__main__":
    unittest.main()
