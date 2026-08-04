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


# 실제 13쌍 LOO 교차검증 재실행 기록값 - hybrid_engine/EVALUATION.md의
# "색수차 보정(chromatic aberration) 실험" 절에 실린 것과 정확히 같다.
# (name, de_baseline, de_corrected, best_red, best_blue)
_RECORDED_13_PAIR_RUN = [
    ("x1d-II-sample-02.jpg", 13.858, 13.858, 1.0, 1.0),
    ("x1d-II-sample-09.jpg", 17.301, 17.301, 1.0, 1.0),
    ("B0000994.jpg", 14.667, 14.667, 1.0, 1.0),
    ("B0001395.jpg", 16.005, 16.005, 1.0, 1.0),
    ("x1d-xcd45-01.jpg", 16.700, 16.700, 1.0, 1.0),
    ("x1d-xcd45-03.jpg", 3.936, 3.936, 1.0, 1.0),
    ("x1d-xcd45-04.jpg", 3.670, 3.670, 1.0, 1.0),
    ("x1d-ii-xcd45p-01.jpg", 6.563, 6.563, 1.0, 1.0),
    ("x1d-ii-xcd45p-02.jpg", 9.938, 9.938, 1.0, 1.0),
    ("x1d-II-sample-01.jpg", 13.903, 13.903, 1.0, 1.0),
    ("x1d-II-sample-06.jpg", 17.088, 17.088, 1.0, 1.0),
    ("02709.jpg", 12.496, 12.496, 1.0, 1.0),
    ("00378.jpg", 3.866, 3.866, 1.0, 1.0),
]


class TestSummarizeRecordedRun(unittest.TestCase):
    """hybrid_engine/EVALUATION.md에 기록된 실제 13쌍 LOO 결과를
    재현하는 회귀 테스트 - 스크립트를 다시 안 돌려도(60~70분 소요)
    문서의 통계 수치를 검증할 수 있다. 이 기록은 완전히 평평한
    결과다: 13개 LOO 폴드 전부가 훈련 폴드 12쌍에서 (1.0, 1.0)을
    최선으로 골랐다 - baseline과 corrected가 폴드마다 바이트
    단위로(따라서 ΔE 단위로도) 동일하다."""

    def setUp(self):
        self.s = summarize(_RECORDED_13_PAIR_RUN)

    def test_reproduces_documented_means(self):
        self.assertAlmostEqual(self.s["mean_baseline"], 11.538, places=2)
        self.assertAlmostEqual(self.s["mean_corrected"], 11.538, places=2)

    def test_reproduces_documented_win_counts(self):
        self.assertEqual(self.s["corrected_wins"], 0)
        self.assertEqual(self.s["baseline_wins"], 0)

    def test_reproduces_documented_sign_test_p(self):
        self.assertAlmostEqual(self.s["sign_test_p"], 1.0, places=9)

    def test_reproduces_documented_t_stat(self):
        self.assertAlmostEqual(self.s["t_stat"], 0.0, places=3)


# 2026-08 - 13쌍 결과를 83쌍(공식 13 + 로컬 기여 61 + owner-x2dii 9)으로
# 재검증한 실제 재실행 출력 그대로 - hybrid_engine/EVALUATION.md의 같은
# 절에 실린 것과 정확히 같다.
_RECORDED_83_PAIR_RUN = [
    ("x1d-II-sample-02.jpg", 13.864, 13.864, 1.0, 1.0),
    ("x1d-II-sample-09.jpg", 17.319, 17.319, 1.0, 1.0),
    ("B0000994.jpg", 14.709, 14.709, 1.0, 1.0),
    ("B0001395.jpg", 16.023, 16.023, 1.0, 1.0),
    ("x1d-xcd45-01.jpg", 16.704, 16.704, 1.0, 1.0),
    ("x1d-xcd45-03.jpg", 3.942, 3.942, 1.0, 1.0),
    ("x1d-xcd45-04.jpg", 3.717, 3.717, 1.0, 1.0),
    ("x1d-ii-xcd45p-01.jpg", 6.600, 6.600, 1.0, 1.0),
    ("x1d-ii-xcd45p-02.jpg", 9.956, 9.956, 1.0, 1.0),
    ("x1d-II-sample-01.jpg", 13.896, 13.896, 1.0, 1.0),
    ("x1d-II-sample-06.jpg", 17.126, 17.126, 1.0, 1.0),
    ("02709.jpg", 12.498, 12.498, 1.0, 1.0),
    ("00378.jpg", 3.874, 3.874, 1.0, 1.0),
    ("local-mixed-2026-07__6507810936", 8.561, 8.561, 1.0, 1.0),
    ("local-mixed-2026-07__0149725587", 5.300, 5.300, 1.0, 1.0),
    ("local-mixed-2026-07__8204307982", 4.719, 4.719, 1.0, 1.0),
    ("local-mixed-2026-07__3832345792", 5.653, 5.653, 1.0, 1.0),
    ("local-mixed-2026-07__5537240075", 5.370, 5.370, 1.0, 1.0),
    ("local-mixed-2026-07__0587181218", 3.665, 3.665, 1.0, 1.0),
    ("local-mixed-2026-07__7971015535", 4.796, 4.796, 1.0, 1.0),
    ("local-mixed-2026-07__6311094775", 3.239, 3.239, 1.0, 1.0),
    ("local-mixed-2026-07__6787000086", 11.556, 11.556, 1.0, 1.0),
    ("local-mixed-2026-07__7826992126", 5.468, 5.468, 1.0, 1.0),
    ("local-mixed-2026-07__5533274085", 4.380, 4.380, 1.0, 1.0),
    ("local-mixed-2026-07__1094220000", 4.565, 4.565, 1.0, 1.0),
    ("local-mixed-2026-07__8082395282", 4.778, 4.778, 1.0, 1.0),
    ("local-mixed-2026-07__1932636179", 4.849, 4.849, 1.0, 1.0),
    ("local-mixed-2026-07__3953661245", 4.820, 4.820, 1.0, 1.0),
    ("local-mixed-2026-07__8127122405", 2.688, 2.688, 1.0, 1.0),
    ("local-mixed-2026-07__5746737497", 8.011, 8.011, 1.0, 1.0),
    ("local-mixed-2026-07__9515423899", 3.256, 3.256, 1.0, 1.0),
    ("local-mixed-2026-07__6454535758", 4.039, 4.039, 1.0, 1.0),
    ("local-mixed-2026-07__8742913299", 3.528, 3.528, 1.0, 1.0),
    ("local-mixed-2026-07__7492975828", 2.932, 2.932, 1.0, 1.0),
    ("local-mixed-2026-07__7321006825", 4.051, 4.051, 1.0, 1.0),
    ("local-mixed-2026-07__6660888354", 33.030, 33.030, 1.0, 1.0),
    ("local-mixed-2026-07__4236625428", 4.179, 4.179, 1.0, 1.0),
    ("local-mixed-2026-07__8581844385", 14.945, 14.945, 1.0, 1.0),
    ("local-mixed-2026-07__7121592185", 14.233, 14.233, 1.0, 1.0),
    ("local-mixed-2026-07__3766372330", 5.108, 5.108, 1.0, 1.0),
    ("local-mixed-2026-07__7732046028", 5.089, 5.089, 1.0, 1.0),
    ("local-mixed-2026-07__0908944042", 5.976, 5.976, 1.0, 1.0),
    ("local-mixed-2026-07__1917191504", 4.026, 4.026, 1.0, 1.0),
    ("local-mixed-2026-07__9011626130", 3.094, 3.094, 1.0, 1.0),
    ("local-mixed-2026-07__5310704161", 5.721, 5.721, 1.0, 1.0),
    ("local-mixed-2026-07__3683076943", 6.521, 6.521, 1.0, 1.0),
    ("local-mixed-2026-07__7406451876", 6.420, 6.420, 1.0, 1.0),
    ("local-mixed-2026-07__6519755969", 6.228, 6.228, 1.0, 1.0),
    ("local-mixed-2026-07__3333340029", 14.562, 14.562, 1.0, 1.0),
    ("local-mixed-2026-07__9479682988", 8.794, 8.794, 1.0, 1.0),
    ("local-mixed-2026-07__5385314660", 5.263, 5.263, 1.0, 1.0),
    ("local-mixed-2026-07__9247740424", 2.064, 2.064, 1.0, 1.0),
    ("local-mixed-2026-07__5715595764", 7.856, 7.856, 1.0, 1.0),
    ("local-mixed-2026-07__6704898202", 4.434, 4.434, 1.0, 1.0),
    ("local-mixed-2026-07__6340134840", 3.312, 3.312, 1.0, 1.0),
    ("local-mixed-2026-07__9928856380", 4.626, 4.626, 1.0, 1.0),
    ("local-mixed-2026-07__0758706524", 5.617, 5.617, 1.0, 1.0),
    ("local-mixed-2026-07__4087418227", 5.991, 5.991, 1.0, 1.0),
    ("local-mixed-2026-07__1063588653", 4.103, 4.103, 1.0, 1.0),
    ("local-mixed-2026-07__1755788551", 36.830, 36.830, 1.0, 1.0),
    ("local-mixed-2026-07__9070200412", 3.622, 3.622, 1.0, 1.0),
    ("local-mixed-2026-07__9318140329", 3.151, 3.151, 1.0, 1.0),
    ("local-mixed-2026-07__4589763049", 4.061, 4.061, 1.0, 1.0),
    ("local-mixed-2026-07__0229019868", 23.371, 23.371, 1.0, 1.0),
    ("local-mixed-2026-07__9063680763", 17.749, 17.749, 1.0, 1.0),
    ("local-mixed-2026-07__0550549226", 3.032, 3.032, 1.0, 1.0),
    ("local-mixed-2026-07__3153320186", 6.197, 6.197, 1.0, 1.0),
    ("local-mixed-2026-07__6762931572", 13.810, 13.810, 1.0, 1.0),
    ("local-mixed-2026-07__6661213999", 14.762, 14.762, 1.0, 1.0),
    ("local-mixed-2026-07__5983653715", 14.564, 14.564, 1.0, 1.0),
    ("local-mixed-2026-07__1372685658", 5.547, 5.547, 1.0, 1.0),
    ("local-mixed-2026-07__3528755502", 8.622, 8.622, 1.0, 1.0),
    ("local-mixed-2026-07__7278483295", 28.388, 28.388, 1.0, 1.0),
    ("local-mixed-2026-07__8647104982", 7.607, 7.607, 1.0, 1.0),
    ("owner-x2dii-2026-08__B0000044", 20.267, 20.267, 1.0, 1.0),
    ("owner-x2dii-2026-08__B0000125", 13.905, 13.905, 1.0, 1.0),
    ("owner-x2dii-2026-08__B0000203", 9.547, 9.547, 1.0, 1.0),
    ("owner-x2dii-2026-08__B0000204", 8.632, 8.632, 1.0, 1.0),
    ("owner-x2dii-2026-08__B00002333FR1756808191", 20.788, 20.788, 1.0, 1.0),
    ("owner-x2dii-2026-08__B0000239", 16.981, 16.981, 1.0, 1.0),
    ("owner-x2dii-2026-08__B0000241", 17.460, 17.460, 1.0, 1.0),
    ("owner-x2dii-2026-08__B0000246", 12.230, 12.230, 1.0, 1.0),
    ("owner-x2dii-2026-08__B0000251", 7.951, 7.951, 1.0, 1.0),
]


class TestSummarizeRecordedRun83Pair(unittest.TestCase):
    """hybrid_engine/EVALUATION.md에 기록된 83쌍(74쌍 확장 + owner-x2dii
    9쌍) LOO 결과를 재현하는 회귀 테스트 - 13쌍 결과와 마찬가지로 완전히
    평평하다(83개 폴드 전부 (1.0, 1.0) 선택)."""

    def setUp(self):
        self.s = summarize(_RECORDED_83_PAIR_RUN)

    def test_reproduces_documented_means(self):
        self.assertAlmostEqual(self.s["mean_baseline"], 9.165, places=3)
        self.assertAlmostEqual(self.s["mean_corrected"], 9.165, places=3)

    def test_reproduces_documented_win_counts(self):
        self.assertEqual(self.s["corrected_wins"], 0)
        self.assertEqual(self.s["baseline_wins"], 0)

    def test_reproduces_documented_sign_test_p(self):
        self.assertAlmostEqual(self.s["sign_test_p"], 1.0, places=9)

    def test_reproduces_documented_t_stat(self):
        self.assertAlmostEqual(self.s["t_stat"], 0.0, places=3)


if __name__ == "__main__":
    unittest.main()
