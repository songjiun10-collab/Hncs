"""`tools/dcp_export_huesatmap_experimental.py`(core/dcp_export.py 격리
사본 + HueSatMap 태그) 라운드트립 검증. RAW 디코드 없이 순수 구조
테스트라 일반 스위트에서 돈다."""
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.dcp_export_huesatmap_experimental import (
    write_dcp, read_dcp,
    TAG_COLOR_MATRIX_1, TAG_PROFILE_HUE_SAT_MAP_DIMS,
    TAG_PROFILE_HUE_SAT_MAP_DATA_1, TAG_PROFILE_HUE_SAT_MAP_ENCODING,
)


class TestHueSatMapRoundTrip(unittest.TestCase):
    def test_hue_sat_map_fields_round_trip(self):
        cm = np.eye(3) * 0.9
        hd, sd, vd = 8, 1, 1
        data = np.zeros((hd, sd, vd, 3))
        data[:, 0, 0, 0] = np.linspace(-5, 5, hd)
        data[:, 0, 0, 1] = 1.0
        data[:, 0, 0, 2] = 1.0

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.dcp")
            write_dcp(path, camera_model="C", profile_name="P", color_matrix_1=cm,
                      calibration_illuminant_1=23, hue_sat_map_dims=(hd, sd, vd),
                      hue_sat_map_data=data, hue_sat_map_encoding=1)
            tags = read_dcp(path)

        np.testing.assert_allclose(tags[TAG_COLOR_MATRIX_1].reshape(3, 3), cm, atol=1e-6)
        np.testing.assert_array_equal(tags[TAG_PROFILE_HUE_SAT_MAP_DIMS], [hd, sd, vd])
        self.assertEqual(tags[TAG_PROFILE_HUE_SAT_MAP_ENCODING], 1)
        recovered = tags[TAG_PROFILE_HUE_SAT_MAP_DATA_1].reshape(hd, sd, vd, 3)
        np.testing.assert_allclose(recovered, data, atol=1e-4)

    def test_hue_sat_map_omitted_when_not_passed(self):
        """기존 필드만 쓰는 호출(HueSatMap 인자 생략)은 그 태그들이 아예
        안 들어가야 한다 - core/dcp_export.py의 기존 동작을 안 바꿨는지
        확인하는 회귀 테스트."""
        cm = np.eye(3) * 0.9
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.dcp")
            write_dcp(path, camera_model="C", profile_name="P", color_matrix_1=cm,
                      calibration_illuminant_1=23)
            tags = read_dcp(path)
        self.assertNotIn(TAG_PROFILE_HUE_SAT_MAP_DIMS, tags)
        self.assertNotIn(TAG_PROFILE_HUE_SAT_MAP_DATA_1, tags)
        self.assertNotIn(TAG_PROFILE_HUE_SAT_MAP_ENCODING, tags)

    def test_mismatched_data_length_raises(self):
        cm = np.eye(3) * 0.9
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.dcp")
            with self.assertRaises(ValueError):
                write_dcp(path, camera_model="C", profile_name="P", color_matrix_1=cm,
                          calibration_illuminant_1=23, hue_sat_map_dims=(8, 1, 1),
                          hue_sat_map_data=np.zeros(10))  # 8*1*1*3=24와 안 맞음


if __name__ == "__main__":
    unittest.main()
