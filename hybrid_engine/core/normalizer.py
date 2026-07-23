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


def white_patch_normalize(img_rgb, percentile=100.0):
    """White Patch(Max-RGB) 알고리즘 - Gray World와 반대 가정: "장면에서
    가장 밝은 지점은 원래 흰색/무채색이었을 것"이라고 보고, 채널별
    최댓값이 서로 같아지도록(가장 밝은 채널은 그대로 두고 나머지를
    끌어올려) 스케일링한다. Gray World는 "평균이 회색"을 가정하고
    White Patch는 "최댓값이 흰색"을 가정한다는 점에서 서로 독립적인
    축 - 하이라이트에 실제 무채색 물체(흰 벽, 구름, 반사광)가 있는
    장면에서는 Gray World보다 나을 수 있지만, 채도 높은 물체가 화면에서
    가장 밝은 경우(네온사인, 조명이 켜진 유채색 광원) 그 색으로
    전체를 물들이는 게 알려진 약점.

    percentile < 100이면 진짜 최댓값 대신 그 퍼센타일 값을 써서 센서
    노이즈/스펙큘러 하이라이트 한두 픽셀에 전체가 휘둘리지 않게 한다
    (100.0이 고전적인 순수 White Patch와 동일)."""
    flat = img_rgb.reshape(-1, 3)
    if percentile >= 100.0:
        max_per_channel = flat.max(axis=0)
    else:
        max_per_channel = np.percentile(flat, percentile, axis=0)
    max_safe = np.clip(max_per_channel, 1e-6, None)
    target = max_per_channel.max()
    scale = target / max_safe
    return img_rgb * scale


def shades_of_gray_normalize(img_rgb, p=6.0):
    """Shades of Gray(Minkowski p-norm) 알고리즘 - Gray World(산술평균,
    p=1과 동일)와 White Patch(p->무한대에 가까울수록 최댓값에 수렴)를
    하나의 식으로 잇는 일반화. 채널별로 (mean(pixel^p))^(1/p)를 조명
    추정치로 쓰고, 그 추정치들의 평균에 맞춰 스케일링한다. van de Weijer
    등의 논문에서 p=6 안팎이 실전에서 무난하다고 알려진 절충값이라
    기본값으로 둠 - Gray World보다 밝은/채도 높은 픽셀에 더 가중치를
    줘서 극단적인 저채도 편향을 줄이면서도 White Patch만큼 하이라이트
    한 점에 휘둘리진 않는다는 게 이론적 동기."""
    flat = np.clip(img_rgb.reshape(-1, 3), 0.0, None)
    illum = np.power(np.mean(np.power(flat, p), axis=0), 1.0 / p)
    illum_safe = np.clip(illum, 1e-6, None)
    target = illum.mean()
    scale = target / illum_safe
    return img_rgb * scale


def gray_edge_normalize(img_rgb, p=1.0):
    """Gray Edge 알고리즘(van de Weijer 2007) - 픽셀값이 아니라 공간
    미분(엣지)의 평균이 무채색이라는 가정. Gray World/Shades of
    Gray/White Patch는 전부 "픽셀 강도 자체"의 통계를 쓰는데, 이 방식은
    "인접 픽셀 간 색 변화량"의 통계를 쓴다는 점에서 이 모듈의 다른
    알고리즘들과 근본적으로 다른 축 - 장면 전체가 하나의 색으로 뒤덮인
    경우(예: 녹색 숲 전체를 채우는 나뭇잎)에도 엣지(잎과 그림자 사이
    경계 등)의 색 자체는 여전히 다양해서 Gray World보다 덜 흔들릴
    수 있다는 게 이론적 동기.

    1차 미분(np.diff, 상하좌우)의 크기를 채널별로 구해서 Shades of
    Gray와 같은 방식(p-norm 평균)으로 조명을 추정한다. 가우시안
    스무딩은 안 함(이 모듈의 numpy-only 의존성 원칙, 원 논문의 sigma=0
    설정에 해당)."""
    grad_x = np.diff(img_rgb, axis=1, prepend=img_rgb[:, :1, :])
    grad_y = np.diff(img_rgb, axis=0, prepend=img_rgb[:1, :, :])
    grad_mag = np.hypot(grad_x, grad_y)
    flat_grad = grad_mag.reshape(-1, 3)
    illum = np.power(np.mean(np.power(flat_grad, p), axis=0), 1.0 / p)
    illum_safe = np.clip(illum, 1e-6, None)
    target = illum_safe.mean()
    scale = target / illum_safe
    return img_rgb * scale


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
              gray_world_saturation_percentile=100.0, gray_world_zones=1, gray_world_strength=1.0,
              color_cast_algorithm="gray_world", white_patch_percentile=100.0,
              shades_of_gray_p=6.0, gray_edge_p=1.0):
    """정규화 파이프라인 진입점 - 색치우침 제거 후 노출 정규화.

    apply_exposure=False면 노출 정규화를 건너뛴다 - Phase 0에 raw_baseline_matrix
    (최소자승으로 적합한 3x3 컬러 매트릭스)가 있을 때 필요해졌다: 매트릭스는
    각 페어의 실제 밝기 관계를 그대로 보존한 채로 적합됐는데, 모든 사진의
    평균 밝기를 강제로 target_gray로 맞춰버리면(사진마다 실측 평균이
    0.03~0.44로 10배 넘게 벌어짐) 매트릭스가 이미 맞춰놓은 결과를 다시
    망가뜨린다는 게 실측으로 확인됨(ΔE 8.55 -> 14.62, 거의 전부 이 단계
    때문 - hybrid_engine/EVALUATION.md 후속 실측 6 참고).

    color_cast_algorithm으로 색치우침 추정 알고리즘 자체를 바꿀 수 있다
    ("gray_world"(기본, 이하 3개 파라미터 적용) / "white_patch" /
    "shades_of_gray" / "gray_edge") - gray_world가 아니면 gray_world_*
    3개 파라미터는 전부 무시된다."""
    if not correct_color_cast:
        out = img_rgb
    elif color_cast_algorithm == "white_patch":
        out = white_patch_normalize(img_rgb, percentile=white_patch_percentile)
    elif color_cast_algorithm == "shades_of_gray":
        out = shades_of_gray_normalize(img_rgb, p=shades_of_gray_p)
    elif color_cast_algorithm == "gray_edge":
        out = gray_edge_normalize(img_rgb, p=gray_edge_p)
    elif gray_world_zones > 1:
        out = gray_world_normalize_zoned(img_rgb, n_zones=gray_world_zones)
    else:
        out = gray_world_normalize(img_rgb, saturation_percentile=gray_world_saturation_percentile,
                                    strength=gray_world_strength)
    if apply_exposure:
        out = normalize_exposure(out, target_gray=target_gray)
    return out
