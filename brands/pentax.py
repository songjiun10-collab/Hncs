"""
Pentax(리코이미징) 색감 근사 - population 통계 기반 1차 버전

imaging-resource.com 카메라 리뷰 갤러리(645Z 중형포맷 + K-1 풀프레임)에서
미편집 SOOC JPEG 40장을 모아 population 통계를 냈다 (tools/analyze.py
pentax 모드). EXIF Make="RICOH IMAGING COMPANY, LTD.", Software가 카메라
펌웨어 버전 문자열("PENTAX 645Z Ver. 1.00" 등)인 것으로 진짜 SOOC 확인.
DNG 페어는 라이카/Phase One 때와 마찬가지로 이 사이트에서 못 찾아서
population 통계만 사용.

population 통계 (2026-07, n=40):
  전체:          블랙p2=10.8  화이트p99.5=239.1  채도=124.1
  645Z (n=20):   블랙p2=10.4  화이트p99.5=247.2  채도=141.1  (중형포맷)
  K-1  (n=20):   블랙p2=11.1  화이트p99.5=231.0  채도=107.1  (풀프레임)

두 바디가 블랙포인트는 거의 같은데 645Z가 화이트/채도 둘 다 더 높음 -
중형포맷 특유의 DR/색 재현 차이일 수도, 표본(리뷰어 1인, 촬영 장소도
갈릴 수 있음)에 의한 차이일 수도 있어 원인은 미확인. 표본이 더 모일
때까지 전체 평균을 타깃으로 사용.

leica.py/phaseone.py와 동일한 한계: raw 기준선이 없어 population 타깃을
film_curve의 toe_lift/white_point에 직접 대입한 것이고, shoulder_start/
clahe_clip/hue·채도 무조작 가정은 검증 없이 핫셀블라드 기본값을 차용.
"""
from core.engine import apply_population_fit_look

_TOE_LIFT = 10.8 / 255
_WHITE_POINT = 239.1 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_pentax_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                       white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
