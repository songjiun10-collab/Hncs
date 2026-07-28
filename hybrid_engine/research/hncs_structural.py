"""HNCS(Hasselblad Natural Colour Solution) 실제 4단계 렌더 구조를
미러링한 연구용 실험 모듈.

brands/hasselblad.py의 apply_hncs()(⭐ Stable, 실사용 중, 3단계 단순화:
exposure_gamma LUT -> CLAHE -> film_curve LUT)와 완전히 별도다.
apply_hncs()는 이 모듈에서 절대 수정하지 않는다.

구조 대비와 출처는 docs/hncs_structural_research.md 참고. 설계 근거는
docs/superpowers/specs/2026-07-28-hncs-structural-research-design.md.

실제 HNCS 파이프라인(조사 결과, 4단계):
1. RAW 센서 데이터
2. 조명별(illuminant-specific) 3x3 컬러 매트릭스
3. 그 매트릭스와 짝지어진 조명별 chroma LUT (hue/채도 보정)
4. Hasselblad Film Curve (공유, 조명과 무관)

이 모듈은 표본(13쌍 raw+jpeg)이 뒷받침하는 만큼만 근사한다: 조명
"최소 4종" 대신 AsShotNeutral R/B 비율 기반 2-클러스터
("cluster_a"/"cluster_b", 임계값 CLUSTER_THRESHOLD_R_OVER_B)로 단순화.
"""
import cv2
import numpy as np

from core.curve import film_curve
from hybrid_engine.core.raw_baseline import apply_color_matrix
from hybrid_engine.utils.exif import read_as_shot_neutral
from hybrid_engine.utils.io import decode_raw_native

CLUSTER_THRESHOLD_R_OVER_B = 0.9


def decode_and_white_balance(raw_path):
    """RAW -> 카메라 네이티브 linear RGB에 AsShotNeutral로 WB만 적용한
    상태(HNCS 2단계 - 조명별 매트릭스 - 가 받는 입력에 해당). WB
    게인만 걸고 아직 어떤 색매트릭스도 안 걸린 상태를 만들어야 하므로
    decode_raw()(libraw 자체 매트릭스까지 같이 적용)가 아니라
    decode_raw_native()(WB/매트릭스 둘 다 미적용)에서 시작해 직접
    AsShotNeutral로 나눈다."""
    native_rgb = decode_raw_native(raw_path)
    as_shot_neutral = read_as_shot_neutral(raw_path)
    if as_shot_neutral is None:
        raise ValueError(f"AsShotNeutral 태그를 읽을 수 없음: {raw_path}")
    return native_rgb / as_shot_neutral


def classify_illuminant_cluster(as_shot_neutral, threshold=CLUSTER_THRESHOLD_R_OVER_B):
    """AsShotNeutral[0]/AsShotNeutral[2](R/B 비율)로 2-클러스터 분류.
    threshold 미만이면 "cluster_a"(실측 10쌍, R/B 0.36~0.66), 이상이면
    "cluster_b"(실측 3쌍, R/B 1.13~1.32). 기본 임계값 0.9는 두 그룹
    사이(0.66~1.13) 아무 값이나 가능해서 중간값으로 고른 것."""
    r_over_b = as_shot_neutral[0] / as_shot_neutral[2]
    return "cluster_a" if r_over_b < threshold else "cluster_b"


def apply_chroma_lut(img_rgb, sat_mult, hue_shift_deg):
    """조명 클러스터별 hue/채도 보정(HNCS 3단계). HSV로 변환해 S
    채널에 sat_mult를 곱하고 H 채널에 hue_shift_deg를 더한 뒤 되돌린다.
    표본이 작아 저차원(파라미터 2개)으로 제한 - 그 이상(예: hue별 배열)은
    이 프로젝트가 반복적으로 경고해온 과적합 함정과 같다.

    img_rgb가 [0,1]을 벗어나는 하이라이트를 담고 있을 수 있는데, HSV
    변환 전에 [0,1]로 clip한다 - 뒤이은 film_curve 단계가 셔츠/롤오프를
    처리하는 대상 범위도 [0,1]이라 여기서 먼저 맞춘다(연구용 단순화로
    문서에 명시)."""
    clipped = np.clip(img_rgb, 0.0, 1.0).astype(np.float32)
    hsv = cv2.cvtColor(clipped, cv2.COLOR_RGB2HSV)
    hsv[..., 0] = (hsv[..., 0] + hue_shift_deg) % 360.0
    hsv[..., 1] = np.clip(hsv[..., 1] * sat_mult, 0.0, 1.0)
    out = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
    return np.clip(out, 0.0, 1.0).astype(np.float64)


def apply_hncs_structural(raw_path, illuminant_matrices, chroma_lut_params,
                           toe_lift, shoulder_start, white_point):
    """4단계 파이프라인: WB적용 네이티브 RGB -> 클러스터별 3x3 매트릭스
    -> 클러스터별 chroma LUT -> 공유 필름커브.

    illuminant_matrices/chroma_lut_params는 {"cluster_a": ..., "cluster_b": ...}
    형태의 피팅 결과를 받는다(피팅 자체는 tools/evaluate_hncs_structural.py).
    필름커브만 클러스터로 안 나누고 공유 - 톤(밝기 분포)은 조명보다
    노출/장면에 더 좌우된다고 보는 판단(v11에서 apply_hncs()의
    toe_lift/shoulder_start를 표본이 작아 바꾸지 않은 전례와 같은
    이유)."""
    wb_rgb = decode_and_white_balance(raw_path)
    as_shot_neutral = read_as_shot_neutral(raw_path)
    cluster = classify_illuminant_cluster(as_shot_neutral)
    matrixed = apply_color_matrix(wb_rgb, illuminant_matrices[cluster])
    sat_mult, hue_shift_deg = chroma_lut_params[cluster]
    chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
    return film_curve(chroma_applied, toe_lift=toe_lift,
                       shoulder_start=shoulder_start, white_point=white_point)
