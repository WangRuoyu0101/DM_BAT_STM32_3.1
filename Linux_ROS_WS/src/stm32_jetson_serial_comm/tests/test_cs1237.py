#!/usr/bin/env python3
import pathlib
import sys
import tempfile
import unittest

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from stm32_jetson_serial_comm.cs1237 import (
    CS1237Calibration,
    force_newtons,
    load_calibration,
    save_calibration,
    temperature_celsius,
)


class CS1237ConversionTest(unittest.TestCase):
    def test_temperature_reference_adc_returns_reference_temperature(self):
        self.assertAlmostEqual(temperature_celsius(4100000), 23.0)

    def test_force_uses_two_point_calibration(self):
        calibration = CS1237Calibration(force_zero_adc=1000, force_span_adc=3000, force_span_newtons=10.0)
        self.assertAlmostEqual(force_newtons(2000, calibration), 5.0)

    def test_force_requires_nonzero_complete_span(self):
        with self.assertRaises(ValueError):
            force_newtons(1000, CS1237Calibration())

    def test_calibration_round_trip_and_missing_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "calibration.json"
            self.assertEqual(load_calibration(path), CS1237Calibration())
            expected = CS1237Calibration(
                temperature_reference_c=25.0,
                temperature_reference_adc=4200000,
                force_zero_adc=1000,
                force_span_adc=3000,
                force_span_newtons=10.0,
            )
            save_calibration(expected, path)
            self.assertEqual(load_calibration(path), expected)


if __name__ == "__main__":
    unittest.main()
