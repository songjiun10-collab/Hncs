"""
후지필름 스타일 필름 시뮬레이션 프리셋 10종.

Astia/Pro Neg Std는 실측 검증됨(tools/analyze.py fuji_film_modes 모드,
mirrorlesscomparison.com 리뷰 갤러리의 RAW+SOOC JPEG에서 실제 Film Mode
태그(exiftool)별 population 비교) - 나머지는 대응하는 실측 라벨을 못
구해서(Eterna/Nostalgic Neg/Reala Ace/Acros 등은 이 사이트 표본에
없었음) 여전히 미검증 추정.

raw+jpeg "같은 사진" 페어를 노려봤지만(mirrorlesscomparison.com의 "RAW
samples"/"SOOC JPG samples" 폴더), 이 사이트는 애초에 같은 촬영을 짝지어
올린 게 아니라 그냥 각각 다른 사진들이었음 - 10개 카메라, RAW 57장+JPEG
40장을 받았는데 EXIF 촬영시각이 정확히 일치하는 페어는 3쌍뿐(그마저 다
Provia). raw 기반 캘리브레이션(핫셀블라드 v10~v12급)은 포기하고
population 비교로 전환.

Astia/Pro Neg Std에서 실제로 발견한 버그: 둘 다 실측과 정반대로 채도가
올랐음(Astia 실측 -12.9 vs 프리셋 +9.4, Pro Neg Std 실측 -19.4 vs 프리셋
+11.3). 원인은 톤커브를 BGR 채널에 개별로 걸어서(apply_lut) 채널 간
격차가 벌어지며 채도가 재상승하는 것(원본 125.0 -> HSV desaturation 후
109.4 -> BGR별 커브 후 139.7, 원본보다도 높아짐). hasselblad_hncs처럼
Lab L채널에만 커브를 적용하도록 두 프리셋 다 수정. Pro Neg Std는 L채널로
옮긴 뒤에도 여전히 반대 방향이었는데, 커브 모양 자체가 틀렸던 것으로
판명 - 기존엔 대비를 강조하는 S커브(n=1.4)를 썼는데 실측은 Pro Neg Std가
Provia보다 오히려 대비가 낮은 플랫한 프로파일(블랙p2 +2.7, 화이트p99.5
-19.0)이었음. 대비 완화 커브(n=0.65)로 교체. 수정 후 재검증: Astia 1/3
-> 2/3 방향 일치, Pro Neg Std 0/3 -> 3/3 방향 일치.

표본 확대(2026-07): mirrorlesscomparison.com 대신 imaging-resource.com의
신형 바디 리뷰 갤러리(X100V/X-T5/X-T4, exiftool FilmMode 태그가 살아있는
걸 확인)에서 269장(무결성 검증 통과분)을 추가로 모음 - Velvia 118장/
Provia 102장/Classic Negative 28장/Bleach Bypass 7장/Classic Chrome 2장.
이걸로:
- **Eterna Bleach Bypass 실측 검증**: 방향은 이미 다 맞았지만(sat/b2 감소,
  w995 증가) 강도가 부족(BGR 채널별 커브 버그로 의도한 채도 25%가 실제로는
  84%까지 재상승). Lab L채널 커브로 옮기고 재보정(sat_mult 0.25->0.32,
  대비커브 n=1.7, black_lift/white_point 추가) - RMSE 34.2 -> 2.8
- **Classic Negative 신규 추가**: 기존 8종에 없던 프리셋. 표본이 가장
  많이 확보돼서(28장) 새로 만듦 - Bleach Bypass와 같은 구조로 그리드서치
  피팅, RMSE=5.7
- Classic Chrome은 2장뿐이라 피팅 근거 부족, 추가 안 함

동일장면 비교차트 검증(2026-07, `tools/fuji_chart_calibrate.py`): 위
population 방식(서로 다른 사진들을 필름모드별로 모아 통계 비교)은
장면/노출 편향이 섞이는 한계가 있는데, 사용자가 리뷰 블로그/영상에서
직접 찾아 공유해준 "동일 장면을 여러 필름모드로 나란히 보여주는" 비교차트
8장(각기 다른 레이아웃 - 2x5/2x3/2x2 그리드, 대각선 5스트립, 세로
4스트립 등)을 `datasets/fuji/chart_comparisons/manifest.json`에 크롭박스
(box_frac, 사람이 육안으로 확인해서 기록 - 레이아웃이 이미지마다 달라서
자동 경계검출 대신 수동 확인이 더 신뢰도 높다고 판단)로 기록하고, Provia
베이스라인이 있는 차트는 실제 apply_* 함수를 그 차트의 Provia 크롭에
걸어 "같은 장면 페어" 기준 실측 delta vs 프리셋 delta를 비교했다
(`datasets/fuji/chart_comparison_stats.json`). 주요 발견:
- **Astia 모순 발견**: 이 실측(n=5, 채도 delta=+6.6)이 기존 population
  검증(17-27행, 채도가 낮아진다는 결론)과 반대 방향으로 나옴 - 표본이
  적어(양쪽 다 한 자릿수) 어느 쪽이 맞는지 판단 근거 부족. 기존 코드는
  안 건드림(이미 실사용 중인 걸 소표본 하나로 뒤집는 건 위험) - 표본이
  더 모이면 재확인 필요.
- **Pro Neg Hi/Eterna Cinema 리팩터+재보정**: 처음으로 실측 delta 확보
  (Pro Neg Hi n=3: 블랙p2 -19.0, 채도 +5.8 / Eterna Cinema, Provia 라벨이
  확실한 차트 1장 기준: 블랙p2 +6.0, 채도 -12.8) - 둘 다 대비커브를
  apply_lut()로 BGR 채널에 개별 적용하던 구조라(Astia/Pro Neg Std 때와
  같은 패턴) 강도가 실측보다 훨씬 과했음(Pro Neg Hi 채도 delta 실측 +5.8
  vs 기존프리셋 +23.2, Eterna Cinema 블랙p2 delta 실측 +6.0 vs 기존
  +32.5). Bleach Bypass/Classic Negative처럼 Lab L채널 커브 구조로
  리팩터하고 그리드서치로 재보정 - Pro Neg Hi는 3장 평균으로 상당히
  근접(채도 delta +6.5, 목표 +5.8), Eterna Cinema는 신뢰도 있는 차트가
  1장뿐이라 그 1장에 정확히 맞춘 것이라 과적합 위험이 있음(다른 차트
  1장은 무라벨 셀을 Provia로 추정한 것이라 튜닝에서 제외 - 그 차트까지
  포함한 집계에서는 채도 방향이 어긋남, 각 함수 docstring에 상세 기록).
- **Nostalgic Neg 버그 발견 및 부분 수정**: 실측(n=1) 채도 delta가 거의
  0(+0.8)인데 기존 구현은 +123까지 폭주 - Astia/Pro Neg Std 때와 같은
  BGR 채널별 조정+곱셈식 boost 버그. BGR 채널 조정 제거 + Lab a/b를
  가산식으로 변경해 +35까지 줄였지만 표본 1장으로 더 정밀하게 맞추는 건
  과적합이라 보류.
- **Acros/필터 4종**: 방향 전부 일치(채도 급감 확인) - 다만 블랙p2 하락
  폭이 프리셋이 실측의 약 2배(예: Acros 실측 -1.0 vs 프리셋 -12.0)로
  과함. Acros는 흑백 변환이라 sat delta는 항상 -58~-74 근처로 나오는데
  이건 그레이스케일 자체의 성질이라 정보량이 적음(프리셋도 그레이스케일
  변환이라 항상 같은 값) - b2 쪽 불일치가 더 의미 있는 신호.
- **Classic Negative**: n=1이지만 방향 대체로 일치(채도 -3.5 vs -6.4).
- Velvia는 이 프로젝트에 대응하는 apply_* 함수가 없어 비교 제외(raw
  실측 delta만 기록: n=5, 채도 +15.2 - 향후 프리셋 추가 시 참고).
- Reala Ace는 8장의 비교차트 어디에도 라벨이 없어 이번엔 검증 못 함.

DCP 카메라 프로필 교차검증(2026-07, `abpy/FujifilmCameraProfiles` 레포
리서치): 이 레포는 Adobe DCP(DNG Camera Profile) 형식으로 8개 필름
시뮬레이션(Provia/Velvia/Astia/Classic Chrome/Eterna/Pro Neg Std/Pro Neg
Hi/Reala Ace)의 LookTable(72 hue x 12 sat x 16 value 격자, 노드별
HueShift/SatScale/ValScale)과 128점 ToneCurve를 XML로 제공 - population/
동일장면차트와는 완전히 다른, Adobe가 카메라 자체를 분석해서 만든
독립적인 세 번째 소스. 이 프로젝트의 실측(Provia 대비 delta)과 같은
기준으로 보려고 SatScale을 Provia 기준 상대값으로 환산해서 비교:

| 프리셋 | DCP SatScale(Provia 대비) | 이 프로젝트 실측/코드 | 방향 일치? |
|---|---|---|---|
| Velvia | +8.4% | (미구현, raw delta +15.2 참고용) | 방향 일치(둘 다 증가) |
| Astia | +2.3% | 챠트 n=5: +6.6 / population: -12.9(모순, 27행) / 코드: a·b×0.85(감소) | 챠트와는 일치, population/코드와는 불일치 - **population vs 챠트 모순에 DCP가 챠트 쪽에 한 표 추가** |
| Pro Neg Std | -8.7% | population: -19.4 / 코드: HSV sat×0.85(감소) | 방향 일치 |
| Pro Neg Hi | -8.1% | 챠트 n=3: +5.8 / 코드: sat_mult=1.10(증가) | **불일치** - DCP는 감소, 챠트+코드는 증가. 새로운 모순 발견, 표본 더 필요 |
| Eterna | -11.7% | 챠트 n=1: -12.8 / 코드: sat_mult=0.55(큰 폭 감소) | 방향+대략적 크기 일치(단위가 달라 직접 비교는 아님) |
| Classic Chrome | -15.8%(8개 중 가장 저채도) | population n=2뿐이라 미구현 | (비교 대상 코드 없음 - 향후 프리셋 추가 시 참고 자료로 남김) |

DCP LookTable은 Adobe가 카메라 JPEG 엔진과 별개로 만드는 "Look" 보정이라
실제 SOOC JPEG 렌더링과 철학이 다를 수 있다는 캐비어트가 있다(이 프로젝트
다른 곳의 "미검증" 라벨과 같은 성격) - 그래서 이 표만으로 기존 코드를
바로 고치지는 않았다. 다만 Astia는 이제 독립적인 두 소스(챠트+DCP)가
"더 채도 높음" 쪽을 가리키는데 코드는 population 쪽(채도 감소)을
따르고 있어 재검토 우선순위가 높아졌고, Pro Neg Hi는 반대로 챠트+코드가
"더 채도 높음"인데 DCP가 "더 낮음"이라는 새로운 모순이 생겼다 - 둘 다
표본이 늘어나면 우선 재확인할 항목으로 남긴다.

**Provia 추가 - raw+jpeg 페어 확보(2026-08)**: 위에서 "이 사이트는 애초에
같은 촬영을 짝지어 올린 게 아니다"라며 포기했던 raw 기반 캘리브레이션을,
로컬 raw+jpeg 라이브러리에 GFX100RF(.raf)+X-T30 III(.raf) 페어가 새로
들어오면서 다시 시도했다 - 이번엔 EXIF DateTimeOriginal이 실제로
일치하는 진짜 같은 촬영 페어. 두 바디 JPEG 전부 FilmMode가
"F0/Standard (Provia)"였는데, 이 파일엔 Provia 프리셋이 아예 없었어서
raw 신호로 직접 새로 그리드서치(`tools/evaluate_new_body_de00_grid.py`
- baseline 없이 가공 없는 중립 렌더 자체를 기준으로 삼는
`--baseline-identity`, 저해상도 선택 -> 400px 확정 ->
`tools/evaluate_native_pixel_confirm.py`로 원본 픽셀(max_dim=3000)
재확인)했다.

| 바디 | n | 개선폭(LOO) | 개선폭(원본 픽셀) | 부호검정 p | 부트스트랩 95% CI(픽셀) |
|---|---|---|---|---|---|
| GFX100RF | 38 | +20.16% | +18.82% | <0.0001 | [+2.792, +3.763] |
| X-T30 III | 20 | +27.13% | +23.65% | <0.0001 | [+2.849, +3.927] |

baseline이 가공 없는 raw 중립 렌더라 개선폭 자체는 크게 나오는 게
당연하지만(다른 브랜드처럼 기존 apply_* 함수와의 근소한 차이가 아니라
"커브를 아예 안 씌운 것" 대비), 두 바디 모두 폴드 전원일치(38/38,
20/20)로 나온 조합이 GFX100RF `toe_lift=0.0, shoulder_start=0.82,
white_point=1.0`, X-T30 III `toe_lift=0.02, shoulder_start=0.82,
white_point=1.0`로 사실상 같다 - `apply_leica_raw_look`의 4바디 수렴값과
동일해서(brands/leica_raw.py 이력 참고) 우연이라 보기 어려움. 표본이
더 작은 X-T30 III(n=20) 대신 GFX100RF(n=38) 값을 기본값으로 채택. 재현:
`python3 -m tools.evaluate_new_body_de00_grid --label "Fuji GFX100RF
Provia" --manifest datasets/fuji/fuji_new_pairs.csv --raw-dir
"/Users/songjiun/local-work" --model GFX100RF --baseline-identity`.

**Provia 3바디 통합 재확인 (2026-08)**: GFX50S II Provia 9쌍이 추가돼서
GFX100RF+X-T30 III+GFX50S II 전체(67쌍)를 한 그리드서치로 통합
재검증했다 - 개선폭 +19.06%, 63승4패, 부호검정 p<0.0001, 부트스트랩
95% CI [+2.731, +3.556]. 65/67 폴드가 `toe_lift=0.0, shoulder_start=0.82,
white_point=1.0`로 수렴 - 기존 채택값과 정확히 일치, 세 번째 바디를
더해도 값이 안 바뀜(기존 결론 재확인).
"""
import cv2
import numpy as np

from core.curve import apply_highlight_rolloff, film_curve, s_curve
from core.lut import apply_lut, ensure_uint8


# ==========================================
# 1. Astia/Soft (부드러운 색감, 인물용) - 실측 검증됨
# ==========================================
def apply_astia(img_bgr):
    img = ensure_uint8(img_bgr).astype(np.float32)
    img[:, :, 2] = np.clip(img[:, :, 2] * 1.03, 0, 255)  # R
    img[:, :, 0] = np.clip(img[:, :, 0] * 0.97, 0, 255)  # B
    img = img.astype(np.uint8)

    img_lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(img_lab)
    # 실측: Astia는 Provia보다 채도가 낮음(부드러운 색감) - a/b를 중심
    # (128)으로 당겨서 채도를 낮춤
    a = np.clip(128 + (a.astype(np.float32) - 128) * 0.85, 0, 255).astype(np.uint8)
    b = np.clip(128 + (b.astype(np.float32) - 128) * 0.85, 0, 255).astype(np.uint8)

    # 하이라이트만 소프트하게 압축 - L채널에만 적용해서 hue/채도 보존
    x = np.arange(256, dtype=np.float32) / 255.0
    y = x.copy()
    y = apply_highlight_rolloff(x, y, start=0.7)
    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


# ==========================================
# 2. PRO Neg. Std (스튜디오 인물용, 부드러움) - 실측 검증됨
# ==========================================
def apply_pro_neg_std(img_bgr):
    img_hsv = cv2.cvtColor(ensure_uint8(img_bgr), cv2.COLOR_BGR2HSV).astype(np.float32)
    img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1] * 0.85, 0, 255)
    img = cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    # 실측: 실제 Pro Neg Std는 Provia보다 대비가 낮은 플랫 프로파일이라
    # n<1(대비 완화) 사용
    x = np.arange(256, dtype=np.float32) / 255.0
    y = s_curve(x, n=0.65)
    lut = np.clip(y * 255, 0, 255).astype(np.uint8)

    # L채널에만 적용해서 desaturation이 유지되도록 함 (BGR 채널별로 걸면
    # 채도가 재상승하는 버그가 있었음)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.LUT(l, lut)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


# ==========================================
# 3. PRO Neg. Hi (Std + 콘트라스트 강화) - 실측 검증됨(2026-07, n=3, 동일장면 비교차트)
# ==========================================
def apply_pro_neg_hi(img_bgr, sat_mult=1.10, contrast_n=1.7, clahe_clip=1.5):
    """
    2026-07 동일장면 비교차트 실측(n=3): 기존 구현은 대비커브를
    apply_lut()로 BGR 채널에 개별 적용해서(Astia/Pro Neg Std 때와 같은
    패턴) 채도가 실측보다 훨씬 크게 뜸(예: 채도 delta 실측 +5.8 vs 프리셋
    +23.2). Lab L채널에만 커브+CLAHE를 걸도록 바꾸고 그리드서치로 재보정
    (HSV desaturation 0.85 -> saturation 배율 1.10로 반전 - 실측은 Pro
    Neg Hi가 Provia보다 오히려 살짝 더 채도가 높았음, contrast_n
    2.2->1.7) - RMSE 개선(3장 평균 기준).
    """
    img = ensure_uint8(img_bgr)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    x = np.arange(256, dtype=np.float32) / 255.0
    y = s_curve(x, n=contrast_n)
    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    img_u8 = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    hsv = cv2.cvtColor(img_u8, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * sat_mult, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


# ==========================================
# 4. Eterna/Cinema (영화 느낌, 플랫, 틸 쉐도우) - 실측 일부 검증(2026-07, n=1, 동일장면 비교차트)
# ==========================================
def apply_eterna_cinema(img_bgr, sat_mult=0.55, black_lift=0.04, white_point=0.90):
    """
    2026-07 동일장면 비교차트 실측(Provia 라벨이 확실한 차트 1장 기준 -
    다른 차트 하나는 무라벨 셀을 Provia로 추정한 것이라 신뢰도 낮아 튜닝엔
    제외): 기존 구현은 flatten 커브를 apply_lut()로 BGR 채널에 개별
    적용했고(black_lift=0.15로 과하게 밝힘) 블랙p2 delta가 실측(+6.0)의
    5배 이상(+30~35)으로 떴음. Lab L채널에만 커브를 걸도록 바꾸고
    black_lift/white_point/sat_mult를 그 차트 1장에 맞춰 재보정(0.15->0.04,
    0.85->0.90, 0.65->0.55) - 정확히 맞긴 하지만 표본이 1장뿐이라 과적합
    위험 있음, 표본이 더 모이면 재확인 필요.
    """
    img = ensure_uint8(img_bgr)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip((black_lift + x * (white_point - black_lift)) * 255, 0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)
    l_float = l.astype(np.float32) / 255.0

    shadow_weight = np.clip(1.0 - (l_float * 2.0), 0, 1)
    a = np.clip(a.astype(np.float32) - (shadow_weight * 15), 0, 255).astype(np.uint8)
    b = np.clip(b.astype(np.float32) - (shadow_weight * 10), 0, 255).astype(np.uint8)

    img_shifted = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

    img_hsv = cv2.cvtColor(img_shifted, cv2.COLOR_BGR2HSV).astype(np.float32)
    img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1] * sat_mult, 0, 255)
    return cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


# ==========================================
# 5. Eterna Bleach Bypass (표백 현상, 저채도 고대비) - 실측 검증됨
# ==========================================
def apply_eterna_bleach_bypass(img_bgr, sat_mult=0.32, contrast_n=1.7,
                                black_lift=0.02, white_point=1.0):
    """
    실측 검증(2026-07, imaging-resource.com X100V/X-T5/X-T4 리뷰 갤러리,
    Bleach Bypass 태그 7장 vs Provia 102장): 원래 채도를 BGR 각 채널에
    apply_lut()(=cv2.LUT을 B/G/R에 개별 적용)로 대비 커브를 걸어서, 채널
    간 격차가 벌어지며 의도한 저채도가 절반 가까이 재상승하는 문제가
    있었음(Astia/Pro Neg Std 때와 같은 버그 패턴) - Lab L채널에만 대비
    커브를 적용하도록 수정.

    타깃(실측): 블랙p2=12.9, 화이트p99.5=250.1, 채도=54.7 (Provia 대비
    sat 0.53배, b2 -6.4, w995 +14.0). 그리드서치로 sat_mult/contrast_n/
    black_lift 재보정 - 기존(sat_mult=0.25 단순곱, BGR 채널별 커브) RMSE
    34.2 -> 신규(Lab L채널 커브) RMSE 2.8.
    """
    lab = cv2.cvtColor(ensure_uint8(img_bgr), cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    x = np.arange(256, dtype=np.float32) / 255.0
    y = s_curve(x, n=contrast_n)
    lut = np.clip((black_lift + y * (white_point - black_lift)) * 255, 0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)
    img_u8 = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

    hsv = cv2.cvtColor(img_u8, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * sat_mult, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


# ==========================================
# 6. Nostalgic Neg (빈티지, 따뜻한 앰버 강조) - 실측 일부 검증(2026-07, n=1)
# ==========================================
def apply_nostalgic_neg(img_bgr):
    """
    2026-07 동일장면 비교차트 실측(사용자가 직접 찾아 공유한 차트 1장,
    n=1이라 확정적이진 않음): 채도 delta가 거의 0(+0.8)에 가까운데, 기존
    구현은 BGR R/B 채널을 각각 배율(x1.1/x0.9)로 조정한 뒤 Lab a/b까지
    128 초과분에 배율(x1.1/x1.15)로 boost를 걸어서 두 단계가 겹치며
    채도가 +123까지 폭주했음 - Astia/Pro Neg Std/Bleach Bypass 때 이미
    겪은 "BGR 채널별 조정 + 곱셈식 boost가 채도를 과도하게 재상승시키는"
    것과 같은 버그 패턴. BGR 채널 조정을 없애고 a/b를 곱셈이 아니라 고정량
    가산(+6/+8)으로 바꿔서 이미 채도가 높은 픽셀에서 폭주하지 않게 수정 -
    수정 후 채도 delta는 +35까지 줄었지만(123 -> 35) 실측 목표(+0.8)에는
    아직 못 미침. 표본이 1장뿐이라 이 이상 그리드서치로 정밀 맞추는 건
    과적합 위험이 커서(포트레이트/빌딩 장면 하나에만 맞추는 꼴) 보류 -
    표본이 더 모이면 재보정.

    **정정(2026-08) - raw+jpeg 페어 27쌍으로 직접 검증하니 방향 자체가
    틀렸음**: GFX50S II Nostalgic Neg raw+jpeg 27쌍에 이 함수를 그대로
    적용해 ΔE00을 재보고 실측했더니, **가공 없는 raw 원본이 이 함수보다도
    ΔE00이 더 낮았다**(개선폭 -2.13%, 부트스트랩 95% CI [-0.936, -0.133],
    0을 포함하지 않는 음수 - `tools/evaluate_fuji_preset_de00.py`). n=1
    비교차트 기반 수작업 튜닝(앰버 틴트 가산)이 실제 카메라 JPEG와
    반대 방향이었다는 뜻. `apply_nostalgic_neg_v2()`(아래, raw+jpeg
    기반 재도출)로 대체 권장 - 이 함수 자체는 과거 기록 보존 목적으로
    코드는 안 건드리고 남겨둔다.
    """
    img = ensure_uint8(img_bgr)
    img_lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(img_lab)
    a = np.where(a > 128, np.clip(a.astype(np.float32) + 6, 0, 255), a).astype(np.uint8)
    b = np.where(b > 128, np.clip(b.astype(np.float32) + 8, 0, 255), b).astype(np.uint8)

    l_float = l.astype(np.float32) / 255.0
    l_float = np.where(l_float > 0.8, 0.8 + (l_float - 0.8) * 0.5, l_float)
    l = np.clip(l_float * 255, 0, 255).astype(np.uint8)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


# ==========================================
# 7. Reala Ace (정확한 색 재현, 정직한 룩) - 미검증
# ==========================================
# 2026-08 코드리뷰: 이 파일의 다른 5개 프리셋(Astia/Pro Neg Std/Hi,
# Bleach Bypass, Nostalgic Neg)이 겪었던 "apply_lut()로 BGR 채널별 커브를
# 걸면 채도가 실측보다 크게 뜨는" 버그를 이 함수도 반복하는지 확인차
# raw+jpeg 실측(X-T30 III Reala ACE, n=2)했음 - 현재 구현(HSV desaturation
# + BGR apply_lut)과 Lab L채널 전용으로 바꾼 후보를 비교한 결과 ΔE00(raw
# 대비 18.014→18.013, 19.127→19.126)과 채도 델타 모두 유의미한 차이 없음.
# n=2라 판정 자체가 안 되는 표본(이 프로젝트 기준 8개 미만은 보류)이기도
# 해서 수정하지 않음 - 여전히 미검증 상태로 둔다.
def apply_reala_ace(img_bgr):
    img_bgr = ensure_uint8(img_bgr)

    img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1] * 0.95, 0, 255)
    img = cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    x = np.arange(256, dtype=np.float32) / 255.0
    y = x.copy()
    y = apply_highlight_rolloff(x, y, start=0.85)

    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    return apply_lut(img, lut)


# ==========================================
# 8. Acros / Monochrome (흑백) - 미검증
# ==========================================
def apply_acros(img_bgr, filter_type='none'):
    b, g, r = cv2.split(ensure_uint8(img_bgr))

    if filter_type == 'red':
        gray = (0.1 * b + 0.3 * g + 0.6 * r)
    elif filter_type == 'green':
        gray = (0.1 * b + 0.7 * g + 0.2 * r)
    elif filter_type == 'yellow':
        gray = (0.15 * b + 0.65 * g + 0.2 * r)
    else:
        gray = (0.2 * b + 0.6 * g + 0.2 * r)

    gray = np.clip(gray, 0, 255).astype(np.uint8)

    x = np.arange(256, dtype=np.float32) / 255.0
    y = s_curve(x, n=1.6)
    y = apply_highlight_rolloff(x, y, start=0.9)

    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    return cv2.LUT(gray, lut)


def apply_monochrome(img_bgr):
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)


# ==========================================
# 9. Classic Negative (무채색에 가까운 저채도, 필름네거티브 톤) - 실측 검증됨
# ==========================================
def apply_classic_negative(img_bgr, sat_mult=0.65, contrast_n=1.4,
                            black_lift=0.03, white_point=1.05):
    """
    실측 검증(2026-07, imaging-resource.com X100V/X-T5/X-T4 리뷰 갤러리,
    Classic Negative 태그 28장 vs Provia 102장) - 이 프로젝트에서
    Classic Negative를 다루는 건 이번이 처음(기존 8종엔 없었음, 표본이
    가장 많이 확보돼서 새로 추가).

    타깃(실측): 블랙p2=11.3, 화이트p99.5=249.6, 채도=81.4 (Provia 대비
    sat 0.79배, b2 -8.0, w995 +13.5 - Bleach Bypass보다는 덜 극단적인
    저채도/고대비). Eterna Bleach Bypass와 동일한 구조(Lab L채널 대비
    커브 + HSV 채도 배율)로 그리드서치 피팅, RMSE=5.7.
    """
    lab = cv2.cvtColor(ensure_uint8(img_bgr), cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    x = np.arange(256, dtype=np.float32) / 255.0
    y = s_curve(x, n=contrast_n)
    lut = np.clip((black_lift + y * (white_point - black_lift)) * 255, 0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)
    img_u8 = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

    hsv = cv2.cvtColor(img_u8, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * sat_mult, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


# ==========================================
# 10. PRO Neg. Hi 비디오 전용 변형 (CLAHE 생략) - tools/video_engine.py가 사용
# ==========================================
def apply_pro_neg_hi_video_frame(img_bgr, sat_mult=1.10, contrast_n=1.7):
    """apply_pro_neg_hi()의 비디오 전용 변형 - CLAHE(프레임별 적응형
    로컬 대비 보정)를 생략해 프레임 간 깜빡임을 피한다. 사진 모드와
    동일한 출력이 아니다(로컬 대비가 약함)."""
    img = ensure_uint8(img_bgr)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    x = np.arange(256, dtype=np.float32) / 255.0
    y = s_curve(x, n=contrast_n)
    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    img_u8 = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    hsv = cv2.cvtColor(img_u8, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * sat_mult, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


# ==========================================
# 11. Provia/Standard (기본 필름모드) - raw+jpeg 페어 실측 검증됨(2026-08, GFX100RF n=38/X-T30 III n=20)
# ==========================================
def apply_provia(img_bgr, toe_lift=0.0, shoulder_start=0.82, white_point=1.0, clahe_clip=1.25):
    img = ensure_uint8(img_bgr)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


# ==========================================
# 12. Classic Chrome - raw+jpeg 페어 실측 검증됨(2026-08, GFX50S II n=39)
# ==========================================
def apply_classic_chrome(img_bgr, toe_lift=0.0, shoulder_start=0.70, white_point=1.0, clahe_clip=1.25):
    """이 파일에 대응 프리셋이 아예 없던 필름모드 - GFX50S II Classic
    Chrome raw+jpeg 43쌍(디코드 성공 39쌍)으로 `apply_provia`와 같은
    방식(무가공 raw 대비 ΔE00 직접 그리드서치+LOO,
    `tools/evaluate_new_body_de00_grid.py --baseline-identity`)으로
    처음부터 새로 만들었다.

    개선폭 +5.60%, 30승9패, 부호검정 p=0.0011, 부트스트랩 95% CI
    [+0.601, +1.556](픽셀단위 재확인은 아직 안 함, 저해상도 그리드서치
    LOO 값). 폴드 선택이 shoulder_start=0.66(15/39)과 0.70(15/39)로
    타이 - 0.82(9/39)까지 셋으로 갈려서 다른 프리셋들처럼 만장일치가
    아님(toe_lift=0/white_point=1.0은 39/39 만장일치). 중간값인 0.70을
    기본값으로 채택 - 표본이 더 모이면 셋 중 어디로 수렴하는지
    재확인 필요.

    **정정(2026-08, 코드리뷰로 발견)**: 이 폴드 3분할 자체가 데이터
    오염 때문이었다 - `tools/build_local_manifest.py`의 페어 매칭
    버그(비단조/비결정적 매칭, 별도 커밋으로 수정)로
    `datasets/fuji/fuji_new_pairs.csv`의 GFX50S II Classic Chrome
    43쌍 중 상당수가 버스트 촬영 구간에서 엉뚱한 jpeg와 짝지어져
    있었음(카메라 자체 넘버링 대조로 확인). 데이터셋을 고쳐서
    재검증한 결과는 `apply_classic_chrome_v2()`(아래) - 이 함수는
    그대로 두고 나란히 둔다."""
    img = ensure_uint8(img_bgr)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


# ==========================================
# 12b. Classic Chrome v2 - 페어 매칭 버그 수정 후 재도출(2026-08, GFX50S II n=42)
# ==========================================
def apply_classic_chrome_v2(img_bgr, toe_lift=0.0, shoulder_start=0.82, white_point=1.0, clahe_clip=1.25):
    """`apply_classic_chrome()`(위)의 정정판. `tools/build_local_manifest.py`
    페어 매칭 버그 수정 후 `datasets/fuji/fuji_new_pairs.csv`를
    재생성(GFX50S II Classic Chrome 46쌍, 디코드 성공 42쌍)하고 같은
    방식(`tools/evaluate_new_body_de00_grid.py --baseline-identity`)으로
    처음부터 재그리드서치했다.

    개선폭 +22.54%(구버전 +5.60%보다 훨씬 큼), 37승5패, 부호검정
    p<0.0001, 부트스트랩 95% CI [+2.018, +2.955]. 폴드 선택이
    toe_lift=0.0/shoulder_start=0.82/white_point=1.0으로 **42/42
    만장일치** - 구버전의 3파전(0.66/0.70/0.82) 자체가 오염된 데이터의
    아티팩트였다는 뜻. `apply_provia`(GFX100RF)와 우연히 완전히 같은
    파라미터로 수렴했다 - 세션 초반 "라이카/후지 파라미터 동일" 건이
    그리드 해상도 우연이었던 전례가 있어서(docs/measurements.md) 이것도
    같은 카메라의 진짜 공통 커브인지 그리드 우연인지는 아직 별도로
    검증 안 됨, 과대해석 자제. 재현: `python3 -m
    tools.evaluate_new_body_de00_grid --label "Fuji GFX50S II Classic
    Chrome" --manifest <film_mode=="Classic Chrome" 행> --raw-dir
    "/Users/songjiun/local-work" --baseline-identity`."""
    img = ensure_uint8(img_bgr)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


# ==========================================
# 13. Nostalgic Neg v2 - raw+jpeg 재도출판(2026-08, GFX50S II n=27), apply_nostalgic_neg 대체
# ==========================================
def apply_nostalgic_neg_v2(img_bgr, toe_lift=0.036, shoulder_start=0.82, white_point=0.85, clahe_clip=1.25):
    """`apply_nostalgic_neg()`(위, n=1 비교차트 수작업 튜닝)가 GFX50S II
    Nostalgic Neg raw+jpeg 27쌍 실측에서 **raw 원본보다도 못한 것**으로
    드러나서(개선폭 -2.13%, CI [-0.936, -0.133], 0 미포함 - 방향 자체가
    틀림) `apply_provia`/`apply_classic_chrome`과 같은 방식으로 무가공
    raw 대비 처음부터 다시 그리드서치했다.

    개선폭 +6.13%, 21승6패, 부호검정 p=0.0059, 부트스트랩 95% CI
    [+0.839, +2.330]. 25/27 폴드가 `toe_lift=0.036, shoulder_start=0.82,
    white_point=0.85`로 수렴(나머지 2폴드는 toe_lift=0.09만 다름) -
    기존 앰버 틴트/하이라이트 압축 방식과 전혀 다른 파라미터 공간이라
    실측이 실제로 다른 방향을 가리키고 있었다는 뜻. 재현:
    `python3 -m tools.evaluate_new_body_de00_grid --label
    "Fuji GFX50S II Nostalgic Neg" --manifest
    /tmp/fuji_nostalgic_neg.csv --raw-dir "/Users/songjiun/local-work"
    --baseline-identity`(매니페스트는 `datasets/fuji/fuji_new_pairs.csv`의
    film_mode=="Nostalgic Neg" 행).

    **정정(2026-08, 코드리뷰로 발견)**: 이 27쌍도 Classic Chrome과 같은
    `tools/build_local_manifest.py` 페어 매칭 버그(별도 커밋으로 수정)에
    오염돼 있었다. 데이터셋을 고쳐서 재검증한 결과는
    `apply_nostalgic_neg_v3()`(아래) - 이 함수는 그대로 두고 나란히
    둔다."""
    img = ensure_uint8(img_bgr)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


# ==========================================
# 13b. Nostalgic Neg v3 - 페어 매칭 버그 수정 후 재도출(2026-08, GFX50S II n=28)
# ==========================================
def apply_nostalgic_neg_v3(img_bgr, toe_lift=0.0, shoulder_start=0.82, white_point=1.0, clahe_clip=1.25):
    """`apply_nostalgic_neg_v2()`(위)의 정정판. `tools/build_local_manifest.py`
    페어 매칭 버그 수정 후 `datasets/fuji/fuji_new_pairs.csv`를
    재생성(GFX50S II Nostalgic Neg 28쌍, 전부 디코드 성공)하고 같은
    방식(`tools/evaluate_new_body_de00_grid.py --baseline-identity`)으로
    처음부터 재그리드서치했다.

    개선폭 +18.14%(v2의 +6.13%보다 훨씬 큼), **28승0패 만장일치**,
    부호검정 p<0.0001, 부트스트랩 95% CI [+1.748, +2.643]. 폴드 선택도
    toe_lift=0.0/shoulder_start=0.82/white_point=1.0으로 28/28 만장일치 -
    v2가 찾은 `toe_lift=0.036/white_point=0.85`는 오염된 데이터의
    아티팩트였다는 뜻. `apply_classic_chrome_v2()`/`apply_provia`
    (GFX100RF)와 우연히 완전히 같은 파라미터로 수렴했다 - 과대해석
    자제 사유는 `apply_classic_chrome_v2()` docstring 참고. 재현:
    `python3 -m tools.evaluate_new_body_de00_grid --label "Fuji GFX50S
    II Nostalgic Neg" --manifest <film_mode=="Nostalgic Neg" 행>
    --raw-dir "/Users/songjiun/local-work" --baseline-identity`."""
    img = ensure_uint8(img_bgr)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
