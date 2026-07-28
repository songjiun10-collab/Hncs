import unittest
from unittest.mock import patch

import numpy as np

from hybrid_engine.research.hncs_structural import (
    CLUSTER_THRESHOLD_R_OVER_B,
    apply_chroma_lut,
    apply_hncs_structural,
    classify_illuminant_cluster,
    decode_and_white_balance,
)


class TestClassifyIlluminantCluster(unittest.TestCase):
    def test_below_threshold_is_cluster_a(self):
        # R/B = 0.4 / 0.6 = 0.667 < 0.9
        self.assertEqual(
            classify_illuminant_cluster(np.array([0.4, 1.0, 0.6])), "cluster_a")

    def test_at_or_above_threshold_is_cluster_b(self):
        # R/B = 1.2 / 1.0 = 1.2 >= 0.9
        self.assertEqual(
            classify_illuminant_cluster(np.array([1.2, 1.0, 1.0])), "cluster_b")

    def test_exactly_at_threshold_is_cluster_b(self):
        # R/B = 0.9 / 1.0 = 0.9, boundary is inclusive on the cluster_b side
        self.assertEqual(
            classify_illuminant_cluster(np.array([0.9, 1.0, 1.0])), "cluster_b")

    def test_uses_module_threshold_constant(self):
        self.assertEqual(CLUSTER_THRESHOLD_R_OVER_B, 0.9)


class TestDecodeAndWhiteBalance(unittest.TestCase):
    @patch("hybrid_engine.research.hncs_structural.read_as_shot_neutral")
    @patch("hybrid_engine.research.hncs_structural.decode_raw_native")
    def test_divides_native_rgb_by_as_shot_neutral(self, mock_decode, mock_asn):
        mock_decode.return_value = np.array([[[0.4, 1.0, 0.6]]])
        mock_asn.return_value = np.array([0.4, 1.0, 0.6])
        result = decode_and_white_balance("fake.3FR")
        np.testing.assert_allclose(result, np.array([[[1.0, 1.0, 1.0]]]))

    @patch("hybrid_engine.research.hncs_structural.read_as_shot_neutral")
    @patch("hybrid_engine.research.hncs_structural.decode_raw_native")
    def test_raises_when_as_shot_neutral_missing(self, mock_decode, mock_asn):
        mock_decode.return_value = np.zeros((2, 2, 3))
        mock_asn.return_value = None
        with self.assertRaises(ValueError):
            decode_and_white_balance("fake.3FR")


class TestApplyChromaLut(unittest.TestCase):
    def test_identity_when_sat_mult_1_and_hue_shift_0(self):
        rng = np.random.default_rng(0)
        img = rng.uniform(0.05, 0.9, size=(8, 8, 3))
        out = apply_chroma_lut(img, sat_mult=1.0, hue_shift_deg=0.0)
        np.testing.assert_allclose(out, img, atol=1e-3)

    def test_hue_shift_is_360_periodic(self):
        rng = np.random.default_rng(1)
        img = rng.uniform(0.05, 0.9, size=(6, 6, 3))
        out_0 = apply_chroma_lut(img, sat_mult=1.0, hue_shift_deg=0.0)
        out_360 = apply_chroma_lut(img, sat_mult=1.0, hue_shift_deg=360.0)
        np.testing.assert_allclose(out_0, out_360, atol=1e-3)

    def test_sat_mult_zero_desaturates_to_gray(self):
        img = np.array([[[0.9, 0.1, 0.1]]])  # saturated red
        out = apply_chroma_lut(img, sat_mult=0.0, hue_shift_deg=0.0)
        r, g, b = out[0, 0]
        self.assertAlmostEqual(r, g, delta=1e-3)
        self.assertAlmostEqual(g, b, delta=1e-3)

    def test_output_shape_matches_input(self):
        rng = np.random.default_rng(2)
        img = rng.uniform(0.05, 0.9, size=(5, 7, 3))
        out = apply_chroma_lut(img, sat_mult=1.1, hue_shift_deg=3.0)
        self.assertEqual(out.shape, img.shape)


class TestApplyHncsStructural(unittest.TestCase):
    @patch("hybrid_engine.research.hncs_structural.read_as_shot_neutral")
    @patch("hybrid_engine.research.hncs_structural.decode_raw_native")
    def test_identity_matrix_and_chroma_matches_film_curve_directly(
            self, mock_decode, mock_asn):
        rng = np.random.default_rng(3)
        native = rng.uniform(0.02, 0.3, size=(4, 4, 3))
        as_shot_neutral = np.array([0.4, 1.0, 0.6])  # R/B=0.667 -> cluster_a
        mock_decode.return_value = native
        mock_asn.return_value = as_shot_neutral
        wb_rgb = native / as_shot_neutral

        matrices = {"cluster_a": np.eye(3), "cluster_b": np.eye(3)}
        chroma_params = {"cluster_a": (1.0, 0.0), "cluster_b": (1.0, 0.0)}
        result = apply_hncs_structural(
            "fake.3FR", matrices, chroma_params,
            toe_lift=0.001, shoulder_start=0.78, white_point=1.0)

        from core.curve import film_curve
        expected = film_curve(wb_rgb, toe_lift=0.001, shoulder_start=0.78,
                               white_point=1.0)
        np.testing.assert_allclose(result, expected, atol=1e-2)

    @patch("hybrid_engine.research.hncs_structural.read_as_shot_neutral")
    @patch("hybrid_engine.research.hncs_structural.decode_raw_native")
    def test_selects_matrix_for_cluster_b_when_r_over_b_high(
            self, mock_decode, mock_asn):
        native = np.full((3, 3, 3), 0.3)
        as_shot_neutral = np.array([1.2, 1.0, 1.0])  # R/B=1.2 -> cluster_b
        mock_decode.return_value = native
        mock_asn.return_value = as_shot_neutral

        # cluster_a gets a matrix that would blow up the output (2x gain);
        # cluster_b keeps identity. If the wrong matrix is picked, the
        # shoulder/highlight clipping in film_curve makes the two diverge.
        matrices = {"cluster_a": np.eye(3) * 2.0, "cluster_b": np.eye(3)}
        chroma_params = {"cluster_a": (1.0, 0.0), "cluster_b": (1.0, 0.0)}
        result = apply_hncs_structural(
            "fake.3FR", matrices, chroma_params,
            toe_lift=0.001, shoulder_start=0.78, white_point=1.0)

        from core.curve import film_curve
        wb_rgb = native / as_shot_neutral
        expected = film_curve(wb_rgb, toe_lift=0.001, shoulder_start=0.78,
                               white_point=1.0)
        np.testing.assert_allclose(result, expected, atol=1e-2)


if __name__ == "__main__":
    unittest.main()
