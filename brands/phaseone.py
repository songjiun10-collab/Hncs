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

라이카와 마찬가지로 raw(IIQ) 기준선을 못 구해서(imaging-resource.com의
DNG 다운로드 링크는 현재 사이트 템플릿에서 사라진 것으로 보임) 그리드서치가
아니라 population 타깃을 film_curve의 toe_lift/white_point에 직접
대입한 1차 버전. shoulder_start/clahe_clip/hue·채도 무조작 가정은 검증
없이 핫셀블라드 기본값을 차용 - raw 페어를 구하면 가장 먼저 검증할 부분
(leica.py와 동일한 한계).
"""
from core.engine import apply_population_fit_look

_TOE_LIFT = 12.8 / 255
_WHITE_POINT = 226.5 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_phaseone_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                         white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
