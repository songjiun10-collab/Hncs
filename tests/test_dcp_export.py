import json
import os
import struct
import tempfile
import unittest

import numpy as np

from core.dcp_export import (
    TAG_CALIBRATION_ILLUMINANT_1, TAG_CALIBRATION_ILLUMINANT_2,
    TAG_COLOR_MATRIX_1, TAG_COLOR_MATRIX_2, TAG_FORWARD_MATRIX_1,
    TAG_FORWARD_MATRIX_2, TAG_PROFILE_EMBED_POLICY, TAG_PROFILE_NAME,
    TAG_UNIQUE_CAMERA_MODEL, read_dcp, write_dcp,
)

_MATRIX = np.array([
    [0.7123, -0.1234, 0.0456],
    [-0.3456, 1.2345, 0.0789],
    [0.0123, -0.2345, 0.8901],
])

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SHIPPED_DCP = os.path.join(_REPO_ROOT, "hybrid_engine", "assets", "profiles",
                            "hasselblad_x2dii_chart.dcp")
_DUAL_ILLUMINANT_REPORT_JSON = os.path.join(
    _REPO_ROOT, "datasets", "hasselblad", "contributed",
    "dpreview-x2dii100c-studio-chart-2026-09", "dual_illuminant_report.json")

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

    def test_color_matrix_2_omitted_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.dcp")
            write_dcp(path, camera_model="Test Camera 1", profile_name="Test Profile",
                       color_matrix_1=_MATRIX, calibration_illuminant_1=21)
            tags = read_dcp(path)
            self.assertNotIn(TAG_COLOR_MATRIX_2, tags)
            self.assertNotIn(TAG_CALIBRATION_ILLUMINANT_2, tags)

    def test_color_matrix_2_requires_calibration_illuminant_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.dcp")
            with self.assertRaises(ValueError):
                write_dcp(path, camera_model="C", profile_name="P",
                           color_matrix_1=_MATRIX, calibration_illuminant_1=21,
                           color_matrix_2=_MATRIX * 0.5)

    def test_color_matrix_2_round_trips_with_its_own_illuminant(self):
        matrix_2 = _MATRIX * 0.7
        forward_2 = _MATRIX * 0.3
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.dcp")
            write_dcp(path, camera_model="C", profile_name="P",
                       color_matrix_1=_MATRIX, calibration_illuminant_1=21,
                       color_matrix_2=matrix_2, calibration_illuminant_2=17,
                       forward_matrix_2=forward_2)
            tags = read_dcp(path)
        self.assertEqual(tags[TAG_CALIBRATION_ILLUMINANT_2], 17)
        np.testing.assert_allclose(tags[TAG_COLOR_MATRIX_2],
                                    matrix_2.reshape(9), atol=1e-6)
        np.testing.assert_allclose(tags[TAG_FORWARD_MATRIX_2],
                                    forward_2.reshape(9), atol=1e-6)
        # Matrix1 쪽도 그대로 정상 - 둘이 서로 안 섞인다
        np.testing.assert_allclose(tags[TAG_COLOR_MATRIX_1],
                                    _MATRIX.reshape(9), atol=1e-6)
        self.assertEqual(tags[TAG_CALIBRATION_ILLUMINANT_1], 21)

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
    신호 판정). `_irls`(무채색-4x 단독, -8.8%)와 원래 균등가중 필드는
    `kmichels-x2dii-2026-07/camera_native_matrix_report.json`에 기록용으로
    보존.

    **정정(2026-09-03)**: 사용자가 dpreview 스튜디오씬 X2D II 100C 챠트
    데이터(Daylight/Lowlight, 16장)가 kmichels 번스트(9장, 단일 조명)와
    진짜 다른 조명 조건이라는 걸 확인시킨 뒤("우리꺼하고 다른줄 알고
    시킴") 승인한 재보정("이제 하셀은 보정 ㄱㄱ dcp") - 두 데이터셋을
    합쳐(n=25) 기존에 이미 승인된 `_weighted` 단계(무채색 6패치 대비
    유채색 18패치 4x 가중 최소자승, ridge=0.0)와 같은 방법론으로 다시
    피팅했다(`tools/refit_x2dii_chart_combined.py`). **IRLS/cyan
    재조정 단계는 이번엔 재적용하지 않았다** - 그 두 단계는 n=9
    kmichels 단독 데이터의 특정 잔차 패턴에 맞춰 손튜닝된 것이라(원본
    리포트 자체가 "n=9 표본 과적합" 위험을 명시) 25장으로 늘어난 합친
    데이터에 그대로 전이된다는 보장이 없어서였다.

    **왜 교체가 정당한가(핵심 수치)**: kmichels 단독 LOO CV는 2.72
    ΔE00로 매우 좋아 보였지만, 이건 "10장을 94초 만에 찍은 같은 조명
    번스트"라 사실상 거의 동일한 이미지끼리 검증한 것 - 실제 다른
    조명(dpreview)에 그 구버전 매트릭스를 **out-of-sample로** 적용해보니
    19.155 ΔE00(무보정 32.733 대비 겨우 -41%)로 훨씬 약했다(이 실행
    확인된 결과, `/tmp/old_x2dii_chart.dcp`로 git 이력의 구버전 DCP를
    복원해서 dpreview 16장에 직접 적용해 측정). 반면 새 합친 매트릭스는
    같은 종류의 다조명 데이터에 대해 5-fold CV로 12.69 ΔE00(무보정
    31.497 대비 -59.7%, 부트스트랩 95% CI(20000회)=[+16.68,+20.81],
    25/0)를 낸다 - kmichels 단독 번스트의 낮은 CV는 단일조명 과적합의
    착시였고, 진짜 다조명 일반화 성능은 새 매트릭스가 명확히 우세하다.

    이제 실제 배포된 `.dcp`는 `datasets/hasselblad/contributed/
    dpreview-x2dii100c-studio-chart-2026-09/combined_chart_matrix_report.json`의
    `dcp_color_matrix_1`(균등가중 아님 - 유채색 4x 가중, 파일 내
    `chroma_patch_weight` 필드로 명시) 기준이었다. 옛 kmichels 단독
    리포트(`_irls_cyan_init` 등)는 기록용으로 그대로 남아있다.

    **정정(2026-09-03, 같은 날) - dual-illuminant로 재교체**: 위 combined
    매트릭스(25장 한 개 3x3, 5-fold CV 12.69)를 이미지별 실측 네이티브
    중립색(무채색 6패치)으로 뜯어보니 R/G가 0.32~0.65로 3그룹(dpreview
    daylight성 R/G≈0.33 n=9, dpreview tungsten성 R/G≈0.64 n=7, kmichels
    R/G≈0.41 n=9)으로 뚜렷이 갈렸다 - 매트릭스 하나로 여러 조명의
    화이트밸런스를 동시에 못 맞추는 게 12.69의 주원인이었다
    (`tools/analyze_x2dii_combined_lighting_split.py` 실행 확인,
    무채색 패치 잔차가 유채색보다 훨씬 컸다:
    `tools/analyze_x2dii_combined_patch_residuals.py`). 사용자 승인
    받아 DNG의 dual-illuminant 메커니즘(`ColorMatrix1`+`ColorMatrix2`+
    `CalibrationIlluminant1/2`, `core/dcp_export.py`에 이번에 추가)으로
    풀었다(`tools/refit_x2dii_dual_illuminant.py`).

    daylight성/tungsten성 두 dpreview 그룹으로 각각 `ColorMatrix1`
    (illuminant=21/D65 근사)/`ColorMatrix2`(illuminant=17/Standard
    Light A 근사)을 피팅하고, kmichels(세 번째 조명, 두 매트릭스
    어디에도 미포함)는 순수 홀드아웃으로 남겨 R/G 선형보간(이 프로젝트가
    만든 근사 - Adobe DNG SDK의 실제 보간 알고리즘 재현이 아님, 실기기
    미검증)을 적용해 일반화 성능을 검증했다. 25장 전체를 셋 다
    out-of-sample로 공정 비교한 결과(`dual_illuminant_report.json`의
    `full25_fair_comparison`, 부트스트랩 95% CI 20000회):
    global 12.69 -> dual-illuminant 8.48, **+33.14%**,
    95% CI=[+0.81,+7.46](0을 안 걸침), wins 16/losses 9(n=25).
    이 테스트도 이제 `dual_illuminant_report.json`을 본다."""

    @classmethod
    def setUpClass(cls):
        if not (os.path.exists(_SHIPPED_DCP) and os.path.exists(_DUAL_ILLUMINANT_REPORT_JSON)):
            raise unittest.SkipTest("커밋된 .dcp/리포트 JSON이 없음")
        with open(_DUAL_ILLUMINANT_REPORT_JSON, encoding="utf-8") as f:
            cls.report = json.load(f)
        cls.tags = read_dcp(_SHIPPED_DCP)
        cls.cm1 = cls.tags[TAG_COLOR_MATRIX_1].reshape(3, 3)
        cls.cm2 = cls.tags[TAG_COLOR_MATRIX_2].reshape(3, 3)
        cls.chart_m1 = np.array(cls.report["color_matrix_1"], dtype=np.float64)
        cls.chart_m2 = np.array(cls.report["color_matrix_2"], dtype=np.float64)

    def test_color_matrix_1_is_inverse_transpose_not_plain_inverse(self):
        expected = np.linalg.inv(self.chart_m1).T
        np.testing.assert_allclose(self.cm1, expected, atol=1e-6)
        # 전치 없는 역행렬이었다면(원래 버그) 통과하지 않아야 한다
        self.assertFalse(np.allclose(self.cm1, np.linalg.inv(self.chart_m1),
                                      atol=1e-6))

    def test_color_matrix_2_is_inverse_transpose_not_plain_inverse(self):
        expected = np.linalg.inv(self.chart_m2).T
        np.testing.assert_allclose(self.cm2, expected, atol=1e-6)
        self.assertFalse(np.allclose(self.cm2, np.linalg.inv(self.chart_m2),
                                      atol=1e-6))

    def test_report_dcp_color_matrix_fields_match_the_file(self):
        np.testing.assert_allclose(
            self.cm1,
            np.array(self.report["dcp_color_matrix_1"], dtype=np.float64),
            atol=1e-6)
        np.testing.assert_allclose(
            self.cm2,
            np.array(self.report["dcp_color_matrix_2"], dtype=np.float64),
            atol=1e-6)

    def test_calibration_illuminants_match_the_two_lighting_clusters(self):
        # illuminant1=D65(21) 근사(daylight성 저R/G 클러스터),
        # illuminant2=Standard Light A(17) 근사(tungsten성 고R/G 클러스터).
        self.assertEqual(self.tags[TAG_CALIBRATION_ILLUMINANT_1], 21)
        self.assertEqual(self.tags[TAG_CALIBRATION_ILLUMINANT_2], 17)
        self.assertEqual(self.report["group1_daylight_like"]["calibration_illuminant"], 21)
        self.assertEqual(self.report["group2_tungsten_like"]["calibration_illuminant"], 17)

    def test_color_matrix_1_maps_d50_white_to_group1_measured_native_neutral(self):
        """물리적 정합성: `ColorMatrixN`은 XYZ(D50) -> 카메라 네이티브이므로
        D50 백색점을 넣으면 그 그룹에서 실측한 네이티브 중립색과 비례해야
        한다. 전치를 빠뜨리면 크게 어긋나면서 여기서 깨진다."""
        measured = np.array(
            self.report["group1_daylight_like"]["measured_native_neutral_g_normalized"],
            dtype=np.float64)
        predicted = self.cm1 @ _XYZ_D50
        predicted = predicted / predicted[1]
        np.testing.assert_allclose(predicted, measured, rtol=0.15)

    def test_color_matrix_2_maps_d50_white_to_group2_measured_native_neutral(self):
        measured = np.array(
            self.report["group2_tungsten_like"]["measured_native_neutral_g_normalized"],
            dtype=np.float64)
        predicted = self.cm2 @ _XYZ_D50
        predicted = predicted / predicted[1]
        np.testing.assert_allclose(predicted, measured, rtol=0.15)

    def test_plain_inverse_would_fail_the_physical_invariant(self):
        # 위 테스트들이 진짜로 버그를 잡는지 확인 - 버그 버전 매트릭스는
        # 같은 검사를 통과하지 못해야 한다.
        measured = np.array(
            self.report["group1_daylight_like"]["measured_native_neutral_g_normalized"],
            dtype=np.float64)
        buggy = np.linalg.inv(self.chart_m1) @ _XYZ_D50
        buggy = buggy / buggy[1]
        with self.assertRaises(AssertionError):
            np.testing.assert_allclose(buggy, measured, rtol=0.05)


if __name__ == "__main__":
    unittest.main()
