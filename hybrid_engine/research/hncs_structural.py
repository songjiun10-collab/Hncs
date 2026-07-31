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

**"미러링"이라는 말의 범위**(과대해석 금지):

- 이 모듈은 조사된 **단계 구성**을 흉내낼 뿐, Phocus의 실제 매트릭스/LUT
  값을 재현하지 않는다. 값은 우리 13쌍으로 새로 피팅한 근사치다.
- 평가(tools/evaluate_hncs_structural.py)의 정답지는 **카메라 내장
  JPEG**이지 Phocus/HNCS의 출력이 아니다. 따라서 ΔE가 낮아진다고 해서
  "진짜 HNCS에 더 가깝다"는 뜻이 되지 않는다 - 재는 건 "카메라 JPEG에
  얼마나 가까운가"뿐이다.
- 그 평가에서 4단계 중 필름커브는 **피팅하지 않고** film_curve() 기본값
  (= apply_hncs()가 쓰는 값)으로 고정한다. 데이터로 정해지는 건 매트릭스,
  chroma LUT, 클러스터 분류 3가지다.
- 2026-07 실측 결과는 apply_hncs() 대비 **판정 보류(무승부)**다 - 평균
  ΔE는 4.1% 낮았지만 n=13에서 그 차이가 0과 구분되지 않는다. 자세한
  통계와 한계는 hybrid_engine/EVALUATION.md "HNCS 구조 실험" 절.
"""
import cv2
import colour
import numpy as np

from core.curve import film_curve
from hybrid_engine.core.raw_baseline import apply_color_matrix
from hybrid_engine.utils.exif import read_as_shot_neutral
from hybrid_engine.utils.io import decode_raw_native

CLUSTER_THRESHOLD_R_OVER_B = 0.9
_SRGB = colour.RGB_COLOURSPACES["sRGB"]


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


def compute_blend_weight_rb(as_shot_neutral, rb_min, rb_max):
    """AsShotNeutral의 R/B 비율을 [rb_min, rb_max] 범위 기준으로
    [0, 1]로 정규화한 블렌딩 가중치. 0에 가까울수록 앵커A(저 R/B),
    1에 가까울수록 앵커B. rb_min/rb_max는 13쌍 전체에서 관측된 실제
    최솟값/최댓값을 호출부(평가 스크립트)가 넘긴다 - 하드코딩하지
    않는다. 관측 범위 밖 값이 오면 [0,1] 밖으로 나갈 수 있고, 이는
    의도된 외삽 허용이다."""
    r_over_b = as_shot_neutral[0] / as_shot_neutral[2]
    return (r_over_b - rb_min) / (rb_max - rb_min)


def compute_blend_weight_cct(as_shot_neutral, mired_min, mired_max):
    """AsShotNeutral을 대략적 CCT로 변환(camera-native RGB를 sRGB
    선형 RGB로 근사하는 가정 1개 추가 - 실제 카메라 분광감도를 모르니
    엄밀하지 않다, 이 실험 안에서만 쓰는 근사) 후 mired(=1e6/CCT) 공간
    에서 [mired_min, mired_max] 기준 [0, 1]로 정규화. mired 공간에서
    보간하는 건 Adobe DCP의 실제 dual-illuminant 보간 관례와 동일."""
    rgb = np.array(as_shot_neutral[:3], dtype=np.float64)
    xyz = colour.RGB_to_XYZ(rgb, _SRGB, apply_cctf_decoding=False)
    xy = colour.XYZ_to_xy(xyz)
    cct = colour.temperature.xy_to_CCT(xy, method="McCamy 1992")
    mired = 1e6 / cct
    return (mired - mired_min) / (mired_max - mired_min)


def apply_hncs_structural_blend(raw_path, weight, matrix_a, matrix_b,
                                 chroma_lut_a, chroma_lut_b,
                                 toe_lift, shoulder_start, white_point):
    """블렌딩 버전 4단계 파이프라인: WB적용 네이티브 RGB -> 가중
    평균 매트릭스((1-weight)*matrix_a + weight*matrix_b) -> 가중 평균
    chroma LUT 파라미터 -> 공유 필름커브(하드클러스터 버전과 동일하게
    조명 무관 고정). weight는 이미 계산된 스칼라를 받는다
    (compute_blend_weight_*는 평가 스크립트에서 호출) - 이 함수는
    블렌딩 로직만 담당한다."""
    wb_rgb = decode_and_white_balance(raw_path)
    blended_matrix = (1.0 - weight) * matrix_a + weight * matrix_b
    matrixed = apply_color_matrix(wb_rgb, blended_matrix)
    sat_a, hue_a = chroma_lut_a
    sat_b, hue_b = chroma_lut_b
    sat_mult = (1.0 - weight) * sat_a + weight * sat_b
    hue_shift_deg = (1.0 - weight) * hue_a + weight * hue_b
    chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
    return film_curve(chroma_applied, toe_lift=toe_lift,
                       shoulder_start=shoulder_start, white_point=white_point)
