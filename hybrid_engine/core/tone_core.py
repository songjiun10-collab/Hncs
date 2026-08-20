"""
[Phase 1] L 채널(명도) 전담 톤 제어 - Shadow Lift, S-Curve 콘트라스트,
Highlight Rolloff. LAB의 L은 [0, 100] 범위로 들어오지만 커브 수식
자체는 [0, 1] 정규화 도메인의 1D LUT으로 만든 뒤 전체 이미지에
np.interp로 매핑한다 (brands/*.py가 쓰는 LUT 패턴과 동일한 방식 - 커브
연산을 LUT 해상도만큼만 계산하면 되고, 2D 이미지 전체에 np.interp를
그대로 걸 수도 있어 구현이 단순해진다).
"""
import numpy as np

_LUT_SIZE = 4096


def s_curve(x, n=1.15):
    """대칭 S자 콘트라스트 커브. x^n / (x^n + (1-x)^n).
    n=1: 변화 없음 / n>1: 콘트라스트 강조 / n<1: 대비 완화.
    항상 y(0)=0, y(1)=1을 보장한다."""
    x_safe = np.clip(x, 1e-6, 1 - 1e-6)
    return (x_safe ** n) / (x_safe ** n + (1 - x_safe) ** n)


def shadow_lift(x, y, lift=0.02, threshold=0.1):
    """threshold 아래 암부를 lift만큼 들어올린다 (x=0에서 lift 최대,
    threshold에서 0으로 선형 감쇠)."""
    y = y.copy()
    mask = x < threshold
    y[mask] = y[mask] + (lift * (1 - (x[mask] / threshold)))
    return y


def apply_highlight_rolloff(x, y, start=0.8):
    """start 이상 하이라이트만 부드럽게(smoothstep) 압축해서 계조를
    보존한다. x, y는 1D 도메인 배열(LUT)이어야 한다 - np.interp로 시작점
    값을 보간해서 연속성을 보장하기 때문."""
    y = y.copy()
    mask = x > start
    if not np.any(mask):
        return y
    y_start = np.interp(start, x, y)
    headroom = 1.0 - y_start
    t = (x[mask] - start) / (1 - start)
    smooth_t = t * t * (3 - 2 * t)
    y[mask] = y_start + smooth_t * headroom
    return y


def _build_tone_lut(shadow_lift_amt, shadow_threshold, contrast_n,
                     highlight_rolloff_start):
    """1D 도메인([0, 1], _LUT_SIZE개 점)에 톤 파이프라인을 적용한 LUT을
    만든다."""
    x = np.linspace(0.0, 1.0, _LUT_SIZE)
    y = s_curve(x, n=contrast_n)
    y = shadow_lift(x, y, lift=shadow_lift_amt, threshold=shadow_threshold)
    y = apply_highlight_rolloff(x, y, start=highlight_rolloff_start)
    return x, np.clip(y, 0.0, 1.0)


def apply_tone(L100, shadow_lift_amt=0.02, shadow_threshold=0.1,
               contrast_n=1.15, highlight_rolloff_start=0.8):
    """LAB의 L 채널(임의 shape, [0, 100])에 톤 파이프라인 전체 적용:
    S-curve 콘트라스트 -> shadow lift -> highlight rolloff. LUT을 만든
    뒤 np.interp로 전체 배열에 한 번에 매핑한다. 반환도 [0, 100] 범위."""
    x_lut, y_lut = _build_tone_lut(shadow_lift_amt, shadow_threshold,
                                    contrast_n, highlight_rolloff_start)
    x_img = np.clip(L100 / 100.0, 0.0, 1.0)
    y_img = np.interp(x_img.ravel(), x_lut, y_lut).reshape(x_img.shape)
    return y_img * 100.0
