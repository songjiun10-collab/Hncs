"""`tools/fit_brand_native_matrix_for_icc.py`의 순수 부분만 검증 - RAW
디코드는 CI에 데이터가 없어서(tests/CLAUDE.md) 제외."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.fit_brand_native_matrix_for_icc import fit_color_matrix, BRAND_DESCRIPTIONS
from core.icc_export import srgb_linear_to_xyz_d50_matrix


class TestFitColorMatrix(unittest.TestCase):
    def test_recovers_known_linear_relationship(self):
        rng = np.random.RandomState(0)
        true_matrix = np.array([
            [1.2, 0.1, -0.05],
            [0.05, 0.9, 0.02],
            [-0.02, 0.08, 1.1],
        ])
        sources = [rng.rand(50, 3) for _ in range(5)]
        targets = [s @ true_matrix for s in sources]
        fitted = fit_color_matrix(sources, targets, ridge=1e-8)
        np.testing.assert_allclose(fitted, true_matrix, atol=1e-3)


class TestSrgbLinearToXyzD50Matrix(unittest.TestCase):
    def test_white_maps_to_d50(self):
        """(1,1,1) linear RGB(D65 백색점) -> Bradford 적응 후 D50 근처."""
        m = srgb_linear_to_xyz_d50_matrix()
        xyz = np.array([1.0, 1.0, 1.0]) @ m
        np.testing.assert_allclose(xyz, [0.9642, 1.0, 0.8249], atol=0.01)


class TestBrandDescriptions(unittest.TestCase):
    def test_all_configured_brands_have_icc_description(self):
        from tools.fit_brand_matrix_chroma_pipeline import BRAND_CONFIG
        for brand in BRAND_CONFIG:
            self.assertIn(brand, BRAND_DESCRIPTIONS, f"{brand}: ICC description 없음")


if __name__ == "__main__":
    unittest.main()
