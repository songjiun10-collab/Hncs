"""
Phase One(Capture One 기본 렌더링) 색감 근사 - population 통계 기반 1차 버전

Phase One 디지털백은 스튜디오/테더링 중심이라 컨슈머 카메라 같은 인카메라
JPEG 엔진이 사실상 의미 없다. imaging-resource.com에서 받은 샘플들의 EXIF
Software가 전부 "Capture One"(Phase One 자체 제작 RAW 컨버터)이었으므로,
이 프로젝트가 재현하려는 건 "카메라 JPEG"가 아니라 "Capture One 기본
렌더링"이다 (tools/analyze.py phaseone 모드).

population 통계 (2026-07, imaging-resource.com Phase One XF 100MP 리뷰
갤러리, 30장 - exiftool Software="Capture One" 확인, Photoshop/Lightroom
편집본 제외):
  1차 실행(n=20)에서 8장 중 6장이 ISO 노이즈 테스트 차트(같은 장면, ISO만
  다름)였는데 이게 population을 왜곡시킴(채도 76.9) - "-iso-" 파일명 필터
  추가하고 표본을 30장으로 늘려 재실행하니 채도 96.0으로 바뀜.

  최종(n=30, ISO 차트 제외): 블랙p2=11.4(그림자유효 9장), 화이트p99.5=228.4,
  채도=96.0

무결성 재검증(2026-07, core/validation.py is_image_usable() 적용 후):
imaging-resource.com media CDN이 이 갤러리의 특정 업로드 배치(2019-05
재처리분, "Y-JG-IQ4-150MP-*" 전체)를 통째로 손상시켜 저장하고 있었던
게 드러남 - 원본(href) 링크는 전부 404, scaled 폴백도 행 단위로 텅
비어있어(디코드가 중간에 멈춤) 위 30장 중 상당수가 사실 못 쓰는
이미지였음. 갤러리 전체(후보 110장)를 무결성 검증 통과분만 다시 모으니
16장(그림자유효 6장)으로 줄었지만 전부 실제로 온전한 이미지:
  재검증(n=16): 블랙p2=12.8(그림자유효 6장), 화이트p99.5=226.5, 채도=114.5
b2/w995는 기존 값과 비슷하지만(오차범위) 채도는 96.0->114.5로 꽤
달라짐 - 손상됐던 이미지들이 채도 계산에도 영향을 준 것으로 보임.
이 재검증값을 최종 채택. 그림자유효 표본이 6장뿐이라 블랙p2는 여전히
불확실성이 큼.

픽셀 시그니처 분석(2026-07, `datasets/phaseone/{tone,color,texture,gamut}_signature.json`
+ `joint_distribution.npz`): 재검증된 16장을 핫셀블라드와 동일한
방법론(사진 단위 동일가중 평균)으로 재분석. w995=226.5/그림자유효
b2=12.8/sat=114.5가 위 재검증값과 정확히 일치(좋은 교차검증). 샤프닝=
0.68, 미세대비=5.74, 노이즈=0.055, 에지헤일로 overshoot=5.35%,
chroma_mean=20.6. n=16 표본이 워낙 작아서(그림자유효 6장) 표준편차가
평균과 맞먹는 지표가 여럿(b2 std=29.0/mean=43.2 등) - 방향성 참고
정도로만 쓸 것, hue/채도를 안 건드리는 설계라 color/gamut 수치는
애초에 보정 타깃도 아님.

라이카와 마찬가지로 raw(IIQ) 기준선을 못 구해서(imaging-resource.com의
DNG 다운로드 링크는 현재 사이트 템플릿에서 사라진 것으로 보임) 그리드서치가
아니라 population 타깃을 film_curve의 toe_lift/white_point에 직접
대입한 1차 버전. shoulder_start/clahe_clip/hue·채도 무조작 가정은 검증
없이 핫셀블라드 기본값을 차용 - raw 페어를 구하면 가장 먼저 검증할 부분
(leica.py와 동일한 한계).

표본 확대 조사(2026-07, 결론: 확대 불가 - XF 100MP가 유일한 컬러 갤러리):
n=16이 이 프로젝트에서 가장 얇은 population-fit 표본이라 imaging-resource.com에
Phase One의 다른 바디/디지털백 리뷰 갤러리가 있는지 슬러그 직접 조회 +
사이트 검색(`?s=phase+one`, 검색결과 페이지 1~4 전체)으로 재조사했다.
추측 슬러그(phase-one-iq4-150mp-review/phase-one-xf-iq4-review/
phase-one-iq4-review/phase-one-iq3-100mp-review/phase-one-iq3-review/
phase-one-iq3-achromatic-review/phase-one-a-series-review/
phase-one-xf-iq3-review/phase-one-iq2-review/phase-one-iq1-review)는
전부 301로 리다이렉트됐고 Location 헤더를 따라가 보니 하나같이
`/cameras/fujifilm-gfx-100-review/gallery/`(`<title>`="Fujifilm GFX 100
Review - Gallery")로 떨어졌다 - 라이카/올림푸스 문서에 기록된 것과 동일한
"가짜 슬러그는 무관한 갤러리로 조용히 폴백" 패턴. 사이트 검색으로 실존이
확인된 리뷰 갤러리는 "Phase One XT"(`/cameras/phase-one-xt-review/gallery/`,
200, `<title>`="Phase One XT Review - Gallery" 정상) 단 하나뿐이었다 -
이건 tools/analyze.py BRAND_CONFIGS 주석에 이미 "시도했다가 뺐음"으로
기록돼 있던 갤러리인데, 이번에 갤러리 HTML을 처음부터 다시 긁어
독립적으로 재확인해보니 후보 218장 **전부**(100%, 이전 기록의 "무결성
통과분 13장이 전부 achromatic"보다 더 강한 근거) 파일명에
"-ACHROMATIC-"가 박혀 있었다(예:
"Y-JG-P1-XT-150MP-ACHROMATIC-13559.jpg") - 이 리뷰에 쓰인 바디가 IQ4
150MP Achromatic(흑백 전용) 디지털백이라 갤러리 후보 자체가 처음부터
전량 무채색(채도=0)이라는 뜻이다. 컬러 population 타깃(toe_lift/
white_point 피팅) 표본에 흑백 전용 카메라를 섞을 수 없으므로 기존
결정을 재확인만 하고 다시 제외했다. 그 외 IQ1/IQ2/IQ3/XF IQ3/XF IQ4를
단독으로 다룬 리뷰 갤러리 페이지는 imaging-resource.com에 존재하지
않는다 - 관련 뉴스 기사("Phase One IQ4 150MP Field Test", "Phase One XF
100MP Field Test")는 있지만 상세페이지별 갤러리 구조
(`/image/N?section=gallery`) 없이 기사 본문에 이미지 17~28장이 박혀있고
갤러리 링크는 전부 기존 XF 100MP 갤러리로 되돌아가는 형태라 이 프로젝트의
스크레이핑 방식(tools/download.py list_gallery_images/resolve_full_image)이
아예 적용되지 않는다. 결론: imaging-resource.com에서 뽑을 수 있는 Phase
One 컬러 갤러리는 XF 100MP 하나뿐이고, 이 사이트를 소스로 쓰는 한
n=16이 사실상의 상한이다 - 다음 세션이 같은 슬러그들을 다시 시도하며
시간을 쓰지 않도록 여기 기록해둔다.

재검증(2026-07, 위 조사와 함께 수행): 기존 캐시
(downloaded_samples_phaseone/, 16장)를 core/validation.py의
is_image_usable()과 genuine_render_check()로 다시 돌려 무결성/진위
(Software="Capture One")가 여전히 유효한지 확인 - 16/16 그대로 통과,
손상이나 제3자 편집 흔적 없음(사이트 CDN 상태가 그동안 바뀌지 않았음을
의미). Canon EOS R3 이후 다른 population-fit 브랜드에 적용해 온 버스트
중복 제거 기준(인접 프레임 번호, w995 차이<=2, 채도 차이<=1.5)도 이
16장에 재적용했으나 해당하는 쌍이 없었다 - 가장 근접한 후보였던
Y-TRI-CF006323/006324-WB 쌍(파일명 접미사 "-WB"로 보아 같은 화이트밸런스
테스트 세트)은 w995 차이는 0이지만 채도 차이가 26.6으로 기준을 훨씬
초과했고, YCF004669/004670 쌍도 w995 차이 42/채도 차이 140으로 명백히
다른 장면이었다. 따라서 population 통계와 아래 상수
(_TOE_LIFT/_WHITE_POINT)는 이번 조사로 변경하지 않았다 - 재검증(n=16)
절의 값을 그대로 유지.
"""
from core.engine import make_population_fit_look

_TOE_LIFT = 12.8 / 255
_WHITE_POINT = 226.5 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용

apply_phaseone_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
