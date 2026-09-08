import unittest
from unittest.mock import patch

import cv2
import numpy as np

from hybrid_engine.evaluation.nare_registration import inspect_registration, register_to_target


class TestNARERegistration(unittest.TestCase):
    def test_nonfinite_ecc_cannot_pass_inspection_or_registration(self):
        source = np.zeros((80, 80, 3), dtype=np.uint8)
        for correlation in (float('nan'), float('inf')):
            with self.subTest(correlation=correlation), patch(
                    'hybrid_engine.evaluation.nare_registration.cv2.findTransformECC',
                    return_value=(correlation, np.eye(2, 3, dtype=np.float32))):
                with self.assertRaisesRegex(ValueError, 'registration_failure'):
                    register_to_target(source, source)
                self.assertFalse(inspect_registration(source, source)['passed'])

    def test_recovers_small_translation_and_returns_valid_overlap(self):
        source = np.zeros((80, 80, 3), dtype=np.uint8)
        cv2.rectangle(source, (20, 20), (50, 55), (120, 180, 220), -1)
        target = cv2.warpAffine(source, np.float32([[1, 0, 3], [0, 1, -2]]),
                                (80, 80), borderValue=(0, 0, 0))
        aligned, mask, diagnostic = register_to_target(source, target)
        self.assertGreater(diagnostic["ecc_correlation"], 0.9)
        self.assertLess(np.mean(np.abs(aligned[mask].astype(float) - target[mask])), 2.0)
        self.assertLess(mask.mean(), 1.0)
        self.assertGreater(mask.mean(), 0.9)

    def test_rejects_low_overlap_or_excessive_shift(self):
        source = np.zeros((80, 80, 3), dtype=np.uint8)
        cv2.rectangle(source, (20, 20), (50, 55), (120, 180, 220), -1)
        target = cv2.warpAffine(source, np.float32([[1, 0, 20], [0, 1, 0]]),
                                (80, 80), borderValue=(0, 0, 0))
        with self.assertRaisesRegex(ValueError, "registration_failure"):
            register_to_target(source, target, max_shift_fraction=0.05)

    def test_inspection_reports_threshold_failure_without_discarding_diagnostics(self):
        source = np.zeros((80, 80, 3), dtype=np.uint8)
        cv2.rectangle(source, (20, 20), (50, 55), (120, 180, 220), -1)
        target = cv2.warpAffine(source, np.float32([[1, 0, 20], [0, 1, 0]]),
                                (80, 80), borderValue=(0, 0, 0))
        report = inspect_registration(source, target, max_shift_fraction=0.05)
        self.assertFalse(report["passed"])
        self.assertIn("translation", report["failure_reason"])
        self.assertIn("shift_x_px", report)


if __name__ == "__main__":
    unittest.main()
