import unittest

import numpy as np

from core.curve import apply_highlight_rolloff, film_curve, s_curve, shadow_lift


class TestFilmCurve(unittest.TestCase):
    def setUp(self):
        self.x = np.linspace(0, 1, 256, dtype=np.float32)

    def test_output_range_clipped(self):
        y = film_curve(self.x)
        self.assertTrue(np.all(y >= 0))
        self.assertTrue(np.all(y <= 1))

    def test_toe_lift_applied_at_zero(self):
        y = film_curve(self.x, toe_lift=0.05)
        self.assertAlmostEqual(y[0], 0.05, places=3)

    def test_default_toe_lift_near_zero(self):
        y = film_curve(self.x, toe_lift=0.001)
        self.assertAlmostEqual(y[0], 0.001, places=3)

    def test_white_point_reached_at_one(self):
        y = film_curve(self.x, white_point=0.9)
        self.assertAlmostEqual(y[-1], 0.9, places=2)

    def test_monotonically_nondecreasing(self):
        y = film_curve(self.x)
        self.assertTrue(np.all(np.diff(y) >= -1e-6))

    def test_shoulder_start_is_identity_point(self):
        # x==shoulder_start의 shoulder 공식 t2=0이므로 y==shoulder_start 그대로여야 함
        shoulder_start = 0.78
        x = np.array([shoulder_start], dtype=np.float32)
        y = film_curve(x, shoulder_start=shoulder_start, white_point=0.9)
        self.assertAlmostEqual(y[0], shoulder_start, places=5)

    def test_does_not_mutate_input(self):
        x_copy = self.x.copy()
        film_curve(self.x)
        np.testing.assert_array_equal(self.x, x_copy)

    def test_monotonic_even_when_toe_lift_exceeds_toe_domain(self):
        # toe_lift가 toe 구간 상한(0.1)을 넘으면 [0,0.1] 보간 기울기가
        # 음수가 돼서 어두운 픽셀이 밝은 픽셀보다 밝게 나오는 반전이
        # 생겼던 버그 - 0.099로 clamp해서 방지했는지 확인.
        y = film_curve(self.x, toe_lift=0.3)
        self.assertTrue(np.all(np.diff(y) >= -1e-6))

    def test_shoulder_start_near_one_does_not_blow_up(self):
        # shoulder_start가 1에 가까우면 (1 - shoulder_start) 분모가 0에
        # 가까워져 t2가 발산할 수 있었던 경우 - 0.999로 clamp해서 방지.
        y = film_curve(self.x, shoulder_start=1.0)
        self.assertTrue(np.all(np.isfinite(y)))
        self.assertTrue(np.all(y >= 0))
        self.assertTrue(np.all(y <= 1))


class TestSCurve(unittest.TestCase):
    def test_endpoints(self):
        x = np.array([1e-6, 1 - 1e-6])
        y = s_curve(x, n=2.0)
        self.assertAlmostEqual(y[0], 0.0, places=3)
        self.assertAlmostEqual(y[1], 1.0, places=3)

    def test_midpoint_is_half(self):
        y = s_curve(np.array([0.5]), n=2.0)
        self.assertAlmostEqual(y[0], 0.5, places=6)

    def test_n_equals_one_is_identity(self):
        x = np.linspace(0.01, 0.99, 20)
        y = s_curve(x, n=1.0)
        np.testing.assert_allclose(y, x, atol=1e-6)

    def test_n_greater_than_one_increases_contrast(self):
        # n>1이면 0.5 미만은 더 어둡게, 0.5 초과는 더 밝게 눌려야 함
        y = s_curve(np.array([0.3, 0.7]), n=3.0)
        self.assertLess(y[0], 0.3)
        self.assertGreater(y[1], 0.7)


class TestHighlightRolloff(unittest.TestCase):
    def test_noop_when_no_pixels_above_start(self):
        x = np.linspace(0, 0.5, 50)
        y = x.copy()
        out = apply_highlight_rolloff(x, y, start=0.8)
        np.testing.assert_array_equal(out, x)

    def test_continuity_at_start_boundary(self):
        x = np.linspace(0, 1, 500)
        y = x.copy()
        out = apply_highlight_rolloff(x, y, start=0.8)
        idx = np.searchsorted(x, 0.8)
        # rolloff 시작 직전/직후 값이 크게 튀지 않아야 함(연속성)
        self.assertLess(abs(out[idx] - out[max(idx - 1, 0)]), 0.05)

    def test_compresses_toward_headroom(self):
        x = np.linspace(0, 1, 500)
        y = x.copy()
        out = apply_highlight_rolloff(x, y, start=0.8)
        self.assertLessEqual(out[-1], 1.0 + 1e-6)


class TestShadowLift(unittest.TestCase):
    def test_lifts_below_threshold(self):
        x = np.array([0.0, 0.05, 0.1, 0.5])
        y = x.copy()
        out = shadow_lift(x, y, lift=0.02, threshold=0.1)
        self.assertGreater(out[0], x[0])
        self.assertGreater(out[1], x[1])

    def test_no_lift_at_or_above_threshold(self):
        x = np.array([0.1, 0.5])
        y = x.copy()
        out = shadow_lift(x, y, lift=0.02, threshold=0.1)
        np.testing.assert_array_equal(out, x)

    def test_max_lift_at_zero(self):
        x = np.array([0.0])
        y = x.copy()
        out = shadow_lift(x, y, lift=0.02, threshold=0.1)
        self.assertAlmostEqual(out[0], 0.02, places=6)

    def test_does_not_mutate_input_y(self):
        x = np.array([0.0, 0.05, 0.5])
        y = x.copy()
        y_before = y.copy()
        shadow_lift(x, y, lift=0.02, threshold=0.1)
        np.testing.assert_array_equal(y, y_before)

    def test_output_clipped_to_one(self):
        x = np.array([0.0])
        y = np.array([0.99])
        out = shadow_lift(x, y, lift=0.5, threshold=0.1)
        self.assertLessEqual(out[0], 1.0)


if __name__ == "__main__":
    unittest.main()
