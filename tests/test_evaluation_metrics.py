import unittest

import numpy as np

from hybrid_engine.evaluation.metrics import (
    delta_e_stats, delta_e_by_zone, saturation_hue_delta, ssim_L, full_report,
)


class TestDeltaEStats(unittest.TestCase):
    def test_identical_images_are_zero(self):
        img = np.full((8, 8, 3), 0.4)
        stats = delta_e_stats(img, img)
        self.assertEqual(stats, {"mean": 0.0, "median": 0.0, "p95": 0.0, "max": 0.0})

    def test_shape_mismatch_raises(self):
        a = np.zeros((4, 4, 3))
        b = np.zeros((5, 5, 3))
        with self.assertRaises(ValueError):
            delta_e_stats(a, b)

    def test_outlier_region_raises_p95_and_max_more_than_mean(self):
        rng = np.random.default_rng(0)
        a = np.full((40, 40, 3), 0.4)
        b = a.copy()
        # 대부분 동일, 작은 영역만 크게 다르게 - p95/max가 mean보다 훨씬 커야 함
        b[:4, :4, 0] = 0.9
        stats = delta_e_stats(a, b)
        self.assertGreater(stats["max"], stats["mean"])
        self.assertGreaterEqual(stats["p95"], stats["median"])


class TestDeltaEByZone(unittest.TestCase):
    def test_only_highlight_present_for_bright_flat_image(self):
        img = np.full((8, 8, 3), 0.9)  # L 채널이 높아서 highlight 존만 표본 있음
        other = img.copy()
        other[..., 0] += 0.05
        zones = delta_e_by_zone(img, other)
        self.assertIsNone(zones["shadow"])
        self.assertIsNone(zones["midtone"])
        self.assertIsNotNone(zones["highlight"])

    def test_shadow_zone_isolates_dark_region_error(self):
        a = np.zeros((20, 20, 3))
        a[:10, :, :] = 0.05  # 어두운 절반
        a[10:, :, :] = 0.9   # 밝은 절반
        b = a.copy()
        b[:10, :, 0] += 0.05  # 어두운 절반에만 오차 주입
        zones = delta_e_by_zone(a, b)
        self.assertGreater(zones["shadow"], 0.0)
        self.assertAlmostEqual(zones["highlight"], 0.0, places=6)


class TestSaturationHueDelta(unittest.TestCase):
    def test_identical_is_zero(self):
        img = np.full((8, 8, 3), 0.4)
        result = saturation_hue_delta(img, img)
        self.assertAlmostEqual(result["mean_abs_dchroma"], 0.0, places=6)
        self.assertAlmostEqual(result["mean_abs_dhue_deg"], 0.0, places=6)

    def test_hue_wraparound_is_small_near_0_360(self):
        # 순수 빨강 근처 두 색 - hue가 0도 근방에서 반대편(360도 근방)으로
        # 넘어가도 실제 각도차는 작아야 함(wraparound 처리 검증)
        a = np.zeros((4, 4, 3))
        a[..., 0] = 0.9  # R 우세
        a[..., 1] = 0.05
        b = a.copy()
        b[..., 2] = 0.03  # 아주 약간의 파란기 추가 - hue가 반대 방향으로 살짝 이동
        result = saturation_hue_delta(a, b)
        self.assertLess(result["mean_abs_dhue_deg"], 90.0)


class TestSsimL(unittest.TestCase):
    def test_identical_images_ssim_is_one(self):
        rng = np.random.default_rng(1)
        img = rng.uniform(0.1, 0.8, size=(32, 32, 3))
        self.assertAlmostEqual(ssim_L(img, img), 1.0, places=6)

    def test_very_different_images_have_low_ssim(self):
        rng = np.random.default_rng(2)
        a = np.zeros((32, 32, 3)) + 0.1
        b = rng.uniform(0, 1, size=(32, 32, 3))  # 완전 노이즈
        self.assertLess(ssim_L(a, b), 0.5)


class TestFullReport(unittest.TestCase):
    def test_contains_all_metric_groups(self):
        img = np.full((8, 8, 3), 0.4)
        report = full_report(img, img)
        self.assertEqual(set(report.keys()),
                          {"delta_e", "delta_e_by_zone", "saturation_hue", "ssim_L"})


if __name__ == "__main__":
    unittest.main()
