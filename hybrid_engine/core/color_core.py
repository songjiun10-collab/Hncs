"""
[Phase 1] 가변 채도(Luma-Saturation) 및 Gamut Clamp - LAB의 a/b 채널
전담. tone_core가 만든 새 L 값을 기준으로 미드톤 위주 채도 부스팅을
적용하고, chroma가 과도하게 커지는 걸 막는다.
"""
import numpy as np


def luma_saturation_boost(L100, a, b, gain=0.15, center=50.0, width=35.0):
    """L(밝기)이 center에 가까울수록(미드톤) 채도를 더 많이 부스팅하고
    그림자/하이라이트는 상대적으로 덜 건드리는 가우시안 가중 부스트."""
    weight = np.exp(-0.5 * ((L100 - center) / width) ** 2)
    mult = 1.0 + gain * weight
    return a * mult, b * mult


def gamut_clamp(a, b, max_chroma=110.0):
    """chroma(sqrt(a^2+b^2))가 max_chroma를 넘으면 hue(방향)는 유지한 채
    크기만 축소한다. 실제 sRGB 색역 경계를 hue/lightness별로 정밀
    계산하는 게 아니라 고정 반지름으로 근사하는 단순화 - V0.1의 알려진
    한계(Phase 2에서 hue/lightness 의존 gamut boundary로 정교화 예정)."""
    chroma = np.sqrt(a ** 2 + b ** 2)
    scale = np.minimum(1.0, max_chroma / np.clip(chroma, 1e-6, None))
    return a * scale, b * scale


def apply_color(L100, a, b, sat_gain=0.15, sat_center=50.0, sat_width=35.0,
                 max_chroma=110.0):
    """color_core 파이프라인 진입점 - 가변 채도 부스팅 후 gamut clamp."""
    a2, b2 = luma_saturation_boost(L100, a, b, gain=sat_gain,
                                    center=sat_center, width=sat_width)
    return gamut_clamp(a2, b2, max_chroma=max_chroma)
