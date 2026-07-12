"""
핫셀 주간 매칭 (v2, 2026-07): 공식 샘플 풀(19장) 중 낮 장면 5장 실측
(아이슬란드폭포, 타워브리지, 숲개울인물, 드레스인물, 풀숲나비)

*** 중요 발견: v1은 홍콩 3장(출처 불확실)으로 "무디 그레이딩"을 학습했으나,
공식 샘플로 재검증하니 낮/밤 타깃이 거의 수렴함(blackp2 13.4 vs 밤 15.0,
화이트 230.2 vs 밤 228.5) - v1의 강한 미드톤 다운(gamma1.18)+깊은 대비는
"X1D 낮 특성"이 아니라 그 사진가 개인 스타일이었을 가능성이 높음.
이번 버전은 gamma를 1.0 근처로 되돌려 과도한 무디함을 제거함.

타깃: 블랙p2=13.4, 화이트p99.5=230.2 (그림자유효 5장/전체 8장)
-> midtone_gamma=1.18->0.95, white_point=0.94->0.96, contrast_n=1.35->1.15
   재현: 블랙p2=12.8(목표13.4), 화이트p99.5=231.0(목표230.2)
"""
import cv2
import numpy as np
from film_sim_presets import _s_curve, _apply_highlight_rolloff


def apply_hasselblad_day(
    img_bgr,
    midtone_gamma=0.95,
    contrast_n=1.15,
    white_point=0.96,
    rolloff_start=0.80,
    saturation=1.0,
    clahe_clip=1.3,
):
    # --- 톤: 전부 L채널 (색 보존 구조) ---
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    x = np.arange(256, dtype=np.float32) / 255.0
    y = x ** midtone_gamma          # 미드톤 다운
    y = _s_curve(y, n=contrast_n)   # 깊은 블랙 + 대비
    y = _apply_highlight_rolloff(x, y, start=rolloff_start)
    y = y * white_point             # 화이트포인트 압축
    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    # 마이크로 콘트라스트 (레퍼런스의 살아있는 텍스처)
    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    img_u8 = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

    # --- 채도 (hue 불변) ---
    if saturation != 1.0:
        hsv = cv2.cvtColor(img_u8, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] * saturation, 0, 255)
        img_u8 = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    return img_u8
