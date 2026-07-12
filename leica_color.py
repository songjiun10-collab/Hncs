"""
Leica 색과학 근사 (population 통계 기반 1차 버전, raw 페어 없음)

핫셀블라드 HNCS 프로젝트와 달리 라이카는 "필름시뮬레이션" 같은 다중
선택형 프로파일이 없고(후지), 공식 킷처럼 raw+jpeg 페어가 딸린 샘플
세트도 못 찾았다(라이카 공식 사이트는 갤러리 구조를 못 찾음, dpreview/
kenrockwell/photographyblog는 Cloudflare 봇 차단, stevehuffphoto.com은
Photoshop/Lightroom으로 편집된 사진이라 SOOC 아님, leicarumors.com의
DNG는 Dropbox 폴더인데 JS 렌더링이라 목록을 못 긁음 - Google Drive
폴더는 gdown으로 우회했지만 Dropbox는 동급 도구가 없었음).

대신 imaging-resource.com의 카메라 리뷰 갤러리(analyze_leica_samples.py)
에서 진짜 미편집 SOOC JPEG 45장(M9/X Vario/SL2, 각 15장, EXIF로 편집
여부 확인)을 모아 population 통계만 냈다 - 핫셀블라드 v8/v9와 같은 급
("이미 그레이딩된 결과물의 통계"), raw 대비 진짜 전/후 피팅(v10~v12급)은
아직 없음.

실측 population 통계 (2026-07, analyze_leica_samples.py):
  전체(n=45):        블랙p2=9.2   화이트p99.5=229.8   채도=98.6
  Leica M9  (n=15):  블랙p2=6.8   화이트p99.5=251.6   채도=93.3  (CCD, 구형)
  Leica X Vario(n=15): 블랙p2=14.2 화이트p99.5=245.8  채도=109.9
  Leica SL2 (n=15):  블랙p2=7.3   화이트p99.5=192.1   채도=92.5  (최신, 46MP)

카메라별 편차가 큼(특히 SL2의 화이트p99.5가 M9보다 60 가까이 낮음) -
세대/센서가 다른 3개 바디를 묶은 population이라 핫셀블라드 v9 초기의
"낮/밤 샘플이 안 갈려서 std가 컸던" 상황과 비슷하다고 보고, 표본이
더 모일 때까지는 전체 population 평균을 그대로 타깃으로 썼다.

파라미터 매핑: toe_lift/white_point를 그리드서치로 피팅한 게 아니라
(raw 기준선이 없어서 피팅할 대상이 없음), _film_curve의 정의상 x=0에서
y=toe_lift, x=1 근방에서 y->white_point로 수렴하는 걸 이용해 population
타깃을 직접 대입했다: toe_lift=9.2/255, white_point=229.8/255.
shoulder_start/clahe_clip은 raw 페어가 없어 피팅 근거가 없으므로
hasselblad_hncs.py의 기본값(0.78/1.25)을 그대로 가져다 씀 - 검증 안 된
가정이라는 점을 명시.

hue/채도: population 통계로는 "라이카가 중립 대비 채도를 올리는지/
내리는지" 판단 불가 (before가 없음 - after만 있음). 핫셀블라드와 같은
원칙(L채널에만 커브 적용, a/b 무조작)을 기본값으로 삼았지만, 이건
"가정"이지 실측 확인된 설계는 아님. raw 페어를 구하면 가장 먼저
검증해야 할 부분.

한계 (다음에 raw 페어를 구하면 검증할 것):
- toe_lift/white_point 외 나머지 파라미터(shoulder_start, clahe_clip,
  exposure_gamma 유무)는 전부 핫셀블라드 값을 그대로 가져온 미검증 추정
- hue/채도 무조작 가정 자체가 미검증
- M9(CCD, 2009)와 SL2(2019, CMOS) 사이 10년의 센서/파이프라인 차이를
  하나의 커브로 뭉뚱그리는 게 타당한지도 미검증 (핫셀블라드는 X1D~X2D
  세대차가 실측상 무시할 만하다고 나왔지만, 라이카는 아직 그 검증을
  안 함)
"""
import cv2
import numpy as np

from hasselblad_hncs import _film_curve

_TOE_LIFT = 9.2 / 255
_WHITE_POINT = 229.8 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_leica_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                      white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(_film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
