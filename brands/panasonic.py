"""
Panasonic(Lumix) 색감 근사 - population 통계 기반 1차 버전

imaging-resource.com 카메라 리뷰 갤러리에서 미편집 SOOC JPEG를 모아
population 통계를 냈다(analyze 스크립트는 tools/analyze.py의
BRAND_CONFIGS를 건드리지 않고 독립 스크립트로 실행 - Olympus 브랜드
작업과 동시에 진행 중이라 공용 딕셔너리 충돌을 피하려고 분리함, 로직
자체는 run_imaging_resource_brand()와 동일). 마이크로포서드(GH/G
시리즈) + 풀프레임(S 시리즈) 갤러리를 섞어 5개 바디(GH5/GH6/G9/S5/S1)를
골랐다. EXIF Make="Panasonic"(Camera Model Name은 "DC-GH5"/"DC-GH6"/
"DC-G9"/"DC-S5"/"DC-S1" 등)으로 진짜 SOOC 확인, Software에 Photoshop/
Lightroom/Capture One/Camera Raw가 있으면 제3자 편집으로 거절. DNG raw
페어는 다른 population-fit 브랜드(라이카/Phase One/Pentax/Ricoh GR/
Canon/Sony/Nikon)와 마찬가지로 이 사이트에서 못 찾아서 population
통계만 사용.

바디 선정: imaging-resource.com에 갤러리가 있는 후보를 URL 직접 조회로
확인(200 vs 존재하지 않는 슬러그의 폴백 리다이렉트 302/301 구분) -
GH5/GH5 II/GH6/G9/S5/S1/S1R 갤러리는 실존(각 48~376장 후보), G9 II/
S5 II/S5 IIX는 리뷰 본문 페이지(`/cameras/*-review/`)는 있지만
`/gallery/` 서브페이지가 없어(301 폴백 또는 갤러리 링크 자체 부재)
후보 갤러리가 없는 것으로 결론 - 신형 바디일수록 갤러리 페이지가
아예 없는 패턴은 Nikon Z9(갤러리는 있지만 죽어있음)와는 또 다른
종류의 결함. GH5 II(48장 후보)와 S1R(376장 후보)도 유효했지만 과제
지침(3~5개 바디)에 맞춰 세대/포맷 균형(MFT 2017~2022세대 3개 +
풀프레임 2019~2020세대 2개)이 잡히는 5개만 선택하고 나머지는 향후
표본 확대 후보로 남겼다.

수집: 바디당 후보 목록에서 최대 25장까지 다운로드+무결성 검증
(core/validation.py is_image_usable()) +genuine SOOC 확인 순으로 진행,
5바디 모두 25장씩 확보(총 125장). 편집/기술 테스트샷 필터는 다른
imaging-resource 브랜드와 동일하게 "edit"/"-mod"/"unsharpmask"/
"nosharp"/"stack"/"-iso-" 키워드 사용(조리개 브라케팅 패턴은 이번
갤러리들에서 발견되지 않아 미적용).

무결성(is_image_usable): 125회 다운로드 시도 중 CDN 손상 0건 - Canon
(2%)보다도 낮고 Pentax(40%)/Phase One(100%)/Hasselblad(72%)와는 확연히
대조적. genuine SOOC 거절 23건은 전부 Photoshop 편집 감지(EXIF
Software) - filename 필터에 안 걸리는 두 가지 브랜드 고유 접미사를
새로 확인함: GH5의 "-ED"(12건, 예:
"83502_YC-200mm-1-4x-1478-ED.jpg")와 S5의 "-edt"(11건, 예:
"67011_Y-DP-0324-edt.jpg") - 둘 다 skip_keywords의 "edit" 부분문자열과
안 겹쳐서(하이픈+ED/edt) 파일명 필터를 통과했지만 genuine_render_check
(EXIF Software="Adobe Photoshop ...")가 정상적으로 거절했음. Nikon
Z9/D850의 "죽어있는 자리표시자 이미지"와는 다른 종류지만, 같은 교훈
(파일명 키워드만으로는 리뷰어 후보정본을 다 못 거른다) - genuine_render_check
가 최종 방어선 역할을 제대로 했다.

버스트 중복 제거: Canon EOS R3 사례와 동일한 방법(인접 프레임 번호,
w995 차이<=2, 채도 차이<=1.5를 같은 장면으로 판단)으로 재점검한 결과
S1과 S5에서 발견됨 - S1은 세 쌍(0156/0157, 0178/0180, 9364/9367,
각 구간 2장)에서 구간당 1장씩 총 3장 제외(25 -> 22), S5는 한 구간
(0458/0459/0460, 연속 3프레임 - b2/w995/채도가 소수점 단위까지 거의
동일: b2=89/89/89, w995=233/234/233, 채도=36.4/35.7/35.6)에서 1장만
남기고 2장 제외(25 -> 23). GH5/GH6/G9에서는 해당 패턴이 발견되지
않았음. 총 5장 제외(125 -> 120). G9 갤러리의 "-AUTOFOCUS"/
"-WHITE-BALANCE"/"-SHADOWS" 접미사 파일들은 프레임 번호와 통계값이
서로 충분히 달라(리뷰어가 카메라 기능 테스트 중 찍은 서로 다른 장면들로
보임) 버스트로 보지 않고 그대로 유지했다 - Sony A7S NR/품질 비교샷과
달리 "같은 장면 반복"이 아니라 "다른 장면, 다른 테스트 카테고리 라벨"
이었음.

population 통계 (2026-07, 버스트 중복 제거 후 n=120):
  전체:                  블랙p2=13.4(그림자유효 82)  화이트p99.5=223.2  채도=102.4
  GH5 (n=25, MFT):       블랙p2=16.9  화이트p99.5=204.4  채도=113.6  (그림자유효 13)
  GH6 (n=25, MFT):       블랙p2= 9.4  화이트p99.5=240.0  채도=102.3  (그림자유효 24)
  G9  (n=25, MFT):       블랙p2=16.8  화이트p99.5=241.0  채도= 64.6  (그림자유효 14)
  S5  (n=23, 풀프레임, dedup 후): 블랙p2=13.7  화이트p99.5=184.2  채도=140.3  (그림자유효 17)
  S1  (n=22, 풀프레임, dedup 후): 블랙p2=13.4  화이트p99.5=245.8  채도= 92.9  (그림자유효 14)

마이크로포서드(GH5/GH6/G9) vs 풀프레임(S5/S1) 센서 포맷 차이가 population
수치에 깔끔하게 나타나지는 않았다 - 화이트p99.5만 봐도 MFT 안에서도
GH5(204.4)와 GH6/G9(240~241)가 크게 갈리고, 풀프레임 안에서도 S5(184.2)와
S1(245.8)이 그만큼 갈린다. 오히려 GH5(야생동물/조류 촬영으로 보이는
망원 200mm 렌즈 샷, 어둡고 대비 큰 장면 위주)와 S5(파일명 "Y-DP-" 세트,
dark_pct가 유독 높은 로우키 장면이 많음)가 서로 다른 포맷인데도 낮은
화이트p99.5로 묶이는 패턴이 나타나, Pentax 645Z/K-1 때처럼 "센서
포맷 자체의 DR/색재현 차이"라기보다 리뷰어별 촬영 세트(장소/피사체) 편향이
더 크게 작용한 것으로 보인다 - 원인은 미확정. 채도도 G9(64.6)이 유난히
낮고 S5(140.3)가 유난히 높아 포맷별 경향으로 정리하기 어렵다. 표본이 더
모일 때까지 전체 population 평균을 타깃으로 사용.

leica.py/phaseone.py/pentax.py/ricoh_gr.py/canon.py/sony.py/nikon.py와
동일한 한계: raw 기준선이 없어 population 타깃을 film_curve의
toe_lift/white_point에 직접 대입한 것이고, shoulder_start/clahe_clip/
hue·채도 무조작 가정은 검증 없이 핫셀블라드 기본값을 차용.

raw 기준선 업그레이드 가능성: canon.py/nikon.py에서 이미 mirrorlesscomparison.com
과 imaging-resource.com 양쪽에서 raw+jpeg 페어 소스가 이번 population-fit
방식에 쓸 수 없다는 게 확인됐음(RAW/JPEG 폴더가 프레임 페어가 아니거나,
imaging-resource.com의 raw 다운로드 링크가 사이트 마이그레이션으로 깨짐).
Panasonic 전용으로 별도 조사는 하지 않았으나 동일한 사이트 구조적 문제라
population-fit 방식을 유지하기로 결정.
"""
from core.engine import apply_population_fit_look

_TOE_LIFT = 13.4 / 255
_WHITE_POINT = 223.2 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_panasonic_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                          white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
