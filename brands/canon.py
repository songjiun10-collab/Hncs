"""
Canon 색감 근사 - population 통계 기반 1차 버전

imaging-resource.com 카메라 리뷰 갤러리(EOS R5/R6/R8/R3/R, 풀프레임
미러리스 5개 바디)에서 미편집 SOOC JPEG를 모아 population 통계를 냈다
(analyze 스크립트는 tools/analyze.py의 BRAND_CONFIGS를 건드리지 않고
독립 스크립트로 실행 - Sony/Nikon 브랜드 작업과 동시에 진행 중이라
공용 딕셔너리 충돌을 피하려고 분리함, 로직 자체는
run_imaging_resource_brand()와 동일). EXIF Make="Canon", Software에
Photoshop/Lightroom/Capture One/Camera Raw가 없는 것으로 진짜 SOOC
확인. DNG/CR2 raw 페어는 다른 population-fit 브랜드(라이카/Phase One/
Pentax/Ricoh GR)와 마찬가지로 이 사이트에서 못 찾아서 population
통계만 사용.

수집: 바디당 후보 목록에서 최대 25장까지 다운로드+무결성 검증
(core/validation.py is_image_usable()) +genuine SOOC 확인 순으로 진행,
바디당 25장 확보(총 125장). 편집/기술 테스트샷 필터는 다른 imaging-
resource 브랜드와 동일하게 "edit"/"-mod"/"unsharpmask"/"nosharp"/
"stack"/"-iso-"/조리개 브라케팅(-f\\d) 키워드 사용.

무결성(is_image_usable): 125장 중 3장만 CDN 손상(원본 실패 후 scaled
폴백도 손상)으로 스킵 - Pentax(40장 중 16장)/Phase One(1차 30/30)/
Hasselblad(72%)에 비해 손상률이 눈에 띄게 낮았음(약 2%, 후보 128회
시도 중). genuine SOOC 거절(Photoshop 등 편집 감지)은 0건 - 다운로드
성공한 것은 전부 EXIF Make="Canon"에 제3자 편집 흔적 없음.

버스트 중복 제거: EOS R3(스포츠/액션 지향 바디) 표본에서 연속 프레임
번호(0K1A2207/2220, 0K1A2230/2231, 0K1A2483~2489 등)가 화이트p99.5/
채도 값이 소수점 단위까지 거의 동일한 걸 발견 - 같은 정지 장면을
연사로 찍은 버스트 시퀀스로 보임(Phase One의 ISO 차트, Ricoh GR의
조리개 브라케팅/HDR 비교샷과 같은 종류의 "장면 반복" 문제, 다만
파일명이 아니라 연속 프레임 통계 유사성으로 발견됨). 인접 프레임의
w995 차이<=2, 채도 차이<=1.5인 구간을 같은 장면으로 보고 구간당 1장만
남기고 나머지를 제외 - R3 25장 중 8장(2개 구간, 각 2장/7장) 제외,
EOS R에서도 2쌍(각 2장) 제외돼 총 10장 빠짐(125 -> 115). R3 채도가
유난히 낮았던(74.7) 이유가 이 중복 버스트 구간(채도 69~78대로 균일)
비중이 커서였던 것으로 보이는데, 제외 후에도 R3 채도(74.5)는 크게
안 바뀜 - 즉 R3 자체가 다른 바디보다 채도가 낮게 렌더링되는 경향은
유지되는 것으로 보이나 표본이 작아(dedup 후 n=17) 확정하긴 이름.

population 통계 (2026-07, 버스트 중복 제거 후 n=115):
  전체:           블랙p2=15.0(그림자유효 82)  화이트p99.5=239.1  채도=89.8
  EOS R5 (n=25):  블랙p2=12.9  화이트p99.5=236.2  채도=98.4
  EOS R6 (n=25):  블랙p2=14.5  화이트p99.5=235.7  채도=104.9
  EOS R8 (n=25):  블랙p2=19.3  화이트p99.5=241.2  채도=76.6
  EOS R3 (n=17):  블랙p2=16.7  화이트p99.5=240.6  채도=74.5  (버스트 제거 후)
  EOS R  (n=23):  블랙p2=12.6  화이트p99.5=242.4  채도=89.7  (2018, 가장 오래된 바디)

바디별로 보면 최신 보급형(R8)/스포츠형(R3)이 블랙p2가 높고(그림자를
덜 눌러 밝게 뜨는 쪽) 채도는 오히려 낮은 반면, R5/R6/초기형 EOS R은
블랙p2가 낮고 채도가 높은 경향이 갈린다 - 세대나 등급별 렌더링 철학
차이일 수도, 촬영 장소/피사체(리뷰어가 바디마다 다른 장면을 찍음)에
의한 표본 편향일 수도 있어 원인은 미확인. 표본이 더 모일 때까지
전체 population 평균을 타깃으로 사용.

leica.py/phaseone.py/pentax.py/ricoh_gr.py와 동일한 한계: raw
기준선이 없어 population 타깃을 film_curve의 toe_lift/white_point에
직접 대입한 것이고, shoulder_start/clahe_clip/hue·채도 무조작 가정은
검증 없이 핫셀블라드 기본값을 차용.
"""
from core.engine import apply_population_fit_look

_TOE_LIFT = 15.0 / 255
_WHITE_POINT = 239.1 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_canon_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                      white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
