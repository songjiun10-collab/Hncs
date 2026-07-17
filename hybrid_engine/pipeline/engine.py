"""
core/의 개별 모듈(color_matrix/normalizer/tone_core/color_core/spatial_core)을
하나의 파이프라인으로 조립하는 HybridCameraEngine.

데이터 흐름: Linear RGB -> [Phase 0: 카메라 색정제, camera_whitebalance
제공 시] -> (Phase 1: Gray World 정규화) -> LAB 분리 -> tone_core(L,
또는 학습 LUT) -> color_core(a, b) -> spatial_core(V0.1은 bypass) ->
LAB 복원 -> Linear RGB

L채널 톤 단계는 두 모드가 있다:
  - 파라메트릭(기본): tone_core의 S-curve/shadow-lift/highlight-rolloff
  - 학습 LUT: profile의 "learned_tone_lut"에 npy 경로를 주면 raw+jpeg
    페어에서 픽셀 대응으로 직접 학습한 1D LUT을 대신 적용 -
    apply_hncs_learned가 파라메트릭 커브(RMSE 23.3)를 학습 LUT(15.4)으로
    이긴 것과 같은 원리를 hybrid_engine에 이식한 것
    (calibrate_profile.py --mode learned로 생성)
"""
import os

import numpy as np
import colour

from hybrid_engine.core import normalizer, tone_core, color_core, spatial_core, color_matrix

_SRGB = colour.RGB_COLOURSPACES["sRGB"]
_LUTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "assets", "luts")

# 프로필에 없는 키를 위한 기본값 - assets/profiles/*.json은 이 중 필요한
# 키만 override하면 된다.
_DEFAULT_PARAMS = {
    "use_color_unification": True,  # Phase 0 - camera_whitebalance가 없으면 자동 skip
    "target_gray": 0.18,
    "correct_color_cast": True,
    "shadow_lift": 0.02,
    "shadow_threshold": 0.1,
    "contrast_n": 1.15,
    "highlight_rolloff_start": 0.8,
    "sat_gain": 0.15,
    "sat_center": 50.0,
    "sat_width": 35.0,
    "max_chroma": 110.0,
    "learned_tone_lut": None,  # npy 파일명(assets/luts/ 기준) 또는 절대경로
    "use_spatial": False,  # Phase 2 예약 - V0.1은 항상 bypass
}


class HybridCameraEngine:
    """profile(dict)로 브랜드별 파라미터를 주입받는 파이프라인 실행기.
    profile은 assets/profiles/*.json을 로드해서 넘기거나(main.py 참고)
    직접 dict로 구성해도 된다 - 누락된 키는 _DEFAULT_PARAMS로 채워짐."""

    def __init__(self, profile=None):
        self.params = dict(_DEFAULT_PARAMS)
        if profile:
            self.params.update(profile)
        self._tone_lut = None
        lut_ref = self.params.get("learned_tone_lut")
        if lut_ref:
            path = lut_ref if os.path.isabs(lut_ref) else os.path.join(_LUTS_DIR, lut_ref)
            self._tone_lut = np.load(path)

    def to_normalized_lab(self, linear_rgb, camera_whitebalance=None):
        """Phase 0(색정제) + Phase 1(정규화)까지만 적용하고 LAB로 분리해서
        (L, a, b)를 반환 - 톤/채도 커브 적용 전의 "중립" 상태.
        calibrate_profile.py의 학습 모드가 이 L을 학습 입력 도메인으로 쓰고,
        process()도 내부적으로 이 메서드를 재사용한다."""
        p = self.params

        unified = linear_rgb
        if p["use_color_unification"] and camera_whitebalance is not None:
            source_white_xy = color_matrix.estimate_source_white_xy(camera_whitebalance)
            xyz0 = colour.RGB_to_XYZ(linear_rgb, _SRGB, apply_cctf_decoding=False)
            xyz0 = color_matrix.unify_to_d65(xyz0, source_white_xy)
            unified = np.clip(
                colour.XYZ_to_RGB(xyz0, _SRGB, apply_cctf_encoding=False), 0.0, None)

        normalized = normalizer.normalize(
            unified,
            target_gray=p["target_gray"],
            correct_color_cast=p["correct_color_cast"],
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

    def process(self, linear_rgb, camera_whitebalance=None):
        """RAW에서 디코드된 Linear RGB(float, [0, 1] 근방) -> 가공된
        Linear RGB. 저장은 utils/io.py의 save_tiff16()이 담당(감마 인코딩
        포함) - 이 메서드는 순수 linear 도메인 값만 다룬다.

        camera_whitebalance(rawpy raw.camera_whitebalance, R/G/B/G2 배수)를
        넘기면 Phase 0(색정제 - core/color_matrix.py)이 촬영 당시 추정
        광원을 D65로 색순응 변환해서 카메라 간 차이를 한 번 더 통일한다.
        생략하면 Phase 0은 건너뛰고 바로 Phase 1(Gray World)부터 시작."""
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

        lab2 = np.stack([L2, a2, b2], axis=-1)
        xyz2 = colour.Lab_to_XYZ(lab2)
        rgb2 = colour.XYZ_to_RGB(xyz2, _SRGB, apply_cctf_encoding=False)

        if p["use_spatial"]:
            rgb2 = spatial_core.apply_spatial(rgb2)

        return np.clip(rgb2, 0.0, None)
