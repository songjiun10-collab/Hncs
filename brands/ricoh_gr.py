"""
Ricoh GR 색감 근사 - population 통계 기반 1차 버전

imaging-resource.com 카메라 리뷰 갤러리(GR III + GR IIIx)에서 미편집
SOOC JPEG를 모았다 (tools/analyze.py ricoh_gr 모드). EXIF Make="RICOH
IMAGING COMPANY, LTD.", Software="RICOH GR III Ver. 1.00" 등 카메라
펌웨어 버전 문자열로 진짜 SOOC 확인 - pentax.py와 같은 회사/같은 EXIF
패턴.

1차 수집(n=40)에서 GR IIIx 쪽에 조리개 브라케팅 테스트샷(-f2.8/-f4.0/
-f8.0 등, 같은 장면을 조리개만 바꿔 반복 촬영, 총 6장)이 섞여 있었음 -
Phase One의 ISO 차트와 같은 종류의 문제라 파일명 정규식으로 걸러내고
재계산 (tools/analyze.py의 스킵 패턴에도 반영해서 다음 실행부터는
자동으로 빠짐). 영향은 Phase One 때보다 작았음(채도 87.7 -> 84.9,
표본 비중이 15%로 ISO 테스트의 30%보다 적었기 때문).

population 통계 (2026-07, n=34, f값 테스트 제외):
  전체:            블랙p2=10.3  화이트p99.5=243.9  채도=84.9
  GR III (n=20):   블랙p2=11.1  화이트p99.5=245.8  채도=78.3

무결성 검증(2026-07, core/validation.py is_image_usable() 적용): 같은
imaging-resource.com에서 Hasselblad/Phase One/Pentax 갤러리가 CDN 자체
손상 문제를 갖고 있던 게 드러나서 이 40장(f값 테스트 포함)도 재검증
했음 - 전부 행 단위 손상 없이 정상. 위 수치 변경 없음.

leica.py/phaseone.py/pentax.py와 동일한 한계: raw 기준선이 없어
population 타깃을 film_curve의 toe_lift/white_point에 직접 대입,
shoulder_start/clahe_clip/hue·채도 무조작 가정은 미검증.
"""
from core.engine import apply_population_fit_look

_TOE_LIFT = 10.3 / 255
_WHITE_POINT = 243.9 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_ricoh_gr_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                         white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
