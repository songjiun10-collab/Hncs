"""`tools/validate_chart_pipeline_on_external_camera.py`의 순수 부분만
검증 - RAW 디코드는 CI에 데이터가 없고, 이 외부 데이터셋은 애초에 이
저장소에 커밋되지도 않으므로(tests/CLAUDE.md) 제외."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.validate_chart_pipeline_on_external_camera import _mean_de, _rmse_xyz


class TestMeanDe(unittest.TestCase):
    def test_identical_samples_give_zero(self):
        from hybrid_engine.core import chart_baseline
        ref = chart_baseline.reference_patches_xyz_d50()
        self.assertAlmostEqual(_mean_de(ref, ref), 0.0, places=6)

    def test_different_samples_give_positive(self):
        from hybrid_engine.core import chart_baseline
        ref = chart_baseline.reference_patches_xyz_d50()
        shifted = ref * 1.5
        self.assertGreater(_mean_de(shifted, ref), 0.0)


class TestRmseXyz(unittest.TestCase):
    def test_identical_samples_give_zero(self):
        from hybrid_engine.core import chart_baseline
        ref = chart_baseline.reference_patches_xyz_d50()
        self.assertAlmostEqual(_rmse_xyz(ref, ref), 0.0, places=6)

    def test_known_offset_gives_exact_rmse(self):
        ref = np.zeros((4, 3))
        samples = np.full((4, 3), 2.0)
        # 모든 성분이 2만큼 어긋나 있으므로 RMSE는 정확히 2
        self.assertAlmostEqual(_rmse_xyz(samples, ref), 2.0, places=6)


if __name__ == "__main__":
    unittest.main()
