import cv2
import numpy as np


def apply_lut(img, lut):
    if img.dtype != np.uint8:
        img = np.clip(img * 255, 0, 255).astype(np.uint8)
    return cv2.LUT(img, lut)


# ==========================================
# 공유 헬퍼 (버그 수정의 핵심)
# ==========================================
def _s_curve(x, n=2.0):
    """
    대칭 S자 커브. x^n / (x^n + (1-x)^n) 형태.
    항상 y(0)=0, y(1)=1을 보장하므로 사인 기반 커브에서 발생하던
    "끝단이 0/1에 안 닿는" 문제가 원천적으로 없음.
    n=1: 직선(변화 없음) / n>1: 콘트라스트 강조 S자 / n<1: 대비 완화
    """
    x_safe = np.clip(x, 1e-6, 1 - 1e-6)
    return (x_safe ** n) / (x_safe ** n + (1 - x_safe) ** n)


def _apply_highlight_rolloff(x, y, start=0.8):
    """
    y 배열(이미 다른 커브가 적용된 상태)에 이어서 하이라이트만 부드럽게 압축.
    연속성 보장: rolloff 시작값을 커브에서 실제로 보간해서 가져오므로
    Acros에서 발생했던 "롤오프 시작점에서 값이 뚝 떨어지는" 문제가 없음.
    """
    mask = x > start
    if not np.any(mask):
        return y
    y_start = np.interp(start, x, y)
    headroom = 1.0 - y_start
    t = (x[mask] - start) / (1 - start)
    smooth_t = t * t * (3 - 2 * t)
    y[mask] = y_start + smooth_t * headroom
    return y


def _shadow_lift(x, y, lift=0.02, threshold=0.1):
    mask = x < threshold
    y[mask] = y[mask] + (lift * (1 - (x[mask] / threshold)))
    return y


# ==========================================
# 1. Astia/Soft (부드러운 색감, 인물용)
# ==========================================
def apply_astia(img_bgr):
    img = img_bgr.astype(np.float32)
    img[:, :, 2] = np.clip(img[:, :, 2] * 1.03, 0, 255)  # R
    img[:, :, 0] = np.clip(img[:, :, 0] * 0.97, 0, 255)  # B

    img_lab = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(img_lab)
    a = np.clip(a.astype(np.float32) * 1.05, 0, 255).astype(np.uint8)
    img = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

    # 하이라이트만 소프트하게 압축 (연속성 보장된 헬퍼 사용)
    x = np.arange(256, dtype=np.float32) / 255.0
    y = x.copy()
    y = _apply_highlight_rolloff(x, y, start=0.7)

    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    return apply_lut(img, lut)


# ==========================================
# 2. PRO Neg. Std (스튜디오 인물용, 부드러움)
# ==========================================
def apply_pro_neg_std(img_bgr):
    img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1] * 0.85, 0, 255)
    img = cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    # 수정: 사인+선형 혼합 대신 완만한 S커브(n=1.4)로 교체
    # 기존 코드는 검은점이 0.1까지 들려서 과하게 "탁해진" 느낌이었음
    x = np.arange(256, dtype=np.float32) / 255.0
    y = _s_curve(x, n=1.4)

    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    return apply_lut(img, lut)


# ==========================================
# 3. PRO Neg. Hi (Std + 콘트라스트 강화)
# ==========================================
def apply_pro_neg_hi(img_bgr):
    img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1] * 0.85, 0, 255)
    img = cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    # 수정: n=2.2 S커브로 진짜 대비 강화 (기존엔 끝단 압축으로 오히려
    # 다이나믹레인지가 줄어드는 역효과가 있었음 - 이제 0/1 정확히 도달)
    x = np.arange(256, dtype=np.float32) / 255.0
    y = _s_curve(x, n=2.2)

    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    img_curved = apply_lut(img, lut)

    img_lab = cv2.cvtColor(img_curved, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(img_lab)
    clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


# ==========================================
# 4. Eterna/Cinema (영화 느낌, 플랫, 틸 쉐도우)
# ==========================================
def apply_eterna_cinema(img_bgr):
    x = np.arange(256, dtype=np.float32) / 255.0
    y = np.clip(x * 0.7 + 0.15, 0, 1)

    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    img_flat = apply_lut(img_bgr, lut)

    img_lab = cv2.cvtColor(img_flat, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(img_lab)
    l_float = l.astype(np.float32) / 255.0

    shadow_weight = np.clip(1.0 - (l_float * 2.0), 0, 1)
    a = np.clip(a.astype(np.float32) - (shadow_weight * 15), 0, 255).astype(np.uint8)
    b = np.clip(b.astype(np.float32) - (shadow_weight * 10), 0, 255).astype(np.uint8)

    img_shifted = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

    img_hsv = cv2.cvtColor(img_shifted, cv2.COLOR_BGR2HSV).astype(np.float32)
    img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1] * 0.65, 0, 255)
    return cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


# ==========================================
# 5. Eterna Bleach Bypass (표백 현상, 저채도 고대비)
# ==========================================
def apply_eterna_bleach_bypass(img_bgr):
    img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1] * 0.25, 0, 255)
    img_low_sat = cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    # 수정: np.where 두 분기가 동일해서 사실상 죽은 코드였음 - 단순화.
    # 강한 대비 + 양끝 하드클리핑 (표백현상 특유의 날아간 느낌)은 그대로 유지
    x = np.arange(256, dtype=np.float32) / 255.0
    y = np.clip(x * 1.5 - 0.25, 0, 1)

    lut = (y * 255).astype(np.uint8)
    return apply_lut(img_low_sat, lut)


# ==========================================
# 6. Nostalgic Neg (빈티지, 따뜻한 앰버 강조)
# ==========================================
def apply_nostalgic_neg(img_bgr):
    img = img_bgr.astype(np.float32)
    img[:, :, 2] = np.clip(img[:, :, 2] * 1.1, 0, 255)
    img[:, :, 0] = np.clip(img[:, :, 0] * 0.9, 0, 255)

    img_lab = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(img_lab)
    a = np.where(a > 128, np.clip(a.astype(np.float32) * 1.1, 0, 255), a).astype(np.uint8)
    b = np.where(b > 128, np.clip(b.astype(np.float32) * 1.15, 0, 255), b).astype(np.uint8)

    l_float = l.astype(np.float32) / 255.0
    l_float = np.where(l_float > 0.8, 0.8 + (l_float - 0.8) * 0.5, l_float)
    l = np.clip(l_float * 255, 0, 255).astype(np.uint8)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


# ==========================================
# 7. Reala Ace (정확한 색 재현, 정직한 룩)
# ==========================================
def apply_reala_ace(img_bgr):
    if img_bgr.dtype != np.uint8:
        img_bgr = np.clip(img_bgr * 255, 0, 255).astype(np.uint8)

    img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1] * 0.95, 0, 255)
    img = cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    x = np.arange(256, dtype=np.float32) / 255.0
    y = x.copy()
    y = _apply_highlight_rolloff(x, y, start=0.85)

    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    return apply_lut(img, lut)


# ==========================================
# 8. Acros / Monochrome (흑백)
# ==========================================
def apply_acros(img_bgr, filter_type='none'):
    b, g, r = cv2.split(img_bgr)

    if filter_type == 'red':
        gray = (0.1 * b + 0.3 * g + 0.6 * r)
    elif filter_type == 'green':
        gray = (0.1 * b + 0.7 * g + 0.2 * r)
    elif filter_type == 'yellow':
        gray = (0.15 * b + 0.65 * g + 0.2 * r)
    else:
        gray = (0.2 * b + 0.6 * g + 0.2 * r)

    gray = np.clip(gray, 0, 255).astype(np.uint8)

    # 수정: 기존엔 x=0.9에서 커브값이 약 0.991 -> 0.9로 뚝 떨어지는
    # 불연속(밴딩 유발)이 있었음. S커브 + 연속성 보장 롤오프 헬퍼로 교체.
    x = np.arange(256, dtype=np.float32) / 255.0
    y = _s_curve(x, n=1.6)
    y = _apply_highlight_rolloff(x, y, start=0.9)

    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    return cv2.LUT(gray, lut)


def apply_monochrome(img_bgr):
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
