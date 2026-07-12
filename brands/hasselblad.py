"""
HNCS(Hasselblad Natural Colour Solution) 근사 - X 시스템 통합
(X1D + X1D II + X2D + X2D II 혼합 풀). 이 파일은 원래 hasselblad_hncs.py
+ hasselblad_hncs_learned.py + hasselblad_day.py + hasselblad_night.py
4개 파일이었던 걸 brands/ 리팩토링 때 하나로 합쳤다 - 4개 함수
(apply_hncs/apply_hncs_learned/apply_hasselblad_day/apply_hasselblad_night)
모두 "같은 X 시스템 색과학을 다른 방법/다른 서브셋으로 근사한다"는
공통 목표라 한 파일에 묶는 게 자연스러웠다.

문서화된 HNCS 설계 원칙 (hasselblad.com):
1. "Hasselblad Film Curve" - toe + 리니어 미드 + shoulder의 필름형 톤커브
2. "정확한 색값만 복원하면 monotonous - 눈은 대비를 강화해 본다"
   -> 지각 보상: 약한 마이크로 콘트라스트
3. "rich saturation" - 채도 무조작
4. 스킨톤이 전 명도 구간에서 부드러움 -> hue/채도 무조작으로 달성
5. HNCS는 X 시스템 전체(X1D~X2D II)에 걸쳐 일관 적용되는 색철학 -> 바디
   세대를 섞어서 풀링하는 것이 오히려 "카메라 개체차"를 노이즈로 상쇄시켜
   "X 시스템 공통 색과학"을 더 안정적으로 드러냄 (설계 판단, 2026-07)

라이브러리 구조 (이 파일 안의 4개 함수):
  apply_hncs          - X 시스템 통합 순정 근사 (파라메트릭 커브, 기본)
  apply_hncs_learned   - 같은 목표를 raw+jpeg 페어에서 직접 학습한 LUT으로
                         근사 (v12, RMSE 더 낮음 - 아래 참고)
  apply_hasselblad_day    - 낮 장면 그레이딩
  apply_hasselblad_night  - 밤 장면 그레이딩 (DR 중앙 압축)
  (day/night 자체 실측 결과, 타깃이 apply_hncs의 전체 population과 거의
  수렴한다는 게 나와서 - 아래 "day/night" 섹션 참고 - 언젠가 apply_hncs로
  통합할 근거가 있음. 아직 안 함)

=== apply_hncs 실측 검증 이력 ===

v8 (공식 샘플 19~20장): 인물 6장 서브셋 재검증 결과 타깃 전체(13.5/222.1)
vs 인물전용(10.0/211.7)이 갈렸지만 피팅 파라미터는 거의 동일(toe_lift
0.001 동일, white_point 0.92->0.90). 스킨톤 hue 3장 검증 - 전부 완전
불변(51->51, 9->9, 11->11).

v9 (공식 샘플 풀 확대 124장, CSV 139행 중 다운로드 성공분): 얼굴 검출
(YuNet)로 인물 서브셋 43장 자동 추출 - 타깃 전체(11.3/223.9) vs 인물전용
(10.2/226.3), v8과 거의 동일선상. 표준편차 큼(화이트 std~27) - 낮/밤/
역광 샘플이 안 갈리고 섞여서 그런 것으로 보이나 커브 파라미터를 흔들
정도는 아니라고 판단해 유지. 스킨톤 hue 43장 자동 검증: 평균 |delta|=
0.21, 최대 2.0 (hue 0~179 기준) - L채널만 건드리는 구조상 나오는 반올림
잡음 수준, 실질적 hue 불변 확인.

v10 (rawpy 설치 후 raw+jpeg 페어 10장으로 진짜 전/후 그리드서치, raw를
카메라WB+오토브라이트끔+표준감마로 중립 렌더링 -> 베이스라인, 같은 행의
공식 JPEG -> 타깃): RMSE 43.8->37.8로 소폭 개선됐지만 최적값이
white_point=1.0(탐색범위 상한)에서 잡힘 - 원인은 중립 렌더링이 실제
그레이딩 결과보다 블랙p2/화이트p99.5가 계통적으로 낮게 나오는데(전역
노출/감마 리프트 단계가 아예 없는 구조), 그 격차를 그리드서치가
white_point를 밀어붙여서 메우려 한 것으로 판단 - 채택 안 하고
toe_lift/shoulder_start/white_point 유지.

v11 (v10 후속): x1d-II-sample-09(오큘러스 실내, 사실상 전체가 흰색이라
그림자 없음)를 그림자무효로 블랙포인트 피팅에서 제외, exposure_gamma
파라미터를 그리드서치에 추가. exposure_gamma=0.7, white_point=1.0만 반영
(toe_lift/shoulder_start는 원안 0.001/0.78 유지) - RMSE 36.3->23.3
(그림자유효 8장+화이트포인트 10장 기준). shoulder_start를 0.5까지
낮추면 RMSE 16.5까지 더 떨어지지만 그림자유효 샘플 8장뿐이라 커브 모양
자체를 바꾸는 건 과적합 위험 커서 채택 안 함.

실험 기록 (음성 결과): calibrate_from_raw.py의 rawpy 베이스라인을
gamma=(2.222,4.5)(sRGB형) 대신 gamma=(1,1)(linear)로 바꿔서 "디모자이크+
컬러매트릭스 직후, 톤커브 적용 전" 상태에 더 가깝게 만들어봄(파이프라인상
이론적으론 더 정확해야 함). 그런데 RMSE 오히려 악화(23.3->28.2) - rawpy의
디모자이크/컬러매트릭스가 핫셀블라드 자체 파이프라인과 다른 알고리즘이라
"센서에 더 가깝게" 만든다고 실제 camera profile 출력과 더 비슷해지는 게
아니었음. gamma=(2.222,4.5) 베이스라인 유지, linear 실험은 되돌림.

v12: toe+리니어미드+shoulder라는 파라메트릭 모양을 아예 가정하지 않고,
raw+jpeg 페어(10장, gamma=(2.222,4.5) 베이스라인)의 neutral_L/target_L을
픽셀 단위로 대응시켜(총 1,078만 쌍) neutral_L값별 target_L 중앙값으로
256단계 LUT을 직접 학습 (tools/calibrate.py learn_curve 모드). RMSE=15.4로
v11 파라메트릭(23.3)보다 낮음 - apply_hncs_learned()로 분리 제공(이
파일의 apply_hncs 기본값은 안 건드림: 원본이 raw+jpeg 페어 10장뿐이라
완전히 대체하기엔 표본이 작다고 판단, 파라메트릭/데이터기반 두 버전을
나란히 유지). 학습된 커브는 그림자 리프트가 원안보다 훨씬 급격하고
(neutral_L 16->target_L 49), 중간톤은 로그형으로 완만해지다 하이라이트는
소프트 숄더로 수렴 - "toe+리니어미드+shoulder" 가정과 결이 다름.

실험 기록 (음성 결과): v12 LUT이 raw+jpeg 10장뿐이라 과적합 우려가 있어,
bin별 표본수에 반비례해 v11 파라메트릭 커브 쪽으로 수축시키는 정규화를
추가해보고, 10장 leave-one-out 교차검증으로 lambda별 일반화 성능을 측정
(tools/calibrate.py regularize 모드). 결과: lambda=0(정규화 없음)이 LOO
RMSE 14.6으로 제일 좋고, lambda를 키울수록(파라메트릭 쪽으로 더 당길수록)
오히려 계속 나빠짐(lambda=20000일 때 20.7, 순수 파라메트릭 28.0). 원인:
매 fold마다 9장 * 약 108만 픽셀 = 약 970만 픽셀이 들어가서 경험적 평균
자체의 분산은 이미 충분히 작고, 파라메트릭 커브는 표본 부족이 아니라
모양 자체(toe+shoulder 가정)가 실측 톤커브(로그형)와 달라서 그쪽으로
당길수록 체계적 편향만 커짐. apply_hncs_learned()는 정규화 없는 순수
경험적 LUT 그대로 유지.
"""
import cv2
import numpy as np

from core.curve import film_curve, s_curve, apply_highlight_rolloff


def apply_hncs(img_bgr, toe_lift=0.001, shoulder_start=0.78,
               white_point=1.0, clahe_clip=1.25, exposure_gamma=0.7):
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    # 0. 전역 노출 리프트 (v10: 중립 렌더링과 그레이딩 결과 사이 밝기
    #    격차가 toe/shoulder만으론 안 메꿔져서 추가. exposure_gamma=1.0이면
    #    기존 동작과 동일 - no-op)
    if exposure_gamma != 1.0:
        x = np.arange(256, dtype=np.float32) / 255.0
        exp_lut = np.clip((x ** exposure_gamma) * 255, 0, 255).astype(np.uint8)
        l = cv2.LUT(l, exp_lut)

    # 1. 지각 보상 대비 (커브보다 먼저 - 순서 중요)
    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    # 2. Film Curve (L채널, 색 보존)
    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    # 3. 채도/hue 무조작 (rich saturation은 "안 건드림"으로 달성)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


# neutral_L(0~255) -> target_L, tools/calibrate.py learn_curve 모드로
# raw+jpeg 10페어에서 학습 (v12). raw+jpeg 페어 기준 RMSE:
#   apply_hncs (파라메트릭)     23.31
#   apply_hncs_learned (이 LUT) 15.41
# 학습에 쓴 원본이 10장(대부분 X1D 계열)뿐이라 표본이 늘어나면 LUT이
# 달라질 수 있음. CLAHE와 hue/채도 무조작 원칙은 apply_hncs와 동일하게
# 유지 - 다만 커브 자체가 apply_hncs 기본값보다 급격해서 8비트 Lab<->BGR
# <->HSV 왕복 변환에서 나오는 hue 반올림 오차가 apply_hncs(평균
# |delta|~0.2)보다 큼(샘플 1장 기준 평균 |delta|~3.0/179) - 여전히 육안상
# 무시할 수준이지만 apply_hncs만큼 엄격하게 불변은 아님.
_LEARNED_LUT = np.array([
    3, 9, 12, 14, 15, 16, 18, 21, 27, 27, 28, 36, 38, 39, 40, 46,
    49, 50, 52, 54, 57, 57, 58, 59, 60, 60, 65, 65, 65, 68, 68, 69,
    69, 72, 72, 73, 75, 79, 79, 79, 79, 79, 79, 79, 79, 80, 80, 82,
    84, 86, 86, 88, 89, 91, 94, 97, 99, 102, 103, 106, 109, 110, 113, 113,
    114, 115, 117, 119, 119, 120, 122, 123, 124, 128, 130, 130, 132, 135, 138, 139,
    141, 143, 145, 147, 149, 150, 152, 154, 155, 157, 159, 160, 161, 162, 164, 165,
    166, 168, 169, 170, 171, 172, 174, 175, 177, 178, 179, 180, 181, 183, 184, 185,
    186, 186, 186, 186, 186, 186, 186, 186, 186, 186, 186, 186, 186, 186, 186, 186,
    195, 201, 201, 202, 202, 202, 203, 204, 205, 207, 207, 208, 209, 209, 210, 210,
    211, 211, 212, 213, 213, 213, 213, 213, 216, 217, 217, 218, 219, 220, 221, 222,
    222, 223, 223, 224, 224, 225, 225, 225, 225, 225, 225, 225, 225, 225, 225, 225,
    225, 225, 225, 225, 225, 225, 225, 225, 225, 226, 226, 226, 226, 226, 226, 227,
    227, 228, 228, 229, 229, 230, 230, 231, 231, 232, 232, 233, 234, 234, 234, 235,
    235, 236, 236, 236, 237, 238, 238, 238, 239, 239, 240, 240, 240, 241, 241, 242,
    242, 243, 243, 244, 244, 244, 245, 245, 245, 246, 246, 246, 246, 247, 247, 248,
    248, 248, 248, 249, 249, 249, 249, 249, 250, 255, 255, 255, 255, 255, 255, 255,
], dtype=np.uint8)


def apply_hncs_learned(img_bgr, clahe_clip=1.25):
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    l = cv2.LUT(l, _LEARNED_LUT)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


# === day/night ===
# v1(day: 홍콩 3장, night: 한강 1장, 출처 불확실)로 만든 강한 그레이딩은
# 공식 샘플로 재검증하니 낮/밤 타깃이 거의 수렴함(day blackp2 13.4 vs
# night 15.0, 화이트 230.2 vs 228.5) - v1의 극단적 스타일은 "X1D 낮/밤
# 특성"이 아니라 그 사진 1~3장의 그레이딩(혹은 사진가 개인 스타일)이었을
# 가능성이 높음. v2(아래)는 공식 day 5장/night 4장 실측으로 되돌린 버전.
# day/night 타깃이 apply_hncs의 전체 population 타깃(11.3/223.9, v9
# 기준)과도 큰 차이가 없어서, 장기적으로는 apply_hncs 하나로 통합할
# 근거가 있음 - 아직 통합 작업은 안 함.

def apply_hasselblad_day(
    img_bgr,
    midtone_gamma=0.95,
    contrast_n=1.15,
    white_point=0.96,
    rolloff_start=0.80,
    saturation=1.0,
    clahe_clip=1.3,
):
    """
    v2: 공식 day 샘플 5장 실측 (아이슬란드폭포/타워브리지/숲개울인물/
    드레스인물/풀숲나비). 타깃 블랙p2=13.4, 화이트p99.5=230.2 (그림자유효
    5장/전체 8장) -> midtone_gamma 1.18->0.95, white_point 0.94->0.96,
    contrast_n 1.35->1.15. 재현: 블랙p2=12.8(목표13.4), 화이트p99.5=231.0
    (목표230.2).
    """
    # --- 톤: 전부 L채널 (색 보존 구조) ---
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    x = np.arange(256, dtype=np.float32) / 255.0
    y = x ** midtone_gamma          # 미드톤 다운
    y = s_curve(y, n=contrast_n)    # 깊은 블랙 + 대비
    y = apply_highlight_rolloff(x, y, start=rolloff_start)
    y = y * white_point             # 화이트포인트 압축
    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    # 마이크로 콘트라스트 (레퍼런스의 살아있는 텍스처)
    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    img_u8 = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

    # --- 채도 (hue 불변) ---
    if saturation != 1.0:
        hsv = cv2.cvtColor(img_u8, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] * saturation, 0, 255)
        img_u8 = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    return img_u8


def apply_hasselblad_night(
    img_bgr,
    black_out=0.02,      # v1: 0.07 (한강1장) -> 4장 풀링 시 축소
    white_out=0.88,      # v1: 0.65 -> 밤 타깃도 낮과 거의 같아 대폭 완화
    saturation=1.08,   # 실측 교훈: 핫셀 야경은 채도가 살아있는 압축 톤 (억제 아님)
    contrast_n=1.2,
    exposure_gamma=None, # None이면 자동 노출 정규화 (중앙명도 -> 0.21)
):
    """
    v2: 공식 night 샘플 4장 실측 (야간교량/도심야경자동차/유목해변/
    포르쉐주차장, 전부 그림자유효). 타깃 블랙p2=15.0, 화이트p99.5=228.5
    -> black_out 0.07->0.02, white_out 0.65->0.88. 재현: 블랙p2=14.2
    (목표15.0), 화이트p99.5=228.8(목표228.5).
    """
    # --- 0+1. 노출 정규화 + S커브를 모두 L채널에서 (색 보존) ---
    # BGR 감마 리프트는 min채널을 상대적으로 더 올려 채도를 죽임 -> L에서 수행
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    if exposure_gamma is None:
        valid = l[l > 3]  # 순흑 프레임 제외
        med = np.median(valid) / 255.0 if valid.size else 0.21
        exposure_gamma = float(np.clip(np.log(0.18) / np.log(max(med, 1e-4)), 0.35, 1.0))
    x = np.arange(256, dtype=np.float32) / 255.0
    y = s_curve(x ** exposure_gamma, n=contrast_n)
    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)
    img_u8 = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

    # --- 2. 채도 (hue 불변) ---
    hsv = cv2.cvtColor(img_u8, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * saturation, 0, 255)
    img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32) / 255.0

    # --- 3. DR 중앙 압축 (핵심): BGR 전 채널 [0,1] -> [black,white] ---
    # smoothstep 숄더로 상단 부드럽게 (하드클립 없이 white_out으로 수렴)
    hl = img > 0.6
    t = (img[hl] - 0.6) / 0.4
    img[hl] = 0.6 + (t * t * (3 - 2 * t)) * (white_out + 0.05 - 0.6)  # 최상단 광원만 white_out 약간 초과 허용
    img = black_out + img * (1.0 - black_out)

    return np.clip(img * 255, 0, 255).astype(np.uint8)
