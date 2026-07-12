"""
핫셀 야경 매칭 (v2, 2026-07): 공식 샘플 풀(19장) 중 밤 장면 4장 실측
(야간교량, 도심야경자동차, 유목해변, 포르쉐주차장)

*** day.py와 동일한 발견: v1은 한강 1장(출처 불확실)만으로 "DR 중앙압축"을
학습했으나, 공식 4장으로 재검증하니 낮 타깃(13.4/230.2)과 거의 수렴
(15.0/228.5) - v1의 강한 블랙리프트(black_out0.07)+화이트압축(white_out0.65)은
그 사진 1장의 그레이딩이었을 가능성이 높음. 이번 버전은 대부분 되돌림.

타깃: 블랙p2=15.0, 화이트p99.5=228.5 (4장 전체, 다 그림자 유효)
-> black_out=0.07->0.02, white_out=0.65->0.88
   재현: 블랙p2=14.2(목표15.0), 화이트p99.5=228.8(목표228.5)

이 결과로 day/night를 별개 프리셋으로 유지할 근거가 약해졌음 - 다음 단계로
둘을 hncs에 통합 검토 필요.
"""
import cv2
import numpy as np
from film_sim_presets import _s_curve


def apply_hasselblad_night(
    img_bgr,
    black_out=0.02,      # v1: 0.07 (한강1장) -> 4장 풀링 시 축소
    white_out=0.88,      # v1: 0.65 -> 밤 타깃도 낮과 거의 같아 대폭 완화
    saturation=1.08,   # 실측 교훈: 핫셀 야경은 채도가 살아있는 압축 톤 (억제 아님)
    contrast_n=1.2,
    exposure_gamma=None, # None이면 자동 노출 정규화 (중앙명도 -> 0.21)
):
    # --- 0+1. 노출 정규화 + S커브를 모두 L채널에서 (색 보존) ---
    # BGR 감마 리프트는 min채널을 상대적으로 더 올려 채도를 죽임 -> L에서 수행
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    if exposure_gamma is None:
        valid = l[l > 3]  # 순흑 프레임 제외
        med = np.median(valid) / 255.0 if valid.size else 0.21
        exposure_gamma = float(np.clip(np.log(0.18) / np.log(max(med, 1e-4)), 0.35, 1.0))
    x = np.arange(256, dtype=np.float32) / 255.0
    y = _s_curve(x ** exposure_gamma, n=contrast_n)
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
