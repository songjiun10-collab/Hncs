"""
Olympus(현 OM System) 색감 근사 - population 통계 기반 1차 버전

imaging-resource.com 카메라 리뷰 갤러리에서 미편집 SOOC JPEG를 모아
population 통계를 냈다(analyze 스크립트는 tools/analyze.py의
BRAND_CONFIGS를 건드리지 않고 독립 스크립트로 실행 - Panasonic 브랜드
작업과 동시에 진행 중이라 공용 딕셔너리 충돌을 피하려고 분리함, 로직
자체는 run_imaging_resource_brand()와 동일). DNG/ORF raw 페어는 다른
population-fit 브랜드(라이카/Phase One/Pentax/Ricoh GR/Canon/Sony/
Nikon/Panasonic)와 마찬가지로 이 사이트에서 못 찾아서 population
통계만 사용.

사명 변경 배경: Olympus는 2021년 이미징(카메라) 사업부를 투자펀드에
매각하며 별도 법인 "OM Digital Solutions Corporation"으로 분사했고,
2022년 OM-1부터 제품 브랜드를 "OM System"으로 전환했다(EXIF Make도
이때부터 "OM Digital Solutions"로 바뀜). 그래서 EXIF Make 검증은
"olympus"(구 바디)와 "om digital solutions"(OM-1/OM-5) 둘 다 기대값으로
받아들였다 - 실제로 다운로드한 표본에서 OM-1/OM-5는 Make="OM Digital
Solutions", E-M1 Mark III/E-M1X/PEN-F는 Make="OLYMPUS CORPORATION"으로
정확히 세대에 맞춰 갈렸다. Software에 Photoshop/Lightroom/Capture One/
Camera Raw가 있으면 제3자 편집으로 거절.

바디 선정: imaging-resource.com에서 여러 슬러그 후보(olympus-om-1-review,
olympus-om-1-mark-ii-review 등)를 직접 조회해 실존 여부를 확인 - 존재하지
않는 슬러그는 전부 Fujifilm GFX 100 리뷰 갤러리로 조용히 폴백 리다이렉트되는
동일한 패턴(라이카 T (Typ 701)/Panasonic G9 II 때와 같은 종류의 함정, 응답
자체는 200이라 HTTP 상태코드만으로는 못 거르고 <title> 대조가 필요했음)이라
사이트 검색(`?s=`)으로 실제 슬러그를 재확인해서 골랐다. 최종 확인된 5개
갤러리: OM System OM-1(om-system-om-1-review, 219장 후보), OM System
OM-5(om-system-om-5-review, 93장), Olympus E-M1 Mark III
(olympus-e-m1-mark-iii-review, 최대 503장), Olympus E-M1X
(olympus-e-m1x-review, 최대 553장), Olympus PEN-F(olympus-pen-f-review,
92장) - 최신/구형, 플래그십/스포츠/레트로 스타일이 섞이도록 선택했다.
OM-1 Mark II/OM-5(대체 슬러그)/E-M1 Mark II/E-M10 시리즈/E-PL10/E-P7 등은
슬러그가 없거나(폴백 리다이렉트) 이미 5바디를 확보해서 시도하지 않음.

수집: 바디당 후보 목록에서 최대 25장까지 다운로드+무결성 검증
(core/validation.py is_image_usable()) +genuine SOOC 확인 순으로 진행,
5바디 모두 25장(OM-1/OM-5/E-M1 Mark III는 dedup 전 25장) 근접 확보(총
125장, 다운로드 시도 130회). 편집/기술 테스트샷 필터는 다른 imaging-
resource 브랜드와 동일하게 "edit"/"-mod"/"unsharpmask"/"nosharp"/
"stack"/"-iso-" 키워드를 우선 사용했으나, Olympus E-M1X 갤러리(483장
후보)에서 리뷰어 후보정본이 파일명 접미사 "-EDT"(예:
"152575_Y-50-200-0021-EDT.jpg")로 붙어있어 "edit" 부분문자열과 안 겹쳐
필터를 통과하는 걸 발견 - Panasonic S5의 "-edt" 사례와 동일한 함정이라
skip_keywords에 "-edt"를 추가해 목록 단계에서 걸러냈다(추가 전에는
"-EDT" 버전을 매번 다운로드+genuine_render_check까지 거쳐야 해서 후보
483장 중 상당수가 낭비됐었음).

무결성(is_image_usable): 다운로드 시도 130회 중 5건이 CDN 손상(원본
실패 후 scaled 폴백도 손상, "Premature end of JPEG file")으로 스킵 -
비율로는 약 3.8%, Canon(2%)/Panasonic(0%)보다는 살짝 높지만
Nikon/Pentax(40%)/Phase One(100%)/Hasselblad(72%)에 비하면 크게 낮은
축. genuine SOOC 거절은 0건 - -edt 필터를 목록 단계에서 미리 걸러낸
덕에 다운로드까지 간 파일은 전부 EXIF Make 기대값에 맞고 제3자 편집
흔적이 없었음(skip_keywords로 "-EDT" 걸러내기 전 시행(run 1)에서는
E-M1X 쪽에서 "-EDT" 파일들이 genuine_render_check에서 Photoshop
편집으로 거절되는 걸 다수 확인했었음 - 최종 스크립트에는 그 낭비를
막기 위한 필터만 반영되고 거절 건수 자체는 0으로 수렴).

버스트 중복 제거: Canon EOS R3/Panasonic S1·S5 사례와 동일한 방법
(인접 프레임 번호, w995 차이<=2, 채도 차이<=1.5를 같은 장면으로 판단)으로
점검한 결과 세 바디에서 각 1쌍씩 발견돼 쌍당 1장만 남기고 제외:
OM-1(080353/080354), OM-5(PC020129/PC020131), E-M1 Mark III
(P7060625/P7060626) - 총 3장 제외(125 -> 122). E-M1X/PEN-F에서는 해당
패턴이 발견되지 않았음.

population 통계 (2026-07, 버스트 중복 제거 후 n=122):
  전체:                        블랙p2=14.5(그림자유효 63)  화이트p99.5=232.2  채도=79.2
  OM-1    (n=24, 그림자유효  3): 블랙p2=27.7  화이트p99.5=251.9  채도=50.2
  OM-5    (n=24, 그림자유효 20): 블랙p2=11.9  화이트p99.5=218.9  채도=69.1
  E-M1 III(n=24, 그림자유효 13): 블랙p2=13.6  화이트p99.5=235.7  채도=130.6
  E-M1X   (n=25, 그림자유효 12): 블랙p2=15.7  화이트p99.5=225.3  채도=76.5
  PEN-F   (n=25, 그림자유효 15): 블랙p2=15.1  화이트p99.5=229.4  채도=69.9

OM-1은 그림자유효 표본이 3장뿐이라(24장 중 21장이 dark_pct<=5인 밝은
야외 장면 위주 - 파일명 "Y-JG-OM-1-08xxxx/09xxxx"로 보아 같은 촬영자의
한 세트) 블랙p2=27.7은 표본이 매우 작아 신뢰도가 낮다(Nikon D780의
그림자유효 9/23 사례보다도 더 극단적). 화이트p99.5도 OM-1이 251.9로
가장 밝게 뜨는데 이 역시 같은 밝은 촬영 세트 편향일 가능성이 크다.
E-M1 Mark III는 채도가 130.6으로 유난히 높은데, 이 바디 표본은 갤러리
안에서 25mm/50mm F1.7 렌즈 태그("Y-25_50MMF17-")가 붙은 한 촬영 세트
전부라 - 다른 4바디보다 촬영자/장면 편향 폭이 좁아서일 수 있음. 바디별
편차의 원인(세대차 렌더링 철학 vs 촬영 세트 편향)은 다른 population-fit
브랜드들과 마찬가지로 미확인 - 표본이 더 모일 때까지 전체 population
평균을 타깃으로 사용.

leica.py/phaseone.py/pentax.py/ricoh_gr.py/canon.py/sony.py/nikon.py/
panasonic.py와 동일한 한계: raw 기준선이 없어 population 타깃을
film_curve의 toe_lift/white_point에 직접 대입한 것이고,
shoulder_start/clahe_clip/hue·채도 무조작 가정은 검증 없이 핫셀블라드
기본값을 차용.

raw 기준선 업그레이드 가능성: canon.py/nikon.py에서 이미
mirrorlesscomparison.com과 imaging-resource.com 양쪽에서 raw+jpeg 페어
소스가 이번 population-fit 방식에 쓸 수 없다는 게 확인됐음(RAW/JPEG
폴더가 프레임 페어가 아니거나, imaging-resource.com의 raw 다운로드
링크가 사이트 마이그레이션으로 깨짐). Olympus 전용으로 별도 조사는
하지 않았으나 동일한 사이트 구조적 문제라 population-fit 방식을
유지하기로 결정.
"""
from core.engine import apply_population_fit_look

_TOE_LIFT = 14.5 / 255
_WHITE_POINT = 232.2 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_olympus_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                        white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
