"""
apply_hasselblad_day - Legacy. 원래 brands/hasselblad.py 한 파일에
apply_hasselblad_night과 같이 있었는데("day/night" 섹션), "공식
채택(apply_hncs) vs 레거시(day/night 별도 프리셋)"를 가르려고 분리했다.
Legacy로 표시하는 이유: v3 재보정 결과 day 타깃이 apply_hncs의 전체
population 타깃에 거의 수렴해서, 별도 프리셋으로 유지할 근거가 계속
약해지는 중이기 때문(아래 참고, 아직 apply_hncs로 통합은 안 함).

v1(day: 홍콩 3장, night: 한강 1장, 출처 불확실)로 만든 강한 그레이딩은
공식 샘플로 재검증하니 낮/밤 타깃이 거의 수렴함(day blackp2 13.4 vs
night 15.0, 화이트 230.2 vs 228.5) - v1의 극단적 스타일은 "X1D 낮/밤
특성"이 아니라 그 사진 1~3장의 그레이딩(혹은 사진가 개인 스타일)이었을
가능성이 높음. v2(아래)는 공식 day 5장/night 4장 실측으로 되돌린 버전.
"""
import cv2
import numpy as np

from core.curve import s_curve, apply_highlight_rolloff


def apply_hasselblad_day(
    img_bgr,
    midtone_gamma=0.85,
    contrast_n=1.35,
    white_point=0.92,
    rolloff_start=0.80,
    saturation=1.0,
    clahe_clip=1.3,
):
    """
    v2: 공식 day 샘플 5장 실측 (아이슬란드폭포/타워브리지/숲개울인물/
    드레스인물/풀숲나비). 타깃 블랙p2=13.4, 화이트p99.5=230.2 (그림자유효
    5장/전체 8장) -> midtone_gamma 1.18->0.95, white_point 0.94->0.96,
    contrast_n 1.35->1.15. 재현: 블랙p2=12.8(목표13.4), 화이트p99.5=231.0
    (목표230.2).

    v3 (2026-07, 표본 확대): 공식 샘플 풀 124장을 실제로 한 장씩 육안
    검토해서(콘택트시트) 확실한 야간 장면 12장(가로등/네온/오로라/은하수/
    도심야경 등)을 골라내고 나머지 112장을 day로 재분류 - v2는 8장뿐이던
    표본이 124장으로 늘어남. 새 타깃: 블랙p2=11.5, 화이트p99.5=224.1
    (day 112장 기준) -> midtone_gamma 0.95->0.85, contrast_n 1.15->1.35,
    white_point 0.96->0.92 (rolloff_start/saturation/clahe_clip은 그대로).
    day 40장 서브샘플 그리드서치 RMSE 22.01->18.65.

    day(11.5/224.1)와 night(9.7/221.3, brands/hasselblad_night.py 참고)이
    v2 때보다 더 수렴함 - 핫셀블라드 전체 population 타깃(v9: 11.3/223.9,
    brands/hasselblad.py 참고)과도 거의 같은 값이라, day/night를 별개
    프리셋으로 유지할 근거가 계속 약해지고 있음(아직 apply_hncs로 통합은
    안 함 - 통합하면 이 함수가 없어지므로 별도 작업으로 결정 필요).
    """
    # --- 톤: 전부 L채널 (색 보존 구조) ---
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    x = np.arange(256, dtype=np.float32) / 255.0
    y = x ** midtone_gamma          # 미드톤 다운
    y = s_curve(y, n=contrast_n)    # 깊은 블랙 + 대비
    y = apply_highlight_rolloff(x, y, start=rolloff_start)
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
