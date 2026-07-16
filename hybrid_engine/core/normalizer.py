"""
[Phase 1] 카메라 색치우침/노출 정규화.

브랜드마다 다른 화이트밸런스/노출 편향(예: 특정 브랜드의 노란기)을 지우고
파라메트릭 코어(tone_core/color_core)가 일관되게 동작할 수 있는 중립
베이스라인으로 세탁하는 단계. hybrid_engine은 의존성을 최소화하기 위해
numpy만 쓰고, 다른 core 모듈(정규화 이후 단계)에 의존하지 않는다.
"""
import numpy as np


def gray_world_normalize(img_rgb):
    """Gray World 알고리즘 - 채널별 평균이 전체 평균(무채색 가정)에
    수렴하도록 R/G/B를 각각 스케일링해서 색치우침을 제거한다.

    장면 자체가 특정 색으로 편중된 경우(예: 초록 숲, 붉은 노을) 과보정될
    수 있다는 게 이 알고리즘의 알려진 약점 - V0.1에서는 이 한계를
    그대로 안고 간다(더 정교한 화이트패치/AWB 추정은 미구현)."""
    means = img_rgb.reshape(-1, 3).mean(axis=0)
    means_safe = np.clip(means, 1e-6, None)
    gray_mean = means.mean()
    scale = gray_mean / means_safe
    return img_rgb * scale


def normalize_exposure(img_rgb, target_gray=0.18):
    """전체 평균 밝기를 target_gray(기본 18% 미드그레이)로 맞춘다."""
    mean = float(np.mean(img_rgb))
    if mean <= 0:
        return img_rgb
    return img_rgb * (target_gray / mean)


def normalize(img_rgb, target_gray=0.18, correct_color_cast=True):
    """정규화 파이프라인 진입점 - Gray World 색치우침 제거 후 노출 정규화."""
    out = gray_world_normalize(img_rgb) if correct_color_cast else img_rgb
    return normalize_exposure(out, target_gray=target_gray)
