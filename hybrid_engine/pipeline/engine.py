"""
core/의 개별 모듈(color_matrix/normalizer/tone_core/color_core/spatial_core)을
하나의 파이프라인으로 조립하는 HybridCameraEngine.

데이터 흐름: Linear RGB -> [Phase 0: 카메라 색정제, camera_whitebalance
제공 시] -> (Phase 1: Gray World 정규화) -> LAB 분리 -> tone_core(L) ->
color_core(a, b) -> spatial_core(V0.1은 bypass) -> LAB 복원 -> Linear RGB
"""
import numpy as np
import colour

from hybrid_engine.core import normalizer, tone_core, color_core, spatial_core, color_matrix

_SRGB = colour.RGB_COLOURSPACES["sRGB"]

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

    def process(self, linear_rgb, camera_whitebalance=None):
        """RAW에서 디코드된 Linear RGB(float, [0, 1] 근방) -> 가공된
        Linear RGB. 저장은 utils/io.py의 save_tiff16()이 담당(감마 인코딩
        포함) - 이 메서드는 순수 linear 도메인 값만 다룬다.

        camera_whitebalance(rawpy raw.camera_whitebalance, R/G/B/G2 배수)를
        넘기면 Phase 0(색정제 - core/color_matrix.py)이 촬영 당시 추정
        광원을 D65로 색순응 변환해서 카메라 간 차이를 한 번 더 통일한다.
        생략하면 Phase 0은 건너뛰고 바로 Phase 1(Gray World)부터 시작."""
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
        L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]

        L2 = tone_core.apply_tone(
            L,
            shadow_lift_amt=p["shadow_lift"],
            shadow_threshold=p["shadow_threshold"],
            contrast_n=p["contrast_n"],
            highlight_rolloff_start=p["highlight_rolloff_start"],
        )
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
