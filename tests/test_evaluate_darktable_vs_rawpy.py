import csv
import os
import tempfile
import unittest

import numpy as np

from tools.evaluate_darktable_vs_rawpy import (
    _resize_max_dim, _sign_test_p, load_fuji_pairs, summarize,
)

_FIELDS = ["camera", "datetime", "film_mode", "raw_path", "jpeg_path"]

# 실제 16쌍 재실행(2098cbf, OMP_NUM_THREADS 버그 수정 이후) 기록값 -
# hybrid_engine/EVALUATION.md의 "darktable vs rawpy RAW 디코드 비교"
# 절에 실린 것과 정확히 같다. (camera, name, de_rawpy, de_dt, improved)
_RECORDED_16_PAIR_RUN = [
    ("Hasselblad", "x1d-II-sample-02.jpg", 14.225, 15.955, False),
    ("Hasselblad", "x1d-II-sample-09.jpg", 17.386, 17.771, False),
    ("Hasselblad", "B0000994.jpg", 14.926, 15.226, False),
    ("Hasselblad", "B0001395.jpg", 16.366, 16.428, False),
    ("Hasselblad", "x1d-xcd45-01.jpg", 16.715, 16.721, False),
    ("Hasselblad", "x1d-xcd45-03.jpg", 4.055, 5.649, False),
    ("Hasselblad", "x1d-xcd45-04.jpg", 4.029, 4.186, False),
    ("Hasselblad", "x1d-ii-xcd45p-01.jpg", 6.657, 7.078, False),
    ("Hasselblad", "x1d-ii-xcd45p-02.jpg", 10.065, 12.843, False),
    ("Hasselblad", "x1d-II-sample-01.jpg", 13.983, 14.040, False),
    ("Hasselblad", "x1d-II-sample-06.jpg", 17.202, 17.482, False),
    ("Hasselblad", "02709.jpg", 12.533, 12.584, False),
    ("Hasselblad", "00378.jpg", 4.007, 4.709, False),
    ("Fujifilm X-T3", "DSCF3954.RAF", 11.648, 11.557, True),
    ("Fujifilm X-T30", "DSCF7094.RAF", 8.379, 8.107, True),
    ("Fujifilm X-T30", "DSCF7030.RAF", 11.188, 11.181, True),
]


class TestLoadFujiPairs(unittest.TestCase):
    def _write_manifest(self, rows):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        self.addCleanup(os.remove, path)
        return path

    def test_parses_camera_and_paths(self):
        path = self._write_manifest([{
            "camera": "Fujifilm X-T3", "datetime": "t", "film_mode": "m",
            "raw_path": "raw_calib_cache_fuji/Fujifilm_X-T3/raw/DSCF3954.RAF",
            "jpeg_path": "raw_calib_cache_fuji/Fujifilm_X-T3/jpeg/DSCF3954.jpg",
        }])
        pairs = load_fuji_pairs(manifest_path=path)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["camera"], "Fujifilm X-T3")
        self.assertEqual(pairs[0]["name"], "DSCF3954.RAF")

    def test_paths_are_absolute(self):
        path = self._write_manifest([{
            "camera": "Fujifilm X-T30", "datetime": "t", "film_mode": "m",
            "raw_path": "raw_calib_cache_fuji/Fujifilm_X-T30/raw/DSCF7030.RAF",
            "jpeg_path": "raw_calib_cache_fuji/Fujifilm_X-T30/jpeg/DSCF7030.JPG",
        }])
        pairs = load_fuji_pairs(manifest_path=path)
        self.assertTrue(os.path.isabs(pairs[0]["raw_path"]))
        self.assertTrue(os.path.isabs(pairs[0]["jpeg_path"]))

    def test_multiple_rows_preserve_order(self):
        path = self._write_manifest([
            {"camera": "A", "datetime": "t1", "film_mode": "m1",
             "raw_path": "r1.RAF", "jpeg_path": "j1.jpg"},
            {"camera": "B", "datetime": "t2", "film_mode": "m2",
             "raw_path": "r2.RAF", "jpeg_path": "j2.jpg"},
        ])
        pairs = load_fuji_pairs(manifest_path=path)
        self.assertEqual([p["camera"] for p in pairs], ["A", "B"])


class TestResizeMaxDim(unittest.TestCase):
    def test_noop_when_already_smaller_than_max_dim(self):
        img = np.random.default_rng(0).uniform(0, 1, size=(10, 20, 3))
        out = _resize_max_dim(img, max_dim=1024)
        self.assertEqual(out.shape, img.shape)

    def test_downsamples_when_larger_than_max_dim(self):
        img = np.random.default_rng(1).uniform(0, 1, size=(2000, 4000, 3))
        out = _resize_max_dim(img, max_dim=1024)
        self.assertLessEqual(max(out.shape[:2]), 1024)
        self.assertAlmostEqual(out.shape[1] / out.shape[0], 4000 / 2000, places=1)

    def test_preserves_channel_count(self):
        img = np.random.default_rng(2).uniform(0, 1, size=(1200, 600, 3))
        out = _resize_max_dim(img, max_dim=1024)
        self.assertEqual(out.shape[2], 3)


class TestSignTestP(unittest.TestCase):
    def test_even_split_is_p_one(self):
        self.assertAlmostEqual(_sign_test_p(8, 8), 1.0)

    def test_no_pairs_is_p_one(self):
        self.assertAlmostEqual(_sign_test_p(0, 0), 1.0)

    def test_all_wins_is_significant(self):
        self.assertLess(_sign_test_p(16, 0), 0.001)

    def test_thirteen_of_sixteen_matches_documented_p(self):
        # hybrid_engine/EVALUATION.md에 기록된 실제 부호검정 p값(≈0.0213)
        self.assertAlmostEqual(_sign_test_p(13, 3), 0.021270751953125, places=9)


class TestSummarizeRecordedRun(unittest.TestCase):
    """hybrid_engine/EVALUATION.md에 기록된 실제 16쌍 재실행 결과를
    재현하는 회귀 테스트 - 스크립트를 다시 안 돌려도 문서의 통계
    수치를 검증할 수 있다."""

    def setUp(self):
        self.s = summarize(_RECORDED_16_PAIR_RUN)

    def test_reproduces_documented_means(self):
        self.assertAlmostEqual(self.s["mean_rawpy"], 11.460, places=2)
        self.assertAlmostEqual(self.s["mean_darktable"], 11.970, places=2)

    def test_reproduces_documented_win_counts(self):
        self.assertEqual(self.s["rawpy_wins"], 13)
        self.assertEqual(self.s["darktable_wins"], 3)

    def test_reproduces_documented_mean_diff(self):
        # EVALUATION.md의 -0.509845(rawpy-darktable, 원본 풀정밀도 계산)와
        # 부호가 반대(summarize()는 darktable-rawpy)이고, 이 페어별 표는
        # 소수점 3자리로 반올림된 값이라 5번째 자리까지는 완전히 일치하지
        # 않는다(반올림 오차 ~0.0003) - places=3이 이 표에서 실제로
        # 재현 가능한 정밀도다.
        self.assertAlmostEqual(self.s["mean_diff"], 0.5095625, places=3)

    def test_reproduces_documented_sign_test_p(self):
        self.assertAlmostEqual(self.s["sign_test_p"], 0.021270751953125, places=9)

    def test_reproduces_documented_t_stat(self):
        self.assertAlmostEqual(self.s["t_stat"], 2.4718, places=3)


if __name__ == "__main__":
    unittest.main()
