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

표본 확대(2026-07): 같은 회사/같은 GR 라인업인 GR(1세대, 2013)과
GR II(2015) 갤러리를 추가로 찾아서(각 20장) n=34->80으로 확대. GR II
쪽에 HDR 효과 on/off 비교샷(같은 장면 반복, "-effect"/"-no-effect"
파일명 2장)이 섞여있어 f값 테스트와 같은 방식으로 필터링. Phase One
XT 때와 달리 GR 라인업은 전부 컬러 APS-C 콤팩트라 흑백 전용 백 같은
이종 카메라 혼입 위험은 없었음.

  전체(n=80):         블랙p2=8.4   화이트p99.5=245.2  채도=91.4
  GR III (n=20):      블랙p2=11.1  화이트p99.5=245.8  채도=78.3  (변경 없음)
  GR IIIx (n=20):     블랙p2=10.3  화이트p99.5=244.2  채도=92.3
  GR (n=20):          블랙p2=7.5   화이트p99.5=245.1  채도=86.2
  GR II (n=20):       블랙p2=4.7   화이트p99.5=245.7  채도=108.9

GR II가 블랙p2가 눈에 띄게 낮음(4.7, 나머지는 7.5~11.1) - 초기 센서
세대라 그림자 렌더링이 다를 수도, 표본(리뷰어 1인, 촬영지)에 의한
차이일 수도 있어 원인 미확인. 이 확대된 전체 population(n=80)을 최종
타깃으로 채택.

leica.py/phaseone.py/pentax.py와 동일한 한계: raw 기준선이 없어
population 타깃을 film_curve의 toe_lift/white_point에 직접 대입,
shoulder_start/clahe_clip/hue·채도 무조작 가정은 미검증.
"""
from core.engine import apply_population_fit_look

_TOE_LIFT = 8.4 / 255
_WHITE_POINT = 245.2 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_ricoh_gr_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                         white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
