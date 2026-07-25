import os
import struct
import tempfile
import unittest

import numpy as np

from core.dcp_export import (
    TAG_CALIBRATION_ILLUMINANT_1, TAG_COLOR_MATRIX_1, TAG_FORWARD_MATRIX_1,
    TAG_PROFILE_NAME, TAG_UNIQUE_CAMERA_MODEL, read_dcp, write_dcp,
)

_MATRIX = np.array([
    [0.7123, -0.1234, 0.0456],
    [-0.3456, 1.2345, 0.0789],
    [0.0123, -0.2345, 0.8901],
])


class TestWriteReadRoundTrip(unittest.TestCase):
    def test_round_trip_recovers_all_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.dcp")
            write_dcp(path, camera_model="Test Camera 1", profile_name="Test Profile",
                       color_matrix_1=_MATRIX, calibration_illuminant_1=21)

            tags = read_dcp(path)

            self.assertEqual(tags[TAG_UNIQUE_CAMERA_MODEL], "Test Camera 1")
            self.assertEqual(tags[TAG_PROFILE_NAME], "Test Profile")
            self.assertEqual(tags[TAG_CALIBRATION_ILLUMINANT_1], 21)
            # SRATIONAL은 분모 1000000로 양자화되므로 그 반올림 오차 내에서 일치
            np.testing.assert_allclose(tags[TAG_COLOR_MATRIX_1],
                                        _MATRIX.reshape(9), atol=1e-6)

    def test_forward_matrix_omitted_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.dcp")
            write_dcp(path, camera_model="Test Camera 1", profile_name="Test Profile",
                       color_matrix_1=_MATRIX, calibration_illuminant_1=21)
            tags = read_dcp(path)
            self.assertNotIn(TAG_FORWARD_MATRIX_1, tags)

    def test_forward_matrix_included_when_given(self):
        forward = _MATRIX * 0.5
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.dcp")
            write_dcp(path, camera_model="Test Camera 1", profile_name="Test Profile",
                       color_matrix_1=_MATRIX, calibration_illuminant_1=21,
                       forward_matrix_1=forward)
            tags = read_dcp(path)
            np.testing.assert_allclose(tags[TAG_FORWARD_MATRIX_1],
                                        forward.reshape(9), atol=1e-6)

    def test_negative_values_survive_round_trip(self):
        # SRATIONAL은 부호 있는 타입 - 음수 계수(색매트릭스에 흔함)가
        # 부호 없는 타입으로 잘못 패킹되면 여기서 깨진다.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.dcp")
            write_dcp(path, camera_model="C", profile_name="P",
                       color_matrix_1=_MATRIX, calibration_illuminant_1=23)
            recovered = read_dcp(path)[TAG_COLOR_MATRIX_1]
        self.assertLess(recovered[1], 0)
        self.assertLess(recovered[3], 0)
        np.testing.assert_allclose(recovered[1], _MATRIX[0, 1], atol=1e-6)


class TestTiffStructure(unittest.TestCase):
    def _write_sample(self, tmp):
        path = os.path.join(tmp, "test.dcp")
        write_dcp(path, camera_model="Test Camera 1", profile_name="Test Profile",
                   color_matrix_1=_MATRIX, calibration_illuminant_1=21)
        return path

    def test_header_is_valid_little_endian_tiff(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(self._write_sample(tmp), "rb") as f:
                header = f.read(8)
        byte_order, magic, first_ifd = struct.unpack("<2sHI", header)
        self.assertEqual(byte_order, b"II")
        self.assertEqual(magic, 42)
        self.assertEqual(first_ifd, 8)

    def test_ifd_entries_sorted_by_tag(self):
        # TIFF 스펙은 IFD 엔트리를 태그 오름차순으로 요구한다 - 어기면
        # 엄격한 리더가 거부할 수 있다.
        with tempfile.TemporaryDirectory() as tmp:
            with open(self._write_sample(tmp), "rb") as f:
                data = f.read()
        (n_entries,) = struct.unpack_from("<H", data, 8)
        tags = [struct.unpack_from("<H", data, 8 + 2 + 12 * i)[0]
                for i in range(n_entries)]
        self.assertEqual(tags, sorted(tags))

    def test_all_offsets_within_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(self._write_sample(tmp), "rb") as f:
                data = f.read()
        (n_entries,) = struct.unpack_from("<H", data, 8)
        type_sizes = {2: 1, 3: 2, 10: 8}
        for i in range(n_entries):
            off = 8 + 2 + 12 * i
            _tag, typ, count = struct.unpack_from("<HHI", data, off)
            size = type_sizes[typ] * count
            if size > 4:
                (payload_offset,) = struct.unpack_from("<I", data, off + 8)
                self.assertLessEqual(payload_offset + size, len(data))

    def test_next_ifd_offset_is_zero(self):
        # 단일 IFD 파일이므로 다음 IFD 오프셋은 0(체인 끝)이어야 한다.
        with tempfile.TemporaryDirectory() as tmp:
            with open(self._write_sample(tmp), "rb") as f:
                data = f.read()
        (n_entries,) = struct.unpack_from("<H", data, 8)
        (next_ifd,) = struct.unpack_from("<I", data, 8 + 2 + 12 * n_entries)
        self.assertEqual(next_ifd, 0)


if __name__ == "__main__":
    unittest.main()
