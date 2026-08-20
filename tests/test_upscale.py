import unittest
from unittest.mock import patch

import numpy as np

from core.upscale import (
    UPSCALE_SCALES, UPSCALE_ENGINES, _tile_bounds, _tile_process, upscale,
)


class TestTileBounds(unittest.TestCase):
    def test_covers_whole_image_exactly_once_in_core_region(self):
        # in_x0:in_x1/in_y0:in_y1(패딩 뺀 "핵심" 영역)는 타일끼리 겹치지
        # 않고 이미지 전체를 정확히 한 번씩만 덮어야 한다.
        width, height, tile_size, tile_pad = 100, 70, 32, 5
        counted = np.zeros((height, width), dtype=np.int32)
        for b in _tile_bounds(width, height, tile_size, tile_pad):
            counted[b["in_y0"]:b["in_y1"], b["in_x0"]:b["in_x1"]] += 1
        self.assertTrue(np.all(counted == 1))

    def test_image_smaller_than_tile_size_yields_single_tile(self):
        tiles = list(_tile_bounds(width=20, height=15, tile_size=64, tile_pad=8))
        self.assertEqual(len(tiles), 1)
        b = tiles[0]
        self.assertEqual((b["in_x0"], b["in_y0"], b["in_x1"], b["in_y1"]), (0, 0, 20, 15))

    def test_padding_clamped_at_image_edges(self):
        tiles = list(_tile_bounds(width=32, height=32, tile_size=32, tile_pad=10))
        b = tiles[0]
        self.assertEqual(b["pad_x0"], 0)
        self.assertEqual(b["pad_y0"], 0)
        self.assertEqual(b["pad_x1"], 32)
        self.assertEqual(b["pad_y1"], 32)


class TestTileProcess(unittest.TestCase):
    def test_identity_infer_reconstructs_input_at_scale_1(self):
        rng = np.random.default_rng(0)
        img = rng.uniform(0, 1, size=(3, 50, 70)).astype(np.float32)
        out = _tile_process(img, scale=1, tile_size=16, tile_pad=4, infer_fn=lambda t: t)
        np.testing.assert_allclose(out, img, atol=1e-6)

    def test_scale_2_upscale_via_repeat_matches_full_image_repeat(self):
        rng = np.random.default_rng(1)
        img = rng.uniform(0, 1, size=(3, 40, 60)).astype(np.float32)

        def repeat_2x(tile):
            return np.repeat(np.repeat(tile, 2, axis=1), 2, axis=2)

        out = _tile_process(img, scale=2, tile_size=15, tile_pad=3, infer_fn=repeat_2x)
        expected = repeat_2x(img)
        np.testing.assert_allclose(out, expected, atol=1e-6)

    def test_output_shape_matches_scale(self):
        img = np.zeros((3, 33, 27), dtype=np.float32)
        out = _tile_process(img, scale=4, tile_size=10, tile_pad=2,
                             infer_fn=lambda t: np.repeat(np.repeat(t, 4, axis=1), 4, axis=2))
        self.assertEqual(out.shape, (3, 33 * 4, 27 * 4))


class TestUpscaleValidation(unittest.TestCase):
    def test_unknown_scale_raises_before_any_model_load(self):
        img = np.zeros((8, 8, 3), dtype=np.uint8)
        with self.assertRaises(ValueError):
            upscale(img, scale=3, engine="onnx")

    def test_unknown_engine_raises_before_any_model_load(self):
        img = np.zeros((8, 8, 3), dtype=np.uint8)
        with self.assertRaises(ValueError):
            upscale(img, scale=4, engine="not-a-real-engine")

    def test_supported_scales_and_engines(self):
        self.assertEqual(UPSCALE_SCALES, [2, 4])
        self.assertEqual(set(UPSCALE_ENGINES), {"pytorch", "onnx"})


class TestUpscaleWithMockedEngine(unittest.TestCase):
    """실제 가중치 다운로드/추론 없이 upscale()의 배관(파이프라인 연결)만
    검증 - tests/CLAUDE.md 컨벤션대로 무거운 모델 계층은 모킹한다."""

    @patch("core.upscale.build_pytorch_model")
    def test_pytorch_engine_calls_model_and_preserves_scale_shape(self, mock_build):
        import torch

        class _FakeIdentityScale4(torch.nn.Module):
            def forward(self, x):
                return torch.nn.functional.interpolate(x, scale_factor=4, mode="nearest")

        mock_build.return_value = _FakeIdentityScale4()
        img = np.random.default_rng(0).integers(0, 255, (20, 24, 3), dtype=np.uint8)
        out = upscale(img, scale=4, engine="pytorch", tile_size=10, tile_pad=2)
        self.assertEqual(out.shape, (80, 96, 3))
        self.assertEqual(out.dtype, np.uint8)
        mock_build.assert_called_once_with(4)


if __name__ == "__main__":
    unittest.main()
