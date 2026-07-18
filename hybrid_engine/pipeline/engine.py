"""
core/의 개별 모듈(raw_baseline/color_matrix/normalizer/tone_core/color_core/
hue_core/lab2d_core/lab3d_core/spatial_core)을 하나의 파이프라인으로
조립하는 HybridCameraEngine.

**Phase 번호는 2026-07 raw 베이스라인 실측(EVALUATION.md 후속 실측 5)
이후 재정의했다** - 무보정 raw 디코드(ΔE 11.78)가 그때까지의
"캘리브레이션된" 파라메트릭 파이프라인(ΔE 14.85)보다 낫다는 게 드러나서,
전역 3x3 컬러 매트릭스를 새 Phase 0으로 앞에 놓고 그 위에서 톤/채도를
다시 학습하는 구조로 바꿨다(사용자 지시: 삭제하지 않고 재배치+재학습).

데이터 흐름: Linear RGB -> **Phase 0: raw_baseline(3x3 매트릭스, 색차트
없이 raw+jpeg 페어 최소자승으로 적합) + 카메라 색정제(camera_whitebalance
제공 시 color_matrix.py) + Gray World 정규화** -> LAB 분리 ->
**Phase 1: tone_core**(L, 또는 학습 LUT) -> **Phase 2: color_core**(a, b
채도) -> Phase 2.5: hue_core(a, b hue 회전, 학습 LUT이 있을 때만) ->
Phase 2.55: lab2d_core(a, b 결합 2D 잔차 LUT, 학습 LUT이 있을 때만) ->
Phase 2.6: lab3d_core(L, a, b 결합 3D 잔차 LUT, 학습 LUT이 있을 때만) ->
Phase 3: spatial_core(L 로컬 콘트라스트, use_spatial=True일 때만) ->
LAB 복원 -> Linear RGB

Phase 0의 raw_baseline_matrix는 profile의 "raw_baseline_matrix"에 3x3
중첩 리스트를 주면 적용되고(calibrate_profile.py --mode raw_baseline_pipeline
으로 생성), 없으면 완전히 bypass한다(V0.1과 동일하게 카메라 색정제+
Gray World만).

L채널 톤 단계는 두 모드가 있다:
  - 파라메트릭(기본): tone_core의 S-curve/shadow-lift/highlight-rolloff
  - 학습 LUT: profile의 "learned_tone_lut"에 npy 경로를 주면 raw+jpeg
    페어에서 픽셀 대응으로 직접 학습한 1D LUT을 대신 적용 -
    apply_hncs_learned가 파라메트릭 커브(RMSE 23.3)를 학습 LUT(15.4)으로
    이긴 것과 같은 원리를 hybrid_engine에 이식한 것
    (calibrate_profile.py --mode learned로 생성)

hue 보정 단계는 파라메트릭 모델 자체가 없다(V0.1엔 아예 없던 축) -
profile의 "learned_hue_lut"에 npy 경로를 주면 순환(circular) 1D LUT을
적용하고, 없으면 완전히 bypass한다(calibrate_profile.py --mode hue로 생성).

2D/3D 잔차 LUT도 파라메트릭 모델이 없다 - 톤/hue를 각각 독립적으로
고치는 1D LUT 두 개가 전부 개선폭 5% 미만에서 막힌 뒤(assets/luts/README.md)
"잔차가 채널별로 분해되지 않는다"는 가설의 다음 시도들. profile의
"learned_lab2d_lut"(npz, a/b만)/"learned_lab3d_lut"(npz, L/a/b 전부)에
경로를 주면 적용, 없으면 bypass(calibrate_profile.py --mode lab2d /
--mode lab3d로 생성). LUT 계열 네 실험 전부 표본 13장에서는 통하지
않는다고 결론(교차검증 기준 전부 음성) 난 뒤의 다음 시도가 Phase 3다
- 채널 재조합이 아니라 "이웃 픽셀을 보는" 근본적으로 다른 축.

Phase 3(공간 연산)는 spatial_core.apply_local_contrast로 L채널에 언샤프
마스크 방식 로컬 콘트라스트를 적용한다. use_spatial=False(기본)면 완전
bypass, True면 spatial_radius/spatial_amount/spatial_threshold 파라미터로
동작(calibrate_profile.py --mode spatial로 좌표하강 캘리브레이션 - 파라미터
3개뿐이라 LUT들과 달리 과적합 위험이 낮음, tone_core 캘리브레이션과 같은
성격).
"""
import os

import numpy as np
import colour

from hybrid_engine.core import (
    normalizer, tone_core, color_core, hue_core, lab2d_core, lab3d_core, spatial_core, color_matrix,
    raw_baseline,
)

_SRGB = colour.RGB_COLOURSPACES["sRGB"]
_LUTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "assets", "luts")

# 프로필에 없는 키를 위한 기본값 - assets/profiles/*.json은 이 중 필요한
# 키만 override하면 된다.
_DEFAULT_PARAMS = {
    "raw_baseline_matrix": None,  # Phase 0 - 3x3 중첩 리스트, 없으면 bypass
    "use_color_unification": True,  # Phase 0 - camera_whitebalance가 없으면 자동 skip
    "target_gray": 0.18,
    "correct_color_cast": True,
    "normalize_exposure": True,  # Phase 0 - raw_baseline_matrix가 있으면 False 권장(EVALUATION.md 후속 실측 6)
    "shadow_lift": 0.02,
    "shadow_threshold": 0.1,
    "contrast_n": 1.15,
    "highlight_rolloff_start": 0.8,
    "sat_gain": 0.15,
    "sat_center": 50.0,
    "sat_width": 35.0,
    "max_chroma": 110.0,
    "learned_tone_lut": None,  # npy 파일명(assets/luts/ 기준) 또는 절대경로
    "learned_hue_lut": None,  # npy 파일명(assets/luts/ 기준) 또는 절대경로
    "learned_lab2d_lut": None,  # npz 파일명(assets/luts/ 기준, table+domain) 또는 절대경로
    "learned_lab3d_lut": None,  # npz 파일명(assets/luts/ 기준, table+domain) 또는 절대경로
    "use_spatial": False,  # Phase 3 - 캘리브레이션 전까지는 기본 bypass
    "spatial_radius": 30.0,
    "spatial_amount": 0.0,  # 0이면 use_spatial=True여도 완전 항등
    "spatial_threshold": 0.0,
}


class HybridCameraEngine:
    """profile(dict)로 브랜드별 파라미터를 주입받는 파이프라인 실행기.
    profile은 assets/profiles/*.json을 로드해서 넘기거나(main.py 참고)
    직접 dict로 구성해도 된다 - 누락된 키는 _DEFAULT_PARAMS로 채워짐."""

    def __init__(self, profile=None):
        self.params = dict(_DEFAULT_PARAMS)
        if profile:
            self.params.update(profile)

        self._raw_baseline_matrix = None
        matrix_param = self.params.get("raw_baseline_matrix")
        if matrix_param is not None:
            self._raw_baseline_matrix = np.asarray(matrix_param, dtype=np.float64)

        self._tone_lut = None
        lut_ref = self.params.get("learned_tone_lut")
        if lut_ref:
            path = lut_ref if os.path.isabs(lut_ref) else os.path.join(_LUTS_DIR, lut_ref)
            self._tone_lut = np.load(path)

        self._hue_lut = None
        hue_lut_ref = self.params.get("learned_hue_lut")
        if hue_lut_ref:
            path = hue_lut_ref if os.path.isabs(hue_lut_ref) else os.path.join(_LUTS_DIR, hue_lut_ref)
            self._hue_lut = np.load(path)

        self._lab2d_table = None
        self._lab2d_domain = None
        lab2d_ref = self.params.get("learned_lab2d_lut")
        if lab2d_ref:
            path = lab2d_ref if os.path.isabs(lab2d_ref) else os.path.join(_LUTS_DIR, lab2d_ref)
            data = np.load(path)
            self._lab2d_table = data["table"]
            self._lab2d_domain = data["domain"]

        self._lab3d_table = None
        self._lab3d_domain = None
        lab3d_ref = self.params.get("learned_lab3d_lut")
        if lab3d_ref:
            path = lab3d_ref if os.path.isabs(lab3d_ref) else os.path.join(_LUTS_DIR, lab3d_ref)
            data = np.load(path)
            self._lab3d_table = data["table"]
            self._lab3d_domain = data["domain"]

    def _apply_raw_baseline_matrix(self, linear_rgb):
        """Phase 0의 3x3 raw_baseline_matrix 적용 - 없으면 완전 bypass
        (V0.1 동작 그대로)."""
        if self._raw_baseline_matrix is not None:
            return raw_baseline.apply_color_matrix(linear_rgb, self._raw_baseline_matrix)
        return linear_rgb

    def to_normalized_lab(self, linear_rgb, camera_whitebalance=None):
        """Phase 0(raw_baseline 매트릭스 + 색정제 + Gray World 정규화)까지
        적용하고 LAB로 분리해서 (L, a, b)를 반환 - 톤/채도 커브 적용 전의
        "중립" 상태. calibrate_profile.py의 학습 모드가 이 L을 학습 입력
        도메인으로 쓰고, process()도 내부적으로 이 메서드를 재사용한다."""
        p = self.params

        unified = self._apply_raw_baseline_matrix(linear_rgb)
        if p["use_color_unification"] and camera_whitebalance is not None:
            source_white_xy = color_matrix.estimate_source_white_xy(camera_whitebalance)
            xyz0 = colour.RGB_to_XYZ(unified, _SRGB, apply_cctf_decoding=False)
            xyz0 = color_matrix.unify_to_d65(xyz0, source_white_xy)
            unified = np.clip(
                colour.XYZ_to_RGB(xyz0, _SRGB, apply_cctf_encoding=False), 0.0, None)

        normalized = normalizer.normalize(
            unified,
            target_gray=p["target_gray"],
            correct_color_cast=p["correct_color_cast"],
            apply_exposure=p["normalize_exposure"],
        )

        xyz = colour.RGB_to_XYZ(normalized, _SRGB, apply_cctf_decoding=False)
        lab = colour.XYZ_to_Lab(xyz)
        return lab[..., 0], lab[..., 1], lab[..., 2]

    def _apply_tone(self, L):
        """L채널 톤 적용 - 학습 LUT이 로드돼 있으면 그걸 쓰고, 없으면
        파라메트릭(tone_core). LUT 포맷: [0, 1] 균등 도메인(L/100)에 대한
        출력값 배열(np.interp로 매핑)."""
        p = self.params
        if self._tone_lut is not None:
            x = np.clip(L / 100.0, 0.0, 1.0)
            domain = np.linspace(0.0, 1.0, len(self._tone_lut))
            y = np.interp(x.ravel(), domain, self._tone_lut).reshape(x.shape)
            return np.clip(y, 0.0, 1.0) * 100.0
        return tone_core.apply_tone(
            L,
            shadow_lift_amt=p["shadow_lift"],
            shadow_threshold=p["shadow_threshold"],
            contrast_n=p["contrast_n"],
            highlight_rolloff_start=p["highlight_rolloff_start"],
        )

    def to_pre_hue_lab(self, linear_rgb, camera_whitebalance=None):
        """Phase 0 정규화 + Phase 1(tone_core, L) + Phase 2(color_core,
        a/b 채도)까지 적용한 뒤, hue 보정 직전의 (L, a, b)를 반환 -
        calibrate_profile.py의 hue 학습 모드가 이 상태를 학습 입력
        도메인으로 쓰고, process()도 내부적으로 이 메서드를 재사용한다
        (to_normalized_lab()과 같은 이유)."""
        p = self.params
        L, a, b = self.to_normalized_lab(linear_rgb, camera_whitebalance)
        L2 = self._apply_tone(L)
        a2, b2 = color_core.apply_color(
            L2, a, b,
            sat_gain=p["sat_gain"],
            sat_center=p["sat_center"],
            sat_width=p["sat_width"],
            max_chroma=p["max_chroma"],
        )
        return L2, a2, b2

    def _apply_hue(self, a, b):
        """hue 보정 - 학습 LUT이 로드돼 있으면 적용, 없으면 완전 bypass
        (a, b를 그대로 반환) - V0.1엔 파라메트릭 hue 모델이 없다."""
        if self._hue_lut is not None:
            return hue_core.apply_hue_lut(a, b, self._hue_lut)
        return a, b

    def _apply_lab2d(self, a, b):
        """2D 잔차 LUT 적용 - 학습 LUT(table+domain)이 로드돼 있으면
        a/b를 결합으로 보정(L은 안 건드림), 없으면 완전 bypass."""
        if self._lab2d_table is not None:
            return lab2d_core.apply_lab2d_lut(a, b, self._lab2d_table, self._lab2d_domain)
        return a, b

    def _apply_lab3d(self, L, a, b):
        """3D 잔차 LUT 적용 - 학습 LUT(table+domain)이 로드돼 있으면
        L/a/b를 결합으로 보정, 없으면 완전 bypass."""
        if self._lab3d_table is not None:
            return lab3d_core.apply_lab3d_lut(L, a, b, self._lab3d_table, self._lab3d_domain)
        return L, a, b

    def _apply_spatial(self, L):
        """Phase 3 로컬 콘트라스트 - use_spatial=False(기본)면 완전
        bypass. True여도 spatial_amount=0이면 apply_local_contrast 자체가
        항등이라 이중으로 안전하다."""
        p = self.params
        if not p["use_spatial"]:
            return L
        return spatial_core.apply_local_contrast(
            L, radius=p["spatial_radius"], amount=p["spatial_amount"],
            threshold=p["spatial_threshold"],
        )

    def process(self, linear_rgb, camera_whitebalance=None):
        """RAW에서 디코드된 Linear RGB(float, [0, 1] 근방) -> 가공된
        Linear RGB. 저장은 utils/io.py의 save_tiff16()이 담당(감마 인코딩
        포함) - 이 메서드는 순수 linear 도메인 값만 다룬다.

        camera_whitebalance(rawpy raw.camera_whitebalance, R/G/B/G2 배수)를
        넘기면 Phase 0의 색정제(core/color_matrix.py)가 촬영 당시 추정
        광원을 D65로 색순응 변환해서 카메라 간 차이를 한 번 더 통일한다.
        생략하면 그 단계는 건너뛰고 바로 Gray World 정규화(Phase 0의
        나머지)부터 시작 - raw_baseline_matrix(있다면)는 이 둘보다도
        먼저 적용된다."""
        L2, a2, b2 = self.to_pre_hue_lab(linear_rgb, camera_whitebalance)
        a3, b3 = self._apply_hue(a2, b2)
        a4, b4 = self._apply_lab2d(a3, b3)
        L5, a5, b5 = self._apply_lab3d(L2, a4, b4)
        L6 = self._apply_spatial(L5)

        lab2 = np.stack([L6, a5, b5], axis=-1)
        xyz2 = colour.Lab_to_XYZ(lab2)
        rgb2 = colour.XYZ_to_RGB(xyz2, _SRGB, apply_cctf_encoding=False)

        return np.clip(rgb2, 0.0, None)
