"""
Ricoh GR 색감 근사 - population 통계 기반 1차 버전

imaging-resource.com 카메라 리뷰 갤러리(GR III + GR IIIx)에서 미편집
SOOC JPEG를 모았다 (analyze_ricoh_gr_samples.py). EXIF Make="RICOH
IMAGING COMPANY, LTD.", Software="RICOH GR III Ver. 1.00" 등 카메라
펌웨어 버전 문자열로 진짜 SOOC 확인 - pentax_color.py와 같은 회사/같은
EXIF 패턴.

1차 수집(n=40)에서 GR IIIx 쪽에 조리개 브라케팅 테스트샷(-f2.8/-f4.0/
-f8.0 등, 같은 장면을 조리개만 바꿔 반복 촬영, 총 6장)이 섞여 있었음 -
Phase One의 ISO 차트와 같은 종류의 문제라 파일명 정규식으로 걸러내고
재계산 (`analyze_ricoh_gr_samples.py`의 SKIP_PATTERN에도 반영해서
다음 실행부터는 자동으로 빠짐). 영향은 Phase One 때보다 작았음
(채도 87.7 -> 84.9, 표본 비중이 15%로 ISO 테스트의 30%보다 적었기 때문).

population 통계 (2026-07, n=34, f값 테스트 제외):
  전체:            블랙p2=10.3  화이트p99.5=243.9  채도=84.9
  GR III (n=20):   블랙p2=11.1  화이트p99.5=245.8  채도=78.3
  GR IIIx(n=14):   블랙p2 등 세부 재계산 안 함(GR IIIx만 6장 빠짐, 전체
                    타깃은 위 통합값 사용)

leica_color.py/phaseone_color.py/pentax_color.py와 동일한 한계: raw
기준선이 없어 population 타깃을 `_film_curve`의 toe_lift/white_point에
직접 대입, shoulder_start/clahe_clip/hue·채도 무조작 가정은 미검증.
"""
import cv2
import numpy as np

from hasselblad_hncs import _film_curve

_TOE_LIFT = 10.3 / 255
_WHITE_POINT = 243.9 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_ricoh_gr_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                         white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(_film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
