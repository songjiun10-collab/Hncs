"""
[Phase 1] 카메라 색치우침/노출 정규화.

브랜드마다 다른 화이트밸런스/노출 편향(예: 특정 브랜드의 노란기)을 지우고
파라메트릭 코어(tone_core/color_core)가 일관되게 동작할 수 있는 중립
베이스라인으로 세탁하는 단계. hybrid_engine은 의존성을 최소화하기 위해
numpy만 쓰고, 다른 core 모듈(정규화 이후 단계)에 의존하지 않는다.
"""
import numpy as np


def gray_world_normalize(img_rgb, saturation_percentile=100.0, strength=1.0):
    """Gray World 알고리즘 - 채널별 평균이 전체 평균(무채색 가정)에
    수렴하도록 R/G/B를 각각 스케일링해서 색치우침을 제거한다.

    장면 자체가 특정 색으로 편중된 경우(예: 초록 숲, 붉은 노을, 주황
    가로등 야경) 과보정된다는 게 이 알고리즘의 알려진 약점이고,
    EVALUATION.md 후속 실측 10에서 야경 하늘이 실제로 이 패턴으로
    깨지는 걸 실측했다(장면을 압도하는 주황 광원의 색치우침 추정이
    무관한 파란 하늘까지 전역 적용됨).

    saturation_percentile < 100이면 그 대책으로 **채도가 낮은 픽셀만**
    골라서 색치우침을 추정한다(robust gray world) - 채도 상위 픽셀
    (가로등, 네온, 꽃밭 등 "원래 유채색인 피사체")이 무채색 가정을
    오염시키지 못하게 하고, 스케일 자체는 기존과 동일하게 화면 전체에
    적용한다. 100.0(기본값)이면 모든 픽셀을 쓰는 기존 동작과 완전히
    동일하다.

    strength는 추정된 스케일과 항등(무보정) 사이를 선형 보간하는 자유도
    1개짜리 미세조정 축(후속 실측 11/12/13 - percentile/hue-chroma/zoned
    전부 자유도를 늘리는 방향이라 기각됐다는 데서 반대로 자유도를 최소로
    줄여본 것) - 1.0(기본값)이 기존 동작, 0.0이면 완전 제거(후속 실측
    13에서 -90.3%로 대참사였던 그 상태)와 같고, 0~1 사이거나 1을 넘는
    값(과보정)도 허용한다."""
    flat = img_rgb.reshape(-1, 3)
    if saturation_percentile < 100.0:
        mx = flat.max(axis=1)
        mn = flat.min(axis=1)
        sat = (mx - mn) / np.clip(mx, 1e-6, None)
        thresh = np.percentile(sat, saturation_percentile)
        mask = sat <= thresh
        if mask.sum() > 0:
            flat = flat[mask]
    means = flat.mean(axis=0)
    means_safe = np.clip(means, 1e-6, None)
    gray_mean = means.mean()
    scale = gray_mean / means_safe
    blended_scale = 1.0 + strength * (scale - 1.0)
    return img_rgb * blended_scale


def gray_world_normalize_zoned(img_rgb, n_zones=3, blend_sigma=0.15):
    """Gray World를 밝기(luma) 구간별로 따로 추정해서 부드럽게 섞는다.

    후속 실측 10/11에서 확인된 근본 문제: 전역 스칼라 하나짜리 Gray World는
    하늘(밝고 중성/파랑)과 도로·광원(어둡고 따뜻함)처럼 밝기 구간마다 색
    성질이 완전히 다른 장면(야경 등)을 동시에 만족시킬 수 없다 -
    saturation_percentile로 "오염 픽셀을 빼는" 방식(후속 실측 11)은
    스칼라 하나라는 구조 자체는 그대로라 기각됐다. 이 함수는 반대로
    **밝기 구간마다 독립적인 색치우침 추정치**를 쓴다 - 하늘(밝은 구간)과
    도로(어두운 구간)가 서로 다른 보정을 받을 수 있게.

    구간은 이미지 자체의 luma(R+G+B 평균) 퍼센타일로 정의(절대 밝기가
    아니라 "이 사진에서 상대적으로 밝은/어두운 픽셀") - normalize()가
    아직 톤 커브 적용 전(raw 선형 RGB) 단계에서 호출되기 때문에, Lab L처럼
    지각적으로 정의된 구간을 쓰려면 별도 변환이 필요해서 여기선 안 쓴다
    (numpy만 쓴다는 이 모듈의 의존성 원칙 참고).

    n_zones개의 구간 중심에 가우시안 가중치로 각 픽셀을 배분해서 구간별
    Gray World 평균을 구하고(np.average와 동일한 가중평균), 각 픽셀의
    최종 스케일은 그 픽셀이 속한 정도(가중치)에 비례해 구간별 스케일을
    섞어서 만든다 - 그래서 구간 경계에서 계단식 밴딩 없이 부드럽게
    이어진다. n_zones=1이면 기존 gray_world_normalize()와 완전히 동일."""
    if n_zones <= 1:
        return gray_world_normalize(img_rgb)

    flat = img_rgb.reshape(-1, 3)
    luma = flat.mean(axis=1)
    lo, hi = np.percentile(luma, 1), np.percentile(luma, 99)
    luma_norm = np.clip((luma - lo) / max(hi - lo, 1e-8), 0.0, 1.0)

    zone_centers = (np.arange(n_zones) + 0.5) / n_zones
    weights = np.stack(
        [np.exp(-0.5 * ((luma_norm - c) / blend_sigma) ** 2) for c in zone_centers], axis=1
    )  # (N, n_zones)
    weight_sums = weights.sum(axis=0)  # (n_zones,)

    zone_scales = np.ones((n_zones, 3))
    for i in range(n_zones):
        if weight_sums[i] < 1e-6:
            continue
        zone_mean = (flat * weights[:, i:i + 1]).sum(axis=0) / weight_sums[i]
        zone_mean_safe = np.clip(zone_mean, 1e-6, None)
        gray_mean = zone_mean.mean()
        zone_scales[i] = gray_mean / zone_mean_safe

    pixel_weight_sum = np.clip(weights.sum(axis=1, keepdims=True), 1e-6, None)
    blend = weights / pixel_weight_sum  # (N, n_zones)
    pixel_scale = blend @ zone_scales  # (N, 3)

    return (flat * pixel_scale).reshape(img_rgb.shape)


def normalize_exposure(img_rgb, target_gray=0.18):
    """전체 평균 밝기를 target_gray(기본 18% 미드그레이)로 맞춘다."""
    mean = float(np.mean(img_rgb))
    if mean <= 0:
        return img_rgb
    return img_rgb * (target_gray / mean)


def normalize(img_rgb, target_gray=0.18, correct_color_cast=True, apply_exposure=True,
              gray_world_saturation_percentile=100.0, gray_world_zones=1, gray_world_strength=1.0):
    """정규화 파이프라인 진입점 - Gray World 색치우침 제거 후 노출 정규화.

    apply_exposure=False면 노출 정규화를 건너뛴다 - Phase 0에 raw_baseline_matrix
    (최소자승으로 적합한 3x3 컬러 매트릭스)가 있을 때 필요해졌다: 매트릭스는
    각 페어의 실제 밝기 관계를 그대로 보존한 채로 적합됐는데, 모든 사진의
    평균 밝기를 강제로 target_gray로 맞춰버리면(사진마다 실측 평균이
    0.03~0.44로 10배 넘게 벌어짐) 매트릭스가 이미 맞춰놓은 결과를 다시
    망가뜨린다는 게 실측으로 확인됨(ΔE 8.55 -> 14.62, 거의 전부 이 단계
    때문 - hybrid_engine/EVALUATION.md 후속 실측 6 참고).

    gray_world_zones > 1이면 gray_world_normalize_zoned()(밝기 구간별
    독립 추정, 후속 실측 10/11 대응)를 쓴다 - gray_world_saturation_percentile
    과는 서로 다른 축이라 동시에는 안 쓴다(zones>1이면 saturation_percentile
    무시). gray_world_strength는 zones=1일 때만 적용되는 미세조정 축
    (후속 실측 14)."""
    if not correct_color_cast:
        out = img_rgb
    elif gray_world_zones > 1:
        out = gray_world_normalize_zoned(img_rgb, n_zones=gray_world_zones)
    else:
        out = gray_world_normalize(img_rgb, saturation_percentile=gray_world_saturation_percentile,
                                    strength=gray_world_strength)
    if apply_exposure:
        out = normalize_exposure(out, target_gray=target_gray)
    return out
