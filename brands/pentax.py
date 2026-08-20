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

무결성 재검증(2026-07, core/validation.py is_image_usable() 적용):
기존 40장 중 16장(645Z 10장, K-1 6장)이 imaging-resource.com CDN에
행 단위로 손상된 채 저장돼 있던 걸 확인 - 손상분을 빼고 같은 갤러리에서
다시 채워 40장(카메라별 20장씩)을 전부 무결성 검증 통과분으로 재구성:
  전체:          블랙p2=11.2(그림자유효 38)  화이트p99.5=237.3  채도=114.3
  645Z (n=20):   블랙p2=11.6  화이트p99.5=239.8  채도=126.3
  K-1  (n=20):   블랙p2=10.7  화이트p99.5=234.8  채도=102.2
b2/w995는 기존 값과 오차범위 내(노이즈 수준)로 거의 그대로였고, 채도만
소폭 하향(124.1->114.3, 645Z는 141.1->126.3) - 손상됐던 이미지들이
채도쪽에 좀 더 영향을 줬던 것으로 보임. 이 재검증값을 최종 채택.

픽셀 시그니처 분석(2026-07, `datasets/pentax/{tone,color,texture,gamut}_signature.json`
+ `joint_distribution.npz`): 재검증된 40장을 핫셀블라드와 동일한
방법론(사진 단위 동일가중 평균, 중앙 2400x2400 크롭 텍스처 측정)으로
재분석. 톤 수치(b2=12.35, 그림자유효 38장 기준 11.16/w995=237.28)가
위 재검증값과 거의 정확히 일치. 샤프닝=2.17, 미세대비=8.71, 노이즈=0.70,
에지헤일로 overshoot=11.42%, chroma_mean=18.73 - 645Z/K-1 카메라별
분리도 유지(w995 격차 재확인: 645Z 239.75 vs K-1 234.8). hue/채도를
안 건드리는 설계라 color/gamut 수치는 보정 타깃이 아니라 참고 자료.

leica.py/phaseone.py와 동일한 한계: raw 기준선이 없어 population 타깃을
film_curve의 toe_lift/white_point에 직접 대입한 것이고, shoulder_start/
clahe_clip/hue·채도 무조작 가정은 검증 없이 핫셀블라드 기본값을 차용.
"""
from core.engine import make_population_fit_look

_TOE_LIFT = 11.2 / 255
_WHITE_POINT = 237.3 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용

apply_pentax_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
