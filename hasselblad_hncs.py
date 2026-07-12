"""
HNCS 순정 근사 - X 시스템 통합 (X1D + X1D II + X2D + X2D II 혼합 풀)

문서화된 HNCS 설계 원칙 (hasselblad.com):
1. "Hasselblad Film Curve" - toe + 리니어 미드 + shoulder의 필름형 톤커브
2. "정확한 색값만 복원하면 monotonous - 눈은 대비를 강화해 본다"
   -> 지각 보상: 약한 마이크로 콘트라스트
3. "rich saturation" - 채도 무조작
4. 스킨톤이 전 명도 구간에서 부드러움 -> hue/채도 무조작으로 달성
5. HNCS는 X 시스템 전체(X1D~X2D II)에 걸쳐 일관 적용되는 색철학 -> 바디
   세대를 섞어서 풀링하는 것이 오히려 "카메라 개체차"를 노이즈로 상쇄시켜
   "X 시스템 공통 색과학"을 더 안정적으로 드러냄 (설계 판단, 2026-07)

설계 판단 기록:
- 초기엔 X1D/X2D를 분리하려 했으나(세대별 DR차 우려: X1D-50C 14비트/
  DR~13스톱 vs X2D100C 16비트/DR~15스톱), 실제로 표본에 확실히 라벨된
  X1D 사진(오큘러스, X1D II 50C+XCD21 확인)을 넣어도 풀링 통계가 안
  튀었음(블랙p2 141=하이키 특이값과 무관하게 동일 패턴) -> 바디 세대보다
  "장면"이 톤 분포를 더 좌우한다는 게 실측으로 재확인됨.
- 결론: hue불변/rich saturation/film curve 형태 같은 "철학"은 세대 무관
  하게 성립하고, 그 정도 레벨의 근사가 이 파일의 목표이므로 통합 풀링이
  타당함. 초정밀 매칭(특정 바디 RAW 대응)이 필요해지면 그때 라벨 확실한
  샘플만으로 별도 분리.

라이브러리 구조:
  hasselblad_hncs   - X 시스템 통합 순정 근사 (이 파일)
  hasselblad_day    - 낮 그레이딩 (day/night 통합 검토 중)
  hasselblad_night  - 밤 그레이딩 (〃)

실측 검증 (v8, 2026-07): 공식 샘플 19~20장 통합 풀 (X1D/X2D 세대 혼합,
그 중 최소 1장 X1D II 50C 캡션 확인). 인물 6장 서브셋 재검증 결과 타깃
전체(13.5/222.1) vs 인물전용(10.0/211.7)이 갈렸지만 피팅 파라미터는
거의 동일(toe_lift 0.001 동일, white_point 0.92->0.90). 피사체/세대
모두 커브 자체를 크게 안 바꾸는 것으로 판단.

스킨톤 hue 3장 검증 - 전부 완전 불변 (51->51, 9->9, 11->11).

실측 검증 (v9, 2026-07): 공식 샘플 풀 확대 124장 (CSV 139행 중 다운로드
성공분, jpeg_url 없는 12행/죽은 링크 3행 제외). 얼굴 검출(YuNet)로 인물
서브셋 43장 자동 추출 - 타깃 전체(11.3/223.9) vs 인물전용(10.2/226.3),
v8 대비 거의 동일선상(블랙p2 13.5->11.3, 화이트p99.5 222.1->223.9).
표준편차가 큼(화이트 std~27) - 낮/밤/역광 샘플이 안 갈리고 섞여 있어서
그런 것으로 보이고, 커브 파라미터를 흔들 정도의 체계적 편차는 아니라고
판단해 toe_lift/shoulder_start/white_point 그대로 유지.

스킨톤 hue 불변성, 인물 43장 자동 검증 (portrait_skin_analysis.py):
apply_hncs 적용 전/후 얼굴 중앙 패치 hue 비교 - 평균 |delta|=0.21,
최대 delta=2.0 (hue 스케일 0~179 기준) - v8의 수동 3장 검증과 일치하는
결과. L채널만 건드리는 구조상 나오는 반올림 잡음 수준이고, 실질적으로
hue 불변 확인.

참고: raw_url이 채워진 행이 21개 있어 원본(비가공) 대 그레이딩 결과의
진짜 전/후 비교가 이론상 가능하나(.fff/.3FR, 장당 최대 ~80MB, rawpy/
libraw 필요 - 이 분석 시점엔 미설치), 이번 v9는 여전히 "이미 그레이딩된
공식 샘플들의 통계"를 타깃으로 삼는 v8과 같은 방법론. 진짜 raw->HNCS
피팅이 필요해지면 rawpy 설치 후 재작업.

실측 검증 (v10, 2026-07): rawpy 설치 후 raw+jpeg 페어 10장으로 진짜
전/후 그리드서치 시도 (calibrate_from_raw.py, raw를 카메라WB+
오토브라이트끔+표준감마로 중립 렌더링 -> 베이스라인, 같은 행의 공식
JPEG -> 타깃). 결과: RMSE 43.8->37.8로 소폭 개선됐지만 최적값이
white_point=1.0(탐색범위 상한)에서 잡힘 - 이건 숄더 롤오프를 사실상
없앤다는 뜻이라 원칙1(toe+리니어미드+shoulder)과 모순됨.

원인 분석: 중립 렌더링이 실제 그레이딩 결과보다 블랙p2/화이트p99.5가
계통적으로 낮게 나옴(예: x1d-II-sample-01 타깃b2=38 vs 중립렌더 기반
결과 15~18) - apply_hncs가 toe/shoulder 형태만 다루고 전역 노출/감마
리프트 단계가 아예 없는 구조라, 이 노출 격차를 커브 파라미터만으론
못 메꿈. 그리드서치가 그 격차를 메우려고 white_point를 경계까지
밀어붙인 것으로 판단 - 실제로 채택하면 시각적으로는 오히려 밋밋해질
가능성이 큼. 그래서 이번엔 그리드서치 결과를 채택하지 않고 기존
toe_lift/shoulder_start/white_point 유지.

다음 단계 후보(미착수): apply_hncs에 hasselblad_day/night처럼 전역
노출/감마 보정 단계를 추가한 뒤 재피팅, 또는 x1d-II-sample-09(타깃
b2=123, 극단치) 등 이상치를 걸러내고 재검증.
"""
import cv2
import numpy as np


def _film_curve(x, toe_lift=0.001, shoulder_start=0.78, white_point=0.90):
    """Film Curve: toe(완만 진입+미세 리프트) + 리니어 미드 + smoothstep shoulder"""
    y = x.copy()
    toe_mask = x < 0.1
    t = x[toe_mask] / 0.1
    y[toe_mask] = toe_lift + t * (0.1 - toe_lift)   # [0,0.1] -> [lift,0.1]
    sh_mask = x > shoulder_start
    t2 = (x[sh_mask] - shoulder_start) / (1 - shoulder_start)
    y[sh_mask] = shoulder_start + (t2 * t2 * (3 - 2 * t2)) * (white_point - shoulder_start)
    return np.clip(y, 0, 1)


def apply_hncs(img_bgr, toe_lift=0.001, shoulder_start=0.78,
               white_point=0.90, clahe_clip=1.25):
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    # 1. 지각 보상 대비 (커브보다 먼저 - 순서 중요)
    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    # 2. Film Curve (L채널, 색 보존)
    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(_film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    # 3. 채도/hue 무조작 (rich saturation은 "안 건드림"으로 달성)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
