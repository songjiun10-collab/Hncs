"""
Leica 색과학 근사 (population 통계 기반 1차 버전, raw 페어 없음)

핫셀블라드 HNCS 프로젝트와 달리 라이카는 "필름시뮬레이션" 같은 다중
선택형 프로파일이 없고(후지), 공식 킷처럼 raw+jpeg 페어가 딸린 샘플
세트도 못 찾았다(라이카 공식 사이트는 갤러리 구조를 못 찾음, dpreview/
kenrockwell/photographyblog는 Cloudflare 봇 차단, stevehuffphoto.com은
Photoshop/Lightroom으로 편집된 사진이라 SOOC 아님, leicarumors.com의
DNG는 Dropbox 폴더인데 JS 렌더링이라 목록을 못 긁음 - Google Drive
폴더는 gdown으로 우회했지만 Dropbox는 동급 도구가 없었음. 이후 라이카
공식 사이트를 Drupal jsonapi까지 파봤지만(leica-camera.com) 역시
노출 안 됨, imaging-resource.com 갤러리도 M9/X Vario/SL2 외에 추가로
찾은 슬러그가 전부 무효였음).

대신 imaging-resource.com의 카메라 리뷰 갤러리(tools/analyze.py leica
모드)에서 진짜 미편집 SOOC JPEG 45장(M9/X Vario/SL2, 각 15장, EXIF로
편집 여부 확인)을 모아 population 통계만 냈다 - 핫셀블라드 v8/v9와 같은
급("이미 그레이딩된 결과물의 통계"), raw 대비 진짜 전/후 피팅(v10~v12급)은
아직 없음.

실측 population 통계 (2026-07):
  전체(n=45):        블랙p2=9.2   화이트p99.5=229.8   채도=98.6
  Leica M9  (n=15):  블랙p2=6.8   화이트p99.5=251.6   채도=93.3  (CCD, 구형)
  Leica X Vario(n=15): 블랙p2=14.2 화이트p99.5=245.8  채도=109.9
  Leica SL2 (n=15):  블랙p2=7.3   화이트p99.5=192.1   채도=92.5  (최신, 46MP)

무결성 검증(2026-07, core/validation.py is_image_usable() 적용): 같은
imaging-resource.com에서 Hasselblad/Phase One/Pentax 갤러리가 CDN 자체
손상 문제를 갖고 있던 게 드러나서 이 45장도 재검증했음 - 전부(45/45)
행 단위 손상 없이 정상. 위 수치 변경 없음.

픽셀 시그니처 분석(2026-07, `datasets/leica/{tone,color,texture,gamut}_signature.json`
+ `joint_distribution.npz`): 위 45장을 핫셀블라드와 동일한 방법론(사진
단위 동일가중 평균, 중앙 2400x2400 크롭에서 샤프닝/미세대비/노이즈/
에지헤일로 측정)으로 재분석. 톤 수치(b2=10.78, 그림자유효 43장 기준
9.21/w995=229.82/sat=98.57)가 위 population 통계와 거의 정확히 일치해
방법론 일관성 재확인. 샤프닝=2.48, 미세대비=9.88, 노이즈=0.50,
에지헤일로 overshoot=22.16%(표본 적은 SL2 사진 몇 장이 표준편차를
끌어올림 - 해석 주의), chroma_mean=12.32. hue/채도를 안 건드리는
설계라 color/gamut 수치는 보정 타깃이 아니라 참고 자료.

카메라별 편차가 큼(특히 SL2의 화이트p99.5가 M9보다 60 가까이 낮음) -
세대/센서가 다른 3개 바디를 묶은 population이라 핫셀블라드 v9 초기의
"낮/밤 샘플이 안 갈려서 std가 컸던" 상황과 비슷하다고 보고, 표본이
더 모일 때까지는 전체 population 평균을 그대로 타깃으로 썼다.

파라미터 매핑: toe_lift/white_point를 그리드서치로 피팅한 게 아니라
(raw 기준선이 없어서 피팅할 대상이 없음), film_curve의 정의상 x=0에서
y=toe_lift, x=1 근방에서 y->white_point로 수렴하는 걸 이용해 population
타깃을 직접 대입했다. shoulder_start/clahe_clip은 raw 페어가 없어 피팅
근거가 없으므로 hasselblad_hncs의 기본값(0.78/1.25)을 그대로 가져다 씀
- 검증 안 된 가정이라는 점을 명시.

hue/채도: population 통계로는 "라이카가 중립 대비 채도를 올리는지/
내리는지" 판단 불가 (before가 없음 - after만 있음). 핫셀블라드와 같은
원칙(L채널에만 커브 적용, a/b 무조작)을 기본값으로 삼았지만, 이건
"가정"이지 실측 확인된 설계는 아님. raw 페어를 구하면 가장 먼저
검증해야 할 부분.

한계 (다음에 raw 페어를 구하면 검증할 것):
- toe_lift/white_point 외 나머지 파라미터(shoulder_start, clahe_clip)는
  전부 핫셀블라드 값을 그대로 가져온 미검증 추정
- hue/채도 무조작 가정 자체가 미검증
- M9(CCD, 2009)와 SL2(2019, CMOS) 사이 10년의 센서/파이프라인 차이를
  하나의 커브로 뭉뚱그리는 게 타당한지도 미검증
"""
from core.engine import apply_population_fit_look

_TOE_LIFT = 9.2 / 255
_WHITE_POINT = 229.8 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_leica_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                      white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
