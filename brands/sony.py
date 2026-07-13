"""
Sony 색감 근사 - population 통계 기반 1차 버전

imaging-resource.com 카메라 리뷰 갤러리 5개 바디(A7/A7R/A7S/A7 III/A7 IV)에서
미편집 SOOC JPEG를 모았다 (tools/analyze.py의 BRAND_CONFIGS 구조를 그대로
따르되, Canon/Nikon 작업과의 동시편집 충돌을 피하려고 별도 스크립트로 수집).
EXIF Make에 "sony" 포함, Software에 Photoshop/Lightroom/Capture One/
Camera Raw 없는 것으로 진짜 SOOC 확인 - leica.py/pentax.py/ricoh_gr.py와
같은 EXIF 검증 원칙.

수집 과정에서 겪은 문제들:
- A7 IV 갤러리(481장 후보, 표본이 가장 큼)는 1차 시도에서 목록 페이지
  자체가 "Connection reset by peer"로 실패 - exponential backoff로 재시도해서
  성공(6번째 시도 이내). 이후 원본 다운로드 단계에서도 CDN 손상
  ("Premature end of JPEG file")이 특히 잦아서(약 14장) scaled 폴백으로도
  못 살린 경우가 많았음 - Hasselblad/Phase One/Pentax 때 확인된 것과 같은
  media.imaging-resource.com 자체 CDN 손상 문제(core/validation.py
  is_image_usable() docstring 참고).
- A7 IV 렌즈테스트 서브갤러리 두 곳(태그가 다른 -TAMRON-28-75-0182 /
  -SONY-A7-IV-0182)에 프레임 번호가 우연히 같은 게 아니라 완전히 동일한
  파일(md5 일치)이 두 렌즈 테스트 묶음에 중복 게재돼 있었음 - 1장 제거.
- A7S 갤러리에 노이즈리덕션 설정 비교샷 3연속(YDSC00476-NRNORM/
  00477-NRLOW/00478-NR0, 같은 장면을 NR 설정만 바꿔 반복 촬영)과 JPEG
  품질모드 테스트샷(YDSC00443-extrafine) 1장이 섞여 있었음 - Phase One의
  ISO 노이즈 차트, Ricoh GR IIIx의 조리개 브라케팅과 같은 종류의 대표성
  없는 기술 테스트샷이라 전부 제외(스킵 키워드에 "-extrafine"/"-nrnorm"/
  "-nrlow"/"-nr0" 추가).
- 위 두 문제로 제거한 5장(A7 IV 1장 + A7S 4장)은 같은 갤러리에서 새 후보로
  백필해서 바디당 n=23을 맞춤. 백필 후 전체 115장에 대해 md5 기준
  콘텐츠 중복 재검사 - 남은 중복 없음.
- 무결성 검증(core/validation.py is_image_usable())과 EXIF 진위 검증
  (genuine_render_check)은 다른 population-fit 브랜드와 동일하게 다운로드한
  모든 파일에 적용. EXIF 거절(비-Sony 렌더러 또는 Photoshop 등 편집 흔적)로
  스킵된 파일이 A7 IV 렌즈테스트 세트에서 특히 많았음(리뷰어가 원본 옆에
  "-EDT" 접미사의 편집본을 같이 올려둔 경우가 많아서 - "edit" 키워드로
  자동 스킵됨).

population 통계 (2026-07, n=115, 바디당 23장):
  전체:              블랙p2=9.1(그림자유효 98)  화이트p99.5=228.6  채도=97.6
  A7    (2013,n=23):   블랙p2=9.7   화이트p99.5=243.5  채도= 95.0
  A7R   (2013,n=23):   블랙p2=7.7   화이트p99.5=232.3  채도=106.9
  A7S   (2014,n=23):   블랙p2=8.9   화이트p99.5=245.5  채도=118.2
  A7 III(2018,n=23):   블랙p2=10.7  화이트p99.5=185.3  채도= 91.8
  A7 IV (2021,n=23):   블랙p2=8.9   화이트p99.5=236.5  채도= 76.0

A7 III의 화이트p99.5(185.3)이 나머지 바디(232~245)보다 눈에 띄게 낮음 -
원인을 살펴보니 리뷰 표본이 105mm/28-200mm 렌즈 테스트용 실내 저대비
피사체 위주로 많이 잡혀 있었음(md5로 중복은 아님을 확인했고 전부 서로 다른
사진). 카메라 자체의 렌더링 차이인지 이 리뷰 회차의 촬영 장소/피사체
편향인지는 구분할 근거가 없어 원인 미확인.

세대별로 보면 A7S(2014, 저조도 특화 바디)가 채도 118.2로 가장 높고, 최신
A7 IV(2021)가 76.0으로 가장 낮음 - 그림자유효 비중도 A7S/A7 20장대에서
A7 IV는 15/23으로 줄어듦(밝은 실내 렌즈테스트 장면 비중이 큼). 단조로운
"세대가 갈수록 채도가 낮아진다"는 서사로 단정하기엔 표본이 리뷰어 1인,
촬영 세트(A7 IV는 특히 렌즈 테스트 위주)에 크게 좌우될 수 있어 확실하지
않음 - leica.py의 M9-vs-SL2 관찰과 같은 종류의 한계.

leica.py/phaseone.py/pentax.py/ricoh_gr.py와 동일한 한계: raw 기준선이
없어 population 타깃을 film_curve의 toe_lift/white_point에 직접 대입한
것이고, shoulder_start/clahe_clip/hue·채도 무조작 가정은 검증 없이
핫셀블라드 기본값을 차용.

raw 기준선 업그레이드 가능성 조사(2026-07): mirrorlesscomparison.com과
imaging-resource.com 양쪽에서 Sony raw+jpeg 페어 소스를 재확인했으나
둘 다 불가로 결론(canon.py 참고 - 동일 조사를 세 브랜드 공통으로 진행).
mirrorlesscomparison.com은 Fuji 때와 같은 이유(RAW/JPEG 폴더가 같은
프레임 페어가 아님)로 population-fit용 캘리브레이션에 못 씀 - 이
사이트엔 A7/A7 II/A7 III/A7R II/A7R III/A7R IV/A7S 갤러리가 있지만
population-fit에 쓴 A7 IV는 아예 없고, 겹치는 바디(A7/A7 III/A7S)도
페어링 자체가 안 되는 구조적 문제라 무의미. imaging-resource.com의
raw 다운로드 링크는 사이트 마이그레이션으로 죽어서 사용 불가. 억지로
raw 기준선을 만들 근거가 없어 population-fit 방식을 유지하기로 결정.
"""
from core.engine import apply_population_fit_look

_TOE_LIFT = 9.1 / 255
_WHITE_POINT = 228.6 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_sony_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                     white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
