import csv
import os
import tempfile
import unittest

import numpy as np

from tools.evaluate_chromatic_aberration import (
    _resize_max_dim, _sign_test_p, load_pairs, summarize,
)

_FIELDS = ["camera", "lens", "photographer", "jpeg_url", "raw_url", "page_url",
           "exif_datetime_original", "exif_camera_model", "exif_lens",
           "exif_iso", "exif_focal_length", "exif_pair_verified"]


class TestLoadPairs(unittest.TestCase):
    def _write_manifest_and_cache(self, jpeg_names):
        csv_fd, csv_path = tempfile.mkstemp(suffix=".csv")
        cache_dir = tempfile.mkdtemp()
        with os.fdopen(csv_fd, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDS)
            writer.writeheader()
            for name in jpeg_names:
                row = {field: "" for field in _FIELDS}
                row["jpeg_url"] = f"https://cdn.example.com/{name}"
                writer.writerow(row)
        for name in jpeg_names:
            open(os.path.join(cache_dir, f"{name}.3FR"), "w").close()
            open(os.path.join(cache_dir, f"{name}.target.jpg"), "w").close()
        self.addCleanup(os.remove, csv_path)
        return csv_path, cache_dir

    def test_parses_names_and_paths(self):
        csv_path, cache_dir = self._write_manifest_and_cache(["x1d-xcd45-01.jpg"])
        pairs = load_pairs(csv_path=csv_path, cache_dir=cache_dir)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["name"], "x1d-xcd45-01.jpg")
        self.assertTrue(pairs[0]["raw_path"].endswith("x1d-xcd45-01.jpg.3FR"))
        self.assertTrue(pairs[0]["target_path"].endswith("x1d-xcd45-01.jpg.target.jpg"))

    def test_multiple_rows_preserve_order(self):
        csv_path, cache_dir = self._write_manifest_and_cache(["a.jpg", "b.jpg"])
        pairs = load_pairs(csv_path=csv_path, cache_dir=cache_dir)
        self.assertEqual([p["name"] for p in pairs], ["a.jpg", "b.jpg"])


class TestResizeMaxDim(unittest.TestCase):
    def test_noop_when_already_smaller_than_max_dim(self):
        img = np.random.default_rng(0).uniform(0, 1, size=(10, 20, 3))
        out = _resize_max_dim(img, max_dim=1024)
        self.assertEqual(out.shape, img.shape)

    def test_downsamples_when_larger_than_max_dim(self):
        img = np.random.default_rng(1).uniform(0, 1, size=(2000, 4000, 3))
        out = _resize_max_dim(img, max_dim=512)
        self.assertLessEqual(max(out.shape[:2]), 512)
        self.assertAlmostEqual(out.shape[1] / out.shape[0], 4000 / 2000, places=1)


class TestSignTestP(unittest.TestCase):
    def test_even_split_is_p_one(self):
        self.assertAlmostEqual(_sign_test_p(6, 6), 1.0)

    def test_no_pairs_is_p_one(self):
        self.assertAlmostEqual(_sign_test_p(0, 0), 1.0)

    def test_all_wins_is_significant(self):
        self.assertLess(_sign_test_p(13, 0), 0.001)

    def test_known_exact_value(self):
        # C(13,3) 이하 누적 / 2^13 = 0.046142578125(한쪽 꼬리) x 2(양측) -
        # tools/evaluate_darktable_vs_rawpy.py의 동일 구현/동일 관례로
        # 교차검증한 값(_sign_test_p(10, 3) == 0.09228515625)
        self.assertAlmostEqual(_sign_test_p(10, 3), 0.09228515625, places=9)


class TestSummarizeShape(unittest.TestCase):
    """summarize()가 반환하는 dict의 키/타입만 검증 - 실제 13쌍 실행
    결과에 대한 회귀 테스트는 실행 후 Step 7에서 별도로 추가한다."""

    def test_returns_expected_keys(self):
        per_fold = [
            ("p1", 10.0, 8.0, 1.0, 0.99),
            ("p2", 12.0, 12.5, 1.0, 1.0),
            ("p3", 9.0, 7.5, 0.99, 1.0),
        ]
        s = summarize(per_fold)
        for key in ("n", "mean_baseline", "mean_corrected", "mean_diff",
                    "median_diff", "improvement_pct", "corrected_wins",
                    "baseline_wins", "sd_diff", "sem_diff", "t_stat",
                    "sign_test_p", "ci_diff", "ci_pct", "dropone_pct_min",
                    "dropone_pct_max", "dropone_flips_sign", "inconclusive",
                    "verdict"):
            self.assertIn(key, s)
        self.assertEqual(s["n"], 3)
        self.assertEqual(s["corrected_wins"], 2)
        self.assertEqual(s["baseline_wins"], 1)


if __name__ == "__main__":
    unittest.main()
