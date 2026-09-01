import json
import os
import struct
import tempfile
import unittest

import numpy as np

from core.dcp_export import (
    TAG_CALIBRATION_ILLUMINANT_1, TAG_COLOR_MATRIX_1, TAG_FORWARD_MATRIX_1,
    TAG_PROFILE_EMBED_POLICY, TAG_PROFILE_NAME, TAG_UNIQUE_CAMERA_MODEL,
    read_dcp, write_dcp,
)

_MATRIX = np.array([
    [0.7123, -0.1234, 0.0456],
    [-0.3456, 1.2345, 0.0789],
    [0.0123, -0.2345, 0.8901],
])

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SHIPPED_DCP = os.path.join(_REPO_ROOT, "hybrid_engine", "assets", "profiles",
                            "hasselblad_x2dii_chart.dcp")
_REPORT_JSON = os.path.join(_REPO_ROOT, "datasets", "hasselblad", "contributed",
                            "kmichels-x2dii-2026-07",
                            "camera_native_matrix_report.json")

# XYZ of D50 (CIE 1931 2도 관측자), colour.xy_to_XYZ(D50_xy)와 동일한 값.
# colour-science import 없이 쓰려고 상수로 박아둔다(이 테스트는 RAW 디코드도
# colour도 필요 없는 순수 파일 읽기 테스트여야 하므로).
_XYZ_D50 = np.array([0.9642956764295677, 1.0, 0.8251046025104605])


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

    def test_profile_embed_policy_defaults_to_allow_copying(self):
        # dcpTool로 컴파일해서 실제 Lightroom 동작 확인된 파일
        # (HNCS_X2DII_Chart_Colorimetric_v4_Adobe_ID.dcp)에 항상 들어있던
        # 태그 - 값 0 = "Allow Copying". 정정(2026-08-31) 참조.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.dcp")
            write_dcp(path, camera_model="Test Camera 1", profile_name="Test Profile",
                       color_matrix_1=_MATRIX, calibration_illuminant_1=21)
            tags = read_dcp(path)
            self.assertEqual(tags[TAG_PROFILE_EMBED_POLICY], 0)

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

    def test_header_uses_dcp_magic_not_standard_tiff_magic(self):
        # 정정(2026-08-31): 표준 TIFF 매직(42)으로 썼던 게 Lightroom이
        # 프로필을 계속 못 읽던 원인 중 하나였다 - dcpTool로 컴파일해서
        # 실제 동작 확인된 파일의 헤더가 0x4352("IIRC")임을 직접 까서
        # 확인했다. exiftool 구조 검증은 이 차이를 못 잡는다(매직을 모르는
        # 파일도 `Validate: OK`를 낸다) - 그래서 이 테스트는 raw 바이트를
        # 직접 본다.
        with tempfile.TemporaryDirectory() as tmp:
            with open(self._write_sample(tmp), "rb") as f:
                header = f.read(8)
        byte_order, magic, first_ifd = struct.unpack("<2sHI", header)
        self.assertEqual(byte_order, b"II")
        self.assertEqual(magic, 0x4352)
        self.assertNotEqual(magic, 42)
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
        type_sizes = {2: 1, 3: 2, 4: 4, 10: 8}
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


class TestRowVsColumnVectorConvention(unittest.TestCase):
    """`ColorMatrix1`에 넣을 값을 만들 때 전치를 빠뜨리는 버그를 막는 회귀
    테스트.

    실제로 발생한 버그다: `raw_baseline.fit_color_matrix()`는 **행벡터**
    규약으로 피팅하는데(`xyz_row ≈ native_row @ M`) DNG의 `ColorMatrix1`은
    **열벡터** 규약(`native_col = CM1 @ xyz_col`)이라 `CM1 = inv(M).T`가
    맞다. 그런데 설계 스펙과 계획서가 둘 다 "역행렬"이라고만 써서
    `np.linalg.inv(M)`가 그대로 파일에 들어갔고, exiftool 구조 검증과 수치
    라운드트립을 전부 통과하는 바람에 5번의 태스크 리뷰를 모두 빠져나갔다.
    버그가 `write_dcp()` 안이 아니라 **호출부**에 있었기 때문이다 - 그래서
    아래 테스트들은 write/read 라운드트립만 보지 않고, 실제로 커밋된
    산출물(`.dcp` + 리포트 JSON)의 물리적 정합성까지 검사한다."""

    def test_inverse_transpose_of_a_row_fit_round_trips(self):
        # 행벡터 규약으로 피팅한 M에서 CM1을 만드는 정석 경로. 이 테스트
        # 자체는 write_dcp()의 라운드트립만 잠그고(버그는 호출부에 있었으니
        # 이것만으로는 못 잡는다) 규약 유도를 코드로 문서화한다.
        from hybrid_engine.core.raw_baseline import fit_color_matrix

        rng = np.random.default_rng(11)
        known_cam_to_xyz = np.array([
            [2.3334, 0.8413, 0.0637],
            [0.2822, 1.2220, -0.2647],
            [0.2489, -0.2915, 2.8022],
        ])
        sources = [rng.uniform(0.02, 0.9, size=(24, 3)) for _ in range(3)]
        targets = [s @ known_cam_to_xyz for s in sources]
        fitted = fit_color_matrix(sources, targets)
        np.testing.assert_allclose(fitted, known_cam_to_xyz, atol=1e-9)

        expected = np.linalg.inv(fitted).T
        # 열벡터 규약을 만족하는지 직접 확인: native_col = CM1 @ xyz_col
        native_col = sources[0][0].reshape(3, 1)
        xyz_col = (sources[0][0] @ fitted).reshape(3, 1)
        np.testing.assert_allclose(expected @ xyz_col, native_col, atol=1e-9)
        # 전치를 빼면 그 규약을 만족하지 못한다 - 즉 이 구분은 실질적이다
        self.assertFalse(np.allclose(np.linalg.inv(fitted) @ xyz_col,
                                      native_col, atol=1e-6))

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.dcp")
            write_dcp(path, camera_model="C", profile_name="P",
                       color_matrix_1=expected, calibration_illuminant_1=23)
            recovered = read_dcp(path)[TAG_COLOR_MATRIX_1].reshape(3, 3)
        np.testing.assert_allclose(recovered, expected, atol=1e-6)


class TestShippedProfileMatchesReport(unittest.TestCase):
    """커밋된 `.dcp`가 커밋된 리포트 JSON에서 올바른 변환으로 생성됐는지
    검사한다. RAW 디코드 없이 이미 커밋된 두 파일만 읽으므로 일반 스위트에서
    돌아간다. 누군가 전치를 빼고 프로필을 재생성하면 여기서 깨진다.

    **정정(2026-09-01)**: 사용자 승인으로 매트릭스를 무채색 6패치 가중치
    낮춘(유채색 4x) 최소자승으로 재피팅해서 배포(`tools/refit_dcp_weighted_chroma.py`,
    9장 LOO 기준 -4.9% 확인 - `hybrid_engine/EVALUATION.md` 참고).

    **추가 정정(2026-09-01, 같은 날)**: 그 위에 Huber IRLS(무채색-4x에서
    시작, `tools/refit_dcp_irls_final.py`)로 한 번 더 재피팅해서 배포 -
    9장 LOO 기준 -8.8%(2.8588->2.6078, `_weighted` 단독 -4.9%보다 더 낮음).
    리포트 JSON엔 균등가중 필드(`chart_matrix_in_sample`/`dcp_color_matrix_1`,
    n=10 - B_31334 유실로 지금은 재현 불가)/유채색-4x 필드(`_weighted`)/
    IRLS 필드(`_irls`) 셋 다 있다 - 실제 배포된 `.dcp`는 `_irls` 기준이라
    이 테스트도 `_irls`를 본다.

    **추가 정정(2026-09-01, 같은 날)**: 패치별 잔차를 뜯어보니 patch
    17(cyan)만 9장 전부에서 평균 ΔE00=7.166(표준편차 0.977)로 다른 패치
    (다음 최악 3.695)보다 압도적으로 나빴다. cyan의 IRLS 초기가중치를
    4.0에서 2.0으로 낮춰 재수렴시킨 매트릭스(`tools/refit_dcp_irls_cyan_init.py`)로
    배포 - 9장 LOO 기준 -0.52%(2.6078->2.5942, 부트스트랩 CI 없음, 단조성으로
    신호 판정). 실제 배포된 `.dcp`는 이제 `_irls_cyan_init` 기준이라 이
    테스트도 `_irls_cyan_init`을 본다. `_irls`(무채색-4x 단독, -8.8%)와
    원래 균등가중 필드는 기록용으로 보존."""

    @classmethod
    def setUpClass(cls):
        if not (os.path.exists(_SHIPPED_DCP) and os.path.exists(_REPORT_JSON)):
            raise unittest.SkipTest("커밋된 .dcp/리포트 JSON이 없음")
        with open(_REPORT_JSON, encoding="utf-8") as f:
            cls.report = json.load(f)
        cls.tags = read_dcp(_SHIPPED_DCP)
        cls.cm1 = cls.tags[TAG_COLOR_MATRIX_1].reshape(3, 3)
        cls.chart_m = np.array(cls.report["chart_matrix_in_sample_irls_cyan_init"], dtype=np.float64)

    def test_color_matrix_1_is_inverse_transpose_not_plain_inverse(self):
        expected = np.linalg.inv(self.chart_m).T
        np.testing.assert_allclose(self.cm1, expected, atol=1e-6)
        # 전치 없는 역행렬이었다면(원래 버그) 통과하지 않아야 한다
        self.assertFalse(np.allclose(self.cm1, np.linalg.inv(self.chart_m),
                                      atol=1e-6))

    def test_report_dcp_color_matrix_field_matches_the_file(self):
        np.testing.assert_allclose(
            self.cm1,
            np.array(self.report["dcp_color_matrix_1_irls_cyan_init"], dtype=np.float64),
            atol=1e-6)

    def test_calibration_illuminant_is_d50_matching_the_fit_reference_space(self):
        # 참조값이 XYZ(D50)으로 색순응된 뒤 피팅되므로 매트릭스는 구성상
        # D50 기준이다. 23 = D50.
        self.assertEqual(self.tags[TAG_CALIBRATION_ILLUMINANT_1], 23)
        self.assertEqual(self.report["calibration_illuminant"]["chosen_enum"], 23)

    def test_color_matrix_1_maps_d50_white_to_the_measured_native_neutral(self):
        """물리적 정합성: `ColorMatrix1`은 XYZ(D50) -> 카메라 네이티브이므로
        D50 백색점을 넣으면 차트 무채색 패치에서 실측한 네이티브 중립색과
        비례해야 한다. 전치를 빠뜨리면 R이 4~5배 어긋나면서 여기서 깨진다 -
        구조 검증이나 라운드트립으로는 절대 잡히지 않던 부분."""
        measured = np.array(self.report["measured_native_neutral_g_normalized"],
                            dtype=np.float64)
        predicted = self.cm1 @ _XYZ_D50
        predicted = predicted / predicted[1]   # 실측값과 같이 G=1 정규화
        # 관대한 허용치(5%) - 차트 피팅 매트릭스가 무채색 패치를 정확히
        # 재현할 의무는 없다(24패치 전체 최소자승이므로). 전치 오류가 만드는
        # 4~5배짜리 어긋남과는 자릿수가 다르다.
        np.testing.assert_allclose(predicted, measured, rtol=0.05)

    def test_plain_inverse_would_fail_the_physical_invariant(self):
        # 위 테스트가 진짜로 버그를 잡는지 확인 - 버그 버전 매트릭스는
        # 같은 검사를 통과하지 못해야 한다.
        measured = np.array(self.report["measured_native_neutral_g_normalized"],
                            dtype=np.float64)
        buggy = np.linalg.inv(self.chart_m) @ _XYZ_D50
        buggy = buggy / buggy[1]
        with self.assertRaises(AssertionError):
            np.testing.assert_allclose(buggy, measured, rtol=0.05)


if __name__ == "__main__":
    unittest.main()
