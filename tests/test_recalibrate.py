import json
import os
import tempfile
import unittest

import numpy as np

from hybrid_engine.recalibrate import decide_and_maybe_write


def _synthetic_dataset(matrix, n=8, seed=30, size=10):
    rng = np.random.default_rng(seed)
    dataset = []
    for _ in range(n):
        img = rng.uniform(0.05, 0.9, size=(size, size, 3))
        target = np.clip(img @ matrix, 0.0, 1.0)
        dataset.append((img, None, target))
    return dataset


class TestDecideAndMaybeWrite(unittest.TestCase):
    def test_dry_run_never_writes_even_if_gate_passes(self):
        matrix = np.array([[1.1, 0.01, -0.01], [0.01, 0.95, 0.01], [-0.01, 0.01, 1.08]])
        dataset = _synthetic_dataset(matrix)
        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "profile.json")
            result = decide_and_maybe_write(
                dataset, "synthetic", n_folds=4, n_passes=1,
                min_improvement_pct=-1000.0,  # 뭘 해도 게이트는 통과하게
                write=False, profile_path=out_path)
            self.assertTrue(result["gate_passed"])
            self.assertFalse(result["written"])
            self.assertFalse(os.path.exists(out_path))

    def test_writes_when_gate_passes_and_write_true(self):
        matrix = np.array([[1.1, 0.01, -0.01], [0.01, 0.95, 0.01], [-0.01, 0.01, 1.08]])
        dataset = _synthetic_dataset(matrix)
        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "profile.json")
            result = decide_and_maybe_write(
                dataset, "synthetic", n_folds=4, n_passes=1,
                min_improvement_pct=-1000.0,
                write=True, profile_path=out_path)
            self.assertTrue(result["gate_passed"])
            self.assertTrue(result["written"])
            self.assertTrue(os.path.exists(out_path))
            with open(out_path, encoding="utf-8") as f:
                saved = json.load(f)
            self.assertIn("raw_baseline_matrix", saved)
            self.assertIn("_comment", saved)
            self.assertIn("synthetic", saved["_comment"])

    def test_below_threshold_never_writes_even_with_write_true(self):
        matrix = np.array([[1.1, 0.01, -0.01], [0.01, 0.95, 0.01], [-0.01, 0.01, 1.08]])
        dataset = _synthetic_dataset(matrix)
        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "profile.json")
            result = decide_and_maybe_write(
                dataset, "synthetic", n_folds=4, n_passes=1,
                min_improvement_pct=1000.0,  # 절대 못 넘을 기준
                write=True, profile_path=out_path)
            self.assertFalse(result["gate_passed"])
            self.assertFalse(result["written"])
            self.assertFalse(os.path.exists(out_path))

    def test_too_few_pairs_for_cv_does_not_write(self):
        matrix = np.eye(3)
        dataset = _synthetic_dataset(matrix, n=2)
        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "profile.json")
            result = decide_and_maybe_write(
                dataset, "synthetic", n_folds=4, n_passes=1,
                write=True, profile_path=out_path)
            self.assertIsNone(result["cv_loss"])
            self.assertFalse(result["written"])
            self.assertFalse(os.path.exists(out_path))


if __name__ == "__main__":
    unittest.main()
