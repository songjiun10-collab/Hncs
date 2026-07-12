"""
후지필름 스타일 필름 시뮬레이션 프리셋 8종.

Astia/Pro Neg Std는 실측 검증됨(tools/analyze.py fuji_film_modes 모드,
mirrorlesscomparison.com 리뷰 갤러리의 RAW+SOOC JPEG에서 실제 Film Mode
태그(exiftool)별 population 비교) - 나머지 6종은 대응하는 실측 라벨을
못 구해서(Eterna/Nostalgic Neg/Reala Ace/Acros 등은 이 사이트 표본에
없었음) 여전히 미검증 추정.

raw+jpeg "같은 사진" 페어를 노려봤지만(mirrorlesscomparison.com의 "RAW
samples"/"SOOC JPG samples" 폴더), 이 사이트는 애초에 같은 촬영을 짝지어
올린 게 아니라 그냥 각각 다른 사진들이었음 - 10개 카메라, RAW 57장+JPEG
40장을 받았는데 EXIF 촬영시각이 정확히 일치하는 페어는 3쌍뿐(그마저 다
Provia). raw 기반 캘리브레이션(핫셀블라드 v10~v12급)은 포기하고
population 비교로 전환.

Astia/Pro Neg Std에서 실제로 발견한 버그: 둘 다 실측과 정반대로 채도가
올랐음(Astia 실측 -12.9 vs 프리셋 +9.4, Pro Neg Std 실측 -19.4 vs 프리셋
+11.3). 원인은 톤커브를 BGR 채널에 개별로 걸어서(apply_lut) 채널 간
격차가 벌어지며 채도가 재상승하는 것(원본 125.0 -> HSV desaturation 후
109.4 -> BGR별 커브 후 139.7, 원본보다도 높아짐). hasselblad_hncs처럼
Lab L채널에만 커브를 적용하도록 두 프리셋 다 수정. Pro Neg Std는 L채널로
옮긴 뒤에도 여전히 반대 방향이었는데, 커브 모양 자체가 틀렸던 것으로
판명 - 기존엔 대비를 강조하는 S커브(n=1.4)를 썼는데 실측은 Pro Neg Std가
Provia보다 오히려 대비가 낮은 플랫한 프로파일(블랙p2 +2.7, 화이트p99.5
-19.0)이었음. 대비 완화 커브(n=0.65)로 교체. 수정 후 재검증: Astia 1/3
-> 2/3 방향 일치, Pro Neg Std 0/3 -> 3/3 방향 일치.
"""
import cv2
import numpy as np

from core.curve import apply_highlight_rolloff, s_curve
from core.lut import apply_lut


# ==========================================
# 1. Astia/Soft (부드러운 색감, 인물용) - 실측 검증됨
# ==========================================
def apply_astia(img_bgr):
    img = img_bgr.astype(np.float32)
    img[:, :, 2] = np.clip(img[:, :, 2] * 1.03, 0, 255)  # R
    img[:, :, 0] = np.clip(img[:, :, 0] * 0.97, 0, 255)  # B
    img = img.astype(np.uint8)

    img_lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(img_lab)
    # 실측: Astia는 Provia보다 채도가 낮음(부드러운 색감) - a/b를 중심
    # (128)으로 당겨서 채도를 낮춤
    a = np.clip(128 + (a.astype(np.float32) - 128) * 0.85, 0, 255).astype(np.uint8)
    b = np.clip(128 + (b.astype(np.float32) - 128) * 0.85, 0, 255).astype(np.uint8)

    # 하이라이트만 소프트하게 압축 - L채널에만 적용해서 hue/채도 보존
    x = np.arange(256, dtype=np.float32) / 255.0
    y = x.copy()
    y = apply_highlight_rolloff(x, y, start=0.7)
    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


# ==========================================
# 2. PRO Neg. Std (스튜디오 인물용, 부드러움) - 실측 검증됨
# ==========================================
def apply_pro_neg_std(img_bgr):
    img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1] * 0.85, 0, 255)
    img = cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    # 실측: 실제 Pro Neg Std는 Provia보다 대비가 낮은 플랫 프로파일이라
    # n<1(대비 완화) 사용
    x = np.arange(256, dtype=np.float32) / 255.0
    y = s_curve(x, n=0.65)
    lut = np.clip(y * 255, 0, 255).astype(np.uint8)

    # L채널에만 적용해서 desaturation이 유지되도록 함 (BGR 채널별로 걸면
    # 채도가 재상승하는 버그가 있었음)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.LUT(l, lut)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


# ==========================================
# 3. PRO Neg. Hi (Std + 콘트라스트 강화) - 미검증
# ==========================================
def apply_pro_neg_hi(img_bgr):
    img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1] * 0.85, 0, 255)
    img = cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    x = np.arange(256, dtype=np.float32) / 255.0
    y = s_curve(x, n=2.2)

    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    img_curved = apply_lut(img, lut)

    img_lab = cv2.cvtColor(img_curved, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(img_lab)
    clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


# ==========================================
# 4. Eterna/Cinema (영화 느낌, 플랫, 틸 쉐도우) - 미검증
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
# 5. Eterna Bleach Bypass (표백 현상, 저채도 고대비) - 미검증
# ==========================================
def apply_eterna_bleach_bypass(img_bgr):
    img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1] * 0.25, 0, 255)
    img_low_sat = cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    x = np.arange(256, dtype=np.float32) / 255.0
    y = np.clip(x * 1.5 - 0.25, 0, 1)

    lut = (y * 255).astype(np.uint8)
    return apply_lut(img_low_sat, lut)


# ==========================================
# 6. Nostalgic Neg (빈티지, 따뜻한 앰버 강조) - 미검증
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
# 7. Reala Ace (정확한 색 재현, 정직한 룩) - 미검증
# ==========================================
def apply_reala_ace(img_bgr):
    if img_bgr.dtype != np.uint8:
        img_bgr = np.clip(img_bgr * 255, 0, 255).astype(np.uint8)

    img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1] * 0.95, 0, 255)
    img = cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    x = np.arange(256, dtype=np.float32) / 255.0
    y = x.copy()
    y = apply_highlight_rolloff(x, y, start=0.85)

    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    return apply_lut(img, lut)


# ==========================================
# 8. Acros / Monochrome (흑백) - 미검증
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

    x = np.arange(256, dtype=np.float32) / 255.0
    y = s_curve(x, n=1.6)
    y = apply_highlight_rolloff(x, y, start=0.9)

    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    return cv2.LUT(gray, lut)


def apply_monochrome(img_bgr):
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
