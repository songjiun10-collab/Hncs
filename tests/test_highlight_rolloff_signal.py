import unittest
from unittest.mock import patch

import numpy as np

from tools.highlight_rolloff_signal import rolloff_stats


class TestRolloffStats(unittest.TestCase):
    def _fake_npz(self, l_hist):
        return {"l_hist": np.array(l_hist, dtype=np.float64)}

    def test_hard_clip_has_narrow_rolloff_and_high_clip_frac(self):
        l_hist = np.zeros(256)
        l_hist[:200] = 1.0
        l_hist[255] = 1000.0  # 대부분 픽셀이 순백에 몰림 (급격한 클리핑)
        with patch("numpy.load", return_value=self._fake_npz(l_hist)):
            st = rolloff_stats("fake_brand")
        self.assertLess(st["rolloff_width"], 5)
        self.assertGreater(st["clip_frac"], 0.8)

    def test_gradual_rolloff_has_wide_spread(self):
        l_hist = np.ones(256)  # 균등분포 - 완만한 확산
        with patch("numpy.load", return_value=self._fake_npz(l_hist)):
            st = rolloff_stats("fake_brand")
        self.assertGreater(st["rolloff_width"], 20)


if __name__ == "__main__":
    unittest.main()
