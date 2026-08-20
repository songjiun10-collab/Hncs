"""
apply_hasselblad_night - Legacy. 원래 brands/hasselblad.py 한 파일에
apply_hasselblad_day와 같이 있었는데("day/night" 섹션), "공식
채택(apply_hncs) vs 레거시(day/night 별도 프리셋)"를 가르려고 분리했다.
Legacy로 표시하는 이유는 brands/hasselblad_day.py docstring 참고 (v1 극단
스타일이 표본 부족 때문이었다는 배경도 그쪽에 있음).
"""
import cv2
import numpy as np

from core.curve import s_curve


def apply_hasselblad_night(
    img_bgr,
    black_out=0.02,      # v1: 0.07 (한강1장) -> 4장 풀링 시 축소
    white_out=0.88,      # v1: 0.65 -> 밤 타깃도 낮과 거의 같아 대폭 완화
    saturation=1.08,   # 실측 교훈: 핫셀 야경은 채도가 살아있는 압축 톤 (억제 아님)
    contrast_n=1.2,
    exposure_gamma=None, # None이면 자동 노출 정규화 (중앙명도 -> 0.18, 순흑 프레임일 땐 0.21로 가정)
):
    """
    v2: 공식 night 샘플 4장 실측 (야간교량/도심야경자동차/유목해변/
    포르쉐주차장, 전부 그림자유효). 타깃 블랙p2=15.0, 화이트p99.5=228.5
    -> black_out 0.07->0.02, white_out 0.65->0.88. 재현: 블랙p2=14.2
    (목표15.0), 화이트p99.5=228.8(목표228.5).

    v3 (2026-07, 표본 확대): 공식 샘플 풀 124장을 육안 콘택트시트 검토로
    재분류(포르쉐주차장 포함 12장이 확실한 야간 - 가로등/네온/오로라/
    은하수/도심야경 등). 새 타깃 블랙p2=9.7, 화이트p99.5=221.3 (12장,
    전부 그림자유효) -> 그리드서치 결과 기존 기본값(black_out=0.02,
    white_out=0.88)이 그대로 최적으로 나옴(RMSE 20.61, 변경 없음).
    apply_hasselblad_day(brands/hasselblad_day.py)의 v3 재보정과 마찬가지로
    이 새 타깃도 전체 population 타깃(v9: 11.3/223.9, brands/hasselblad.py
    참고)에 가까워서 day/night 통합 근거가 더 강해짐.
    """
    # --- 0+1. 노출 정규화 + S커브를 모두 L채널에서 (색 보존) ---
    # BGR 감마 리프트는 min채널을 상대적으로 더 올려 채도를 죽임 -> L에서 수행
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    if exposure_gamma is None:
        valid = l[l > 3]  # 순흑 프레임 제외
        med = np.median(valid) / 255.0 if valid.size else 0.21
        exposure_gamma = float(np.clip(np.log(0.18) / np.log(max(med, 1e-4)), 0.35, 1.0))
    x = np.arange(256, dtype=np.float32) / 255.0
    y = s_curve(x ** exposure_gamma, n=contrast_n)
    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)
    img_u8 = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

    # --- 2. 채도 (hue 불변) ---
    hsv = cv2.cvtColor(img_u8, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * saturation, 0, 255)
    img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32) / 255.0

    # --- 3. DR 중앙 압축 (핵심): BGR 전 채널 [0,1] -> [black,white] ---
    # smoothstep 숄더로 상단 부드럽게 (하드클립 없이 white_out으로 수렴)
    hl = img > 0.6
    t = (img[hl] - 0.6) / 0.4
    img[hl] = 0.6 + (t * t * (3 - 2 * t)) * (white_out + 0.05 - 0.6)  # 최상단 광원만 white_out 약간 초과 허용
    img = black_out + img * (1.0 - black_out)

    return np.clip(img * 255, 0, 255).astype(np.uint8)
