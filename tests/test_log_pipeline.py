import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from core.log_pipeline import (
    LOG_SPACES, HDR_SPACES, apply_exposure, auto_exposure_average, auto_exposure_highlight_safe,
    auto_exposure_matrix, estimate_wb_shades_of_gray, estimate_wb_white_patch,
    raw_to_prophoto_linear, to_log_space, to_hdr_space, apply_cube_lut, to_16bit_bgr, write_exr,
)

_IDENTITY_CUBE = """TITLE "Identity"
LUT_3D_SIZE 2
0.0 0.0 0.0
1.0 0.0 0.0
0.0 1.0 0.0
1.0 1.0 0.0
0.0 0.0 1.0
1.0 0.0 1.0
0.0 1.0 1.0
1.0 1.0 1.0
"""


class TestApplyExposure(unittest.TestCase):
    def test_zero_ev_is_passthrough(self):
        img = np.full((4, 4, 3), 0.3)
        out = apply_exposure(img, ev=0.0)
        self.assertIs(out, img)

    def test_positive_ev_brightens(self):
        img = np.full((4, 4, 3), 0.1)
        out = apply_exposure(img, ev=1.0)
        np.testing.assert_allclose(out, img * 2.0)

    def test_negative_ev_darkens(self):
        img = np.full((4, 4, 3), 0.4)
        out = apply_exposure(img, ev=-1.0)
        np.testing.assert_allclose(out, img * 0.5)


class TestAutoExposureAverage(unittest.TestCase):
    def test_scales_mean_to_target_gray(self):
        img = np.full((8, 8, 3), 0.09)
        out = auto_exposure_average(img, target_gray=0.18)
        self.assertAlmostEqual(float(np.mean(out)), 0.18, places=6)

    def test_all_zero_image_is_unchanged(self):
        img = np.zeros((4, 4, 3))
        out = auto_exposure_average(img)
        np.testing.assert_array_equal(out, img)


class TestAutoExposureHighlightSafe(unittest.TestCase):
    def test_scales_percentile_to_target(self):
        rng = np.random.default_rng(0)
        img = np.zeros((20, 20, 3))
        img[..., :] = rng.uniform(0.05, 0.3, size=(20, 20, 1))
        img[0, 0] = 0.9  # 스펙큘러 하이라이트 한 픽셀 (400픽셀 중 1개 = 99.75 백분위)
        out = auto_exposure_highlight_safe(img, percentile=99.5, target=0.9)
        luma = out.mean(axis=-1)
        p = np.percentile(luma, 99.5)
        self.assertAlmostEqual(p, 0.9, places=2)

    def test_bright_highlight_darkens_more_than_average_metering(self):
        # 어두운 배경 + 밝은 창문(하이라이트, 전체의 9%) - percentile을
        # 하이라이트 비중보다 낮게 잡아야(95 < 100-9) 측광이 실제로 그
        # 하이라이트를 "보고" 지킨다 - highlight-safe는 하이라이트를
        # 지키느라 average보다 더 어둡게 노출을 잡아야 함.
        img = np.full((20, 20, 3), 0.1)
        img[:6, :6] = 1.0  # 36/400 = 9% 픽셀이 밝은 하이라이트
        out_avg = auto_exposure_average(img, target_gray=0.18)
        out_hs = auto_exposure_highlight_safe(img, percentile=95.0, target=0.9)
        self.assertLess(float(np.mean(out_hs)), float(np.mean(out_avg)))

    def test_all_zero_image_is_unchanged(self):
        img = np.zeros((4, 4, 3))
        out = auto_exposure_highlight_safe(img)
        np.testing.assert_array_equal(out, img)


class TestAutoExposureMatrix(unittest.TestCase):
    def test_uniform_image_scales_to_target_gray(self):
        img = np.full((10, 10, 3), 0.09)
        out = auto_exposure_matrix(img, target_gray=0.18)
        self.assertAlmostEqual(float(np.mean(out)), 0.18, places=2)

    def test_center_weighting_ignores_bright_corners(self):
        # 중앙은 어둡고 가장자리(구석)만 밝은 이미지 - 매트릭스 측광은
        # 중앙에 가중치를 주므로, 순수 average metering보다 덜 어둡게
        # (덜 보정) 노출을 잡아야 함(가장자리의 밝기에 덜 휘둘림).
        img = np.full((20, 20, 3), 0.05)
        img[:4, :4] = 0.9
        img[:4, -4:] = 0.9
        img[-4:, :4] = 0.9
        img[-4:, -4:] = 0.9
        out_avg = auto_exposure_average(img, target_gray=0.18)
        out_matrix = auto_exposure_matrix(img, target_gray=0.18, center_weight=5.0)
        # average는 밝은 구석들 때문에 전체 평균이 이미 높아서 덜 끌어올림
        # (스케일이 1에 더 가까움) -> matrix는 중앙(어두운 값) 기준으로
        # 맞추므로 더 많이 밝게 끌어올려야(스케일이 더 커야) 함.
        self.assertGreater(float(np.mean(out_matrix)), float(np.mean(out_avg)))

    def test_all_zero_image_is_unchanged(self):
        img = np.zeros((10, 10, 3))
        out = auto_exposure_matrix(img)
        np.testing.assert_array_equal(out, img)


class TestEstimateWbWhitePatch(unittest.TestCase):
    def test_uniform_color_cast_neutralized(self):
        # 순수 회색 장면에 (2, 1, 0.5) 조명색이 곱해진 상황을 시뮬레이션
        img = np.full((8, 8, 3), 0.4) * np.array([2.0, 1.0, 0.5])
        out = estimate_wb_white_patch(img, percentile=100)
        # 채널별 max가 정확히 1이 되어야 함(장면 전체가 균일해서 percentile=max)
        np.testing.assert_allclose(out.reshape(-1, 3).max(axis=0), [1.0, 1.0, 1.0])

    def test_all_zero_channel_avoids_division_by_zero(self):
        img = np.zeros((4, 4, 3))
        out = estimate_wb_white_patch(img)
        self.assertTrue(np.all(np.isfinite(out)))


class TestEstimateWbShadesOfGray(unittest.TestCase):
    def test_uniform_color_cast_neutralized_to_equal_channels(self):
        img = np.full((8, 8, 3), 0.4) * np.array([2.0, 1.0, 0.5])
        out = estimate_wb_shades_of_gray(img, p=6)
        result_channels = out.reshape(-1, 3)[0]
        # 셋 다 같은 값으로 돌아와야 함(균일 장면이라 p 값에 무관하게
        # 완전히 중화됨)
        self.assertAlmostEqual(result_channels[0], result_channels[1], places=6)
        self.assertAlmostEqual(result_channels[1], result_channels[2], places=6)

    def test_all_zero_channel_avoids_division_by_zero(self):
        img = np.zeros((4, 4, 3))
        out = estimate_wb_shades_of_gray(img)
        self.assertTrue(np.all(np.isfinite(out)))


class TestRawToProphotoLinearWhiteBalanceFlag(unittest.TestCase):
    @patch("core.log_pipeline.rawpy.imread")
    def test_camera_wb_true_passes_use_camera_wb(self, mock_imread):
        mock_raw = MagicMock()
        mock_raw.postprocess.return_value = np.zeros((4, 4, 3), dtype=np.uint16)
        mock_imread.return_value.__enter__.return_value = mock_raw

        raw_to_prophoto_linear("dummy.CR3", use_camera_wb=True)

        kwargs = mock_raw.postprocess.call_args.kwargs
        self.assertEqual(kwargs.get("use_camera_wb"), True)
        self.assertNotIn("user_wb", kwargs)

    @patch("core.log_pipeline.rawpy.imread")
    def test_camera_wb_false_passes_identity_user_wb(self, mock_imread):
        mock_raw = MagicMock()
        mock_raw.postprocess.return_value = np.zeros((4, 4, 3), dtype=np.uint16)
        mock_imread.return_value.__enter__.return_value = mock_raw

        raw_to_prophoto_linear("dummy.CR3", use_camera_wb=False)

        kwargs = mock_raw.postprocess.call_args.kwargs
        self.assertEqual(kwargs.get("user_wb"), [1.0, 1.0, 1.0, 1.0])
        self.assertNotIn("use_camera_wb", kwargs)


class TestToLogSpace(unittest.TestCase):
    def test_unknown_log_space_raises(self):
        img = np.full((4, 4, 3), 0.18)
        with self.assertRaises(ValueError):
            to_log_space(img, "not-a-real-log-space")

    def test_preserves_shape(self):
        img = np.random.default_rng(0).uniform(0, 1, size=(6, 5, 3))
        out = to_log_space(img, "V-Log")
        self.assertEqual(out.shape, img.shape)

    def test_middle_gray_encodes_to_documented_v_log_value(self):
        # Panasonic V-Log spec: 18% middle gray in a matching gamut encodes
        # to roughly 0.42-0.46 (matches core/log_pipeline.py's docstring
        # caveat that this isn't independently re-derived, just uses
        # colour-science's own curve definitions).
        img = np.full((2, 2, 3), 0.18)
        out = to_log_space(img, "V-Log")
        self.assertTrue(np.all((out > 0.3) & (out < 0.6)))

    def test_all_log_spaces_resolve_without_error(self):
        img = np.full((2, 2, 3), 0.18)
        for name in LOG_SPACES:
            with self.subTest(log_space=name):
                out = to_log_space(img, name)
                self.assertEqual(out.shape, img.shape)
                self.assertTrue(np.all(np.isfinite(out)))


class TestToHdrSpace(unittest.TestCase):
    def test_unknown_hdr_space_raises(self):
        img = np.full((4, 4, 3), 0.18)
        with self.assertRaises(ValueError):
            to_hdr_space(img, "not-a-real-hdr-space")

    def test_non_positive_peak_nits_raises(self):
        img = np.full((4, 4, 3), 0.18)
        with self.assertRaises(ValueError):
            to_hdr_space(img, "PQ", peak_nits=0.0)
        with self.assertRaises(ValueError):
            to_hdr_space(img, "PQ", peak_nits=-100.0)

    def test_preserves_shape(self):
        img = np.random.default_rng(0).uniform(0, 1, size=(6, 5, 3))
        for name in HDR_SPACES:
            with self.subTest(hdr_space=name):
                out = to_hdr_space(img, name)
                self.assertEqual(out.shape, img.shape)

    def test_all_hdr_spaces_resolve_without_error(self):
        img = np.full((2, 2, 3), 0.18)
        for name in HDR_SPACES:
            with self.subTest(hdr_space=name):
                out = to_hdr_space(img, name)
                self.assertTrue(np.all(np.isfinite(out)))

    def test_reference_white_maps_near_peak_for_pq(self):
        # linear 1.0(기준 화이트) * peak_nits=10000이면 PQ 시스템피크와
        # peak_nits가 일치하므로 코드값이 1.0 근처여야 한다.
        img = np.full((2, 2, 3), 1.0)
        out = to_hdr_space(img, "PQ", peak_nits=10000.0)
        self.assertTrue(np.all(out > 0.99))

    def test_pq_output_scales_with_peak_nits(self):
        img = np.full((2, 2, 3), 0.18)
        low = to_hdr_space(img, "PQ", peak_nits=500.0)
        high = to_hdr_space(img, "PQ", peak_nits=4000.0)
        self.assertTrue(np.all(high > low))

    def test_hlg_output_changes_with_peak_nits(self):
        # HLG도 L_W=peak_nits를 그대로 받아쓰므로(처음 가정과 달리 절대
        # 기준점이 필요 없지 않음 - to_hdr_space() docstring 참고) peak_nits
        # 를 바꾸면 같은 입력이라도 출력이 달라져야 한다.
        img = np.full((2, 2, 3), 0.18)
        a = to_hdr_space(img, "HLG", peak_nits=500.0)
        b = to_hdr_space(img, "HLG", peak_nits=1000.0)
        self.assertFalse(np.allclose(a, b))

    def test_brighter_input_gives_higher_pq_code_value(self):
        dark = np.full((2, 2, 3), 0.05)
        bright = np.full((2, 2, 3), 0.5)
        out_dark = to_hdr_space(dark, "PQ")
        out_bright = to_hdr_space(bright, "PQ")
        self.assertTrue(np.all(out_bright > out_dark))


class TestApplyCubeLut(unittest.TestCase):
    def test_identity_lut_roundtrips_values(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "identity.cube")
            with open(path, "w") as f:
                f.write(_IDENTITY_CUBE)
            img = np.array([[[0.2, 0.5, 0.8]]])
            out = apply_cube_lut(img, path)
            np.testing.assert_allclose(out, img, atol=1e-6)


class TestTo16BitBgr(unittest.TestCase):
    def test_dtype_and_channel_order(self):
        img = np.zeros((2, 2, 3))
        img[0, 0] = [1.0, 0.0, 0.0]  # pure red in RGB
        out = to_16bit_bgr(img)
        self.assertEqual(out.dtype, np.uint16)
        # BGR order: red channel should land in index 2, not 0
        self.assertEqual(out[0, 0, 2], 65535)
        self.assertEqual(out[0, 0, 0], 0)

    def test_out_of_range_values_are_clipped(self):
        img = np.array([[[-0.5, 1.5, 0.5]]])  # RGB: R=-0.5, G=1.5, B=0.5
        out = to_16bit_bgr(img)
        self.assertEqual(out[0, 0, 2], 0)      # R=-0.5 -> clipped to 0 (index 2 in BGR)
        self.assertEqual(out[0, 0, 1], 65535)  # G=1.5 -> clipped to 1.0 (index 1 in BGR)


class TestWriteExr(unittest.TestCase):
    def test_round_trips_float_values(self):
        import OpenEXR
        img = np.array([[[0.18, 0.5, 1.4]]], dtype=np.float64)  # 1.4: Log/HDR라 1.0 넘는 값도 그대로
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "out.exr")
            write_exr(img, path)
            self.assertTrue(os.path.exists(path))
            readback = OpenEXR.File(path).channels()["RGB"].pixels
            np.testing.assert_allclose(readback, img, atol=1e-5)

    def test_unknown_compression_raises(self):
        img = np.zeros((2, 2, 3))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "out.exr")
            with self.assertRaises(ValueError):
                write_exr(img, path, compression="not-a-real-codec")


if __name__ == "__main__":
    unittest.main()
