"""
Sigma 색감 근사 - population 통계 기반 1차 버전

imaging-resource.com 카메라 리뷰 갤러리에서 미편집 SOOC JPEG를 모아
population 통계를 냈다(analyze 스크립트는 tools/analyze.py의
BRAND_CONFIGS를 건드리지 않고 독립 스크립트로 실행 - 기존 Panasonic/
Olympus 작업과 동일한 이유로 공용 딕셔너리 충돌을 피하려고 분리함, 로직
자체는 run_imaging_resource_brand()와 동일). EXIF Make="SIGMA"로 진짜
SOOC 확인. DNG/X3F raw 페어는 다른 population-fit 브랜드(라이카/Phase
One/Pentax/Ricoh GR/Canon/Sony/Nikon/Panasonic/Olympus)와 마찬가지로
이 사이트에서 못 찾아서 population 통계만 사용.

바디 선정: Sigma는 Bayer 센서(fp/fp L, L마운트 풀프레임)와 Foveon 센서
(dp Quattro/sd Quattro/SD1 Merrill, APS-C)를 병행 판매하는 유일한
브랜드라 두 계열을 다 포함하는 게 흥미로울 것 같아 imaging-resource.com
슬러그를 직접 조회(sigma-*-review/gallery/)해 실존 여부를 확인했다 -
다른 브랜드와 동일하게 존재하지 않는 슬러그는 301로 조용히 폴백되고
(sigma-sd-quattro-h-review/sigma-dp1-quattro-review/
sigma-dp3-quattro-review/sigma-dp2-merrill-review/sigma-fpl-review 전부
301), 실존하는 갤러리는 200 + <title> 태그가 실제 카메라명과 일치하는
걸로 확인했다. 최종 확보 5개: Sigma fp(Bayer, L마운트, 2019,
sigma-fp-review, 후보 45장), Sigma fp L(Bayer, 6100만화소, 2021,
sigma-fp-l-review, 후보 35장), Sigma sd Quattro(Foveon Quattro, APS-C
DSLR형, 2016, sigma-sd-quattro-review, 후보 25장), Sigma dp2 Quattro
(Foveon Quattro, APS-C 콤팩트, 2014, sigma-dp2-quattro-review, 후보
25장), Sigma SD1 Merrill(Foveon Merrill, APS-C DSLR, 2012,
sigma-sd1-merrill-review, 후보 12장 - 갤러리 자체가 14장뿐이라 다른
바디보다 표본이 작음). Bayer 2바디 + Foveon 2세대(Merrill/Quattro)
3바디 구성.

수집: 바디당 후보 목록에서 최대 25장까지 다운로드+무결성 검증
(core/validation.py is_image_usable()) + genuine SOOC 확인 순으로
진행. 편집/기술 테스트샷 필터는 다른 imaging-resource 브랜드와 동일한
"edit"/"-mod"/"unsharpmask"/"nosharp"/"stack"/"-iso-"에 Sigma 고유 함정
3종을 추가했다:
  - "-edt": Sigma fp 갤러리의 Photoshop 편집본 접미사(Panasonic S5의
    "-edt", Olympus E-M1X의 "-EDT"와 동일한 종류의 함정).
  - "spp": Sigma dp2 Quattro 갤러리에서 발견 - 같은 촬영 컷(예: "YC-99")을
    Sigma 자체 RAW 컨버터 "Sigma Photo Pro"로 재처리한 버전들이
    "-SPP605"/"-SPP606"/"_SPP_LANDSCAPE" 등 접미사로 잔뜩 섞여있었음
    (실측: YC-14/YC-19/YC-99/YA-00xx 등 여러 컷이 SPP 버전 3~5개씩과
    인카메라 원본 1개로 중복). exiftool로 확인해보니 인카메라 원본은
    Software="1.00.0.8174"(펌웨어 버전 문자열)인 반면 SPP 재처리본은
    Software="SIGMA Photo Pro 6.0.6"으로 정확히 갈려서, "spp"를
    filename 1차 필터에 추가하고 genuine_render_check의 reject_keywords에도
    "photo pro"를 추가해 이중 방어했다(Phase One이 자사 RAW 컨버터
    "Capture One"을 오히려 "기대하는 렌더러"로 받아들이는 것과 반대로,
    Sigma는 카메라 자체 JPEG 엔진을 근사하는 게 목적이라 자사 RAW
    컨버터도 "제3자 처리"와 동일하게 거절 대상으로 취급).
  - "leaves_closeup"/"leaves_sharp": SD1 Merrill 갤러리(전체 14장 중
    2장)의 해상력 테스트용 크롭 비교 페어("YLEAVES_CLOSEUP.jpg"/
    "YLEAVES_SHARP.jpg") - Phase One의 ISO 노이즈 차트, Ricoh GR IIIx의
    조리개 브라케팅과 같은 종류의 "대표성 없는 기술 테스트샷" 제외.

무결성/genuine SOOC 결과가 바디별로 극단적으로 갈렸다:
  - Sigma fp: 시도 45, 확보 16, CDN손상 1, 편집거절 28(62%!) - "YC-DP-IM00xx"
    로 시작하는 초반 블록(23장)이 전부 Adobe Photoshop 편집본이었고
    ("YC-DP-IM0031.jpg"처럼 접미사가 전혀 없는 "깨끗해 보이는" 파일명도
    포함 - filename 필터로는 전혀 못 거르고 genuine_render_check의 EXIF
    Software 검사가 유일한 방어선이었음), 이후 "YD-DP-" 블록에서도
    편집본과 원본(Software="SIGMA fp Ver.1.02.0.V79" 같은 펌웨어 버전
    문자열)이 섞여있었음.
  - Sigma fp L: 시도 35, 확보 6, CDN손상 29(83%!) - 지금까지 나온 모든
    브랜드/갤러리 중 가장 높은 CDN 손상률(기존 최고는 Phase One XF
    100MP의 100%지만 그건 표본 30장 전부, Hasselblad X2D 100C 72%가
    다음으로 높았음 - fp L은 표본이 있는 갤러리 중 최고 손상률). 원본이
    실패하면 scaled로 폴백하는 로직까지 거쳤는데도 대부분 scaled마저
    "Premature end of JPEG file"으로 손상돼 있었다 - 6100만화소 원본
    파일이 커서(장당 20~30MB) media.imaging-resource.com CDN에 저장된
    원본 자체가 깨져있는 기존 패턴(core/validation.py 모듈 docstring
    참고)이 파일 크기가 큰 갤러리에서 더 심하게 나타나는 것으로 보이나
    확정할 근거는 없음.
  - Sigma sd Quattro/dp2 Quattro/SD1 Merrill: 시도한 만큼 전부 확보(25/25,
    25/25, 12/12), CDN손상 0, 편집거절 0 - Foveon 갤러리 3개는 전부
    깨끗했음. dp2 Quattro는 SPP 필터를 filename 단계에서 미리 걸러낸
    덕에(34장 -> 25장 확보 시도) genuine_render_check에서 추가로 거절된
    건이 없었다.

버스트 중복 제거: Canon EOS R3/Panasonic S1·S5/Olympus 사례와 동일한
방법(인접 프레임 번호, w995 차이<=2, 채도 차이<=1.5를 같은 장면으로
판단)으로 점검하되, Sigma는 한 갤러리 안에 서로 다른 촬영 세션/명명
규칙이 섞여 있는 경우가 있어(dp2 Quattro의 "YC-14"/"YA0012"/"YSDIM0007"
등 서로 다른 접두사) 파일명 접두사가 같은 항목끼리만 비교하도록
방법론을 보강했다 - 접두사를 무시하고 프레임번호만 비교했더니 dp2
Quattro의 "YC-78.jpg"(브루클린 길거리, 사람+자전거)와
"YSDIM0080.jpg"(전혀 다른 실내/스튜디오 정물)가 프레임번호가 우연히
근접(78/80)하고 w995(233/231)·채도(67.7/69.2)도 우연히 비슷해서 거짓
양성으로 잡혔음 - 실제 이미지를 열어 육안 확인 후 폐기. 같은 이유로
프레임번호 갭이 큰 경우(같은 접두사라도 49 이상 벌어진 dp2 Quattro의
YA0055/YA0104 - 역시 육안 확인 결과 완전히 다른 장면)를 배제하려고
Canon EOS R3 사례에서 실측된 최대 갭(13)을 참고해 갭<=15인 경우만
"인접 프레임"으로 인정하도록 임계값을 추가했다. 이 두 단계 보강 후
남은 진짜 버스트 쌍은 sd Quattro의 "Y_SDI0034.jpg"/"Y_SDI0036.jpg"
하나뿐(w995 238/238, 채도 84.9/86.1, 육안 확인 결과 동일한 페루
어촌/어선 정박 장면을 프레임 2장 차이로 연사) - 1장만 남기고 제외
(84 -> 83). 나머지 4바디에서는 해당 패턴이 발견되지 않았다.

population 통계 (2026-07, 버스트 중복 제거 후 n=83):
  전체:                       블랙p2=9.3(그림자유효 64)  화이트p99.5=228.8  채도=93.8
  fp         (n=16, Bayer):   블랙p2= 3.9  화이트p99.5=193.9  채도=123.6  (그림자유효 16)
  fp L       (n= 6, Bayer):   블랙p2=16.5  화이트p99.5=228.8  채도= 87.9  (그림자유효  4)
  sd Quattro (n=24, Foveon):  블랙p2=13.2  화이트p99.5=236.4  채도= 84.6  (그림자유효 13)
  dp2 Quattro(n=25, Foveon):  블랙p2= 8.0  화이트p99.5=236.7  채도= 85.0  (그림자유효 23)
  SD1 Merrill(n=12, Foveon):  블랙p2=13.6  화이트p99.5=243.4  채도= 93.5  (그림자유효  8)

Bayer vs Foveon 비교(코디네이터 요청으로 조사): 3개 Foveon 바디는
서로 다른 두 세대(Merrill 2012/Quattro 2014,2016)이고 폼팩터도
DSLR형(sd Quattro/SD1 Merrill)과 콤팩트형(dp2 Quattro)으로 다른데도
화이트p99.5(236.4~243.4)와 채도(84.6~93.5)가 서로 상당히 좁게
모여있다 - Foveon 특유의 렌더링 성향이 있을 가능성을 시사. 반면
Bayer인 fp는 블랙p2=3.9로 Foveon 세 바디(8.0~13.6)보다 뚜렷이 낮고
화이트p99.5=193.9도 Foveon보다 40 이상 낮으며 채도=123.6은 Foveon보다
30~40 높아 확실히 이질적이다. 그런데 같은 Bayer인 fp L은 화이트
p99.5=228.8·채도=87.9로 오히려 fp보다 Foveon 클러스터에 훨씬 더
가깝다 - "Bayer vs Foveon" 이분법으로 설명되지 않는다. fp의 이질적
수치가 센서 자체의 특성인지 표본 편향인지도 불확실한데, fp 표본
(n=16)이 45장 후보 중 Photoshop 편집 62%를 걸러낸 뒤 남은 것이라
"YD-DP-" 태그가 붙은 한 촬영 세트에 크게 쏠려있어(리뷰어 한 명의
한 촬영 세션일 가능성) 카메라 자체의 렌더링 특성이라기보다 그
세션의 장면/노출 선택(저채도·저대비 장면이 많았을 가능성) 편향일
수 있다. fp L 쪽은 표본이 6장(그림자유효 4장)뿐이라 반대로 신뢰도가
낮아 "fp L이 fp와 다르다"는 것도 확정할 수 없다. 결론: 두 센서
계열을 population 타깃을 나누어 별도로 피팅할 만큼 깨끗한 근거는
없다고 판단해(표본도 작고 Bayer 내부에서도 fp/fp L이 서로 갈리는
모순이 있어) Panasonic의 MFT vs 풀프레임, Olympus의 세대별 편차
사례와 동일하게 전체 population 평균 하나를 타깃으로 사용한다 -
Bayer/Foveon 계열 차이는 표본이 더 모일 때까지 미확정 관찰 사항으로만
남긴다.

leica.py/phaseone.py/pentax.py/ricoh_gr.py/canon.py/sony.py/nikon.py/
panasonic.py/olympus.py와 동일한 한계: raw 기준선이 없어 population
타깃을 film_curve의 toe_lift/white_point에 직접 대입한 것이고,
shoulder_start/clahe_clip/hue·채도 무조작 가정은 검증 없이 핫셀블라드
기본값을 차용.

raw 기준선 업그레이드 가능성: canon.py/nikon.py에서 이미
mirrorlesscomparison.com과 imaging-resource.com 양쪽에서 raw+jpeg 페어
소스가 이번 population-fit 방식에 쓸 수 없다는 게 확인됐음. Sigma
전용으로 별도 조사는 하지 않았으나 동일한 사이트 구조적 문제라
population-fit 방식을 유지하기로 결정. Sigma는 X3F(Foveon)/DNG 등
raw 포맷이 브랜드마다도 특수해서(Foveon 3레이어 센서) 설사 페어를
구해도 기존 그리드서치 파이프라인을 그대로 못 쓸 가능성이 있다는 점도
참고.

픽셀 시그니처 분석 (2026-07, `datasets/sigma/` - 버스트 중복 제거 후
동일한 n=83): tone/color/texture/gamut 4개 json + Lab 채널 풀링
히스토그램 joint_distribution.npz를 canon.py/panasonic.py/olympus.py와
동일 스키마로 추가. sharpening/micro_contrast는 Sony 스케일 버그 재발
방지를 위해 Canon의 공식을 그대로 재사용(샤프닝=중앙크롭 Sobel
그래디언트크기 표준편차/15, 미세대비=DoG(sigma1=1,sigma2=2) 표준편차,
스케일 없음). overshoot/undershoot 에지헤일로 지표는 Canon 원본
스크립트가 커밋되지 않아 텍스트 설명만 보고 새로 구현한 것이라
Panasonic/Olympus와 마찬가지로 파라미터가 정확히 같다는 보장은
없음(datasets/sigma/texture_signature.json methodology 필드에 명시) -
sharpening/micro_contrast만큼 브랜드 간 1:1 비교 가능하다고 보지 말 것.
"""
from core.engine import make_population_fit_look

_TOE_LIFT = 9.3 / 255
_WHITE_POINT = 228.8 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용

apply_sigma_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
