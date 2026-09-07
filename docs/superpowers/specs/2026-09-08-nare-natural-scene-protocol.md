# NARE Protocol

**Natural-scene Appearance Reconstruction Evaluation**

NARE는 EAGER의 메인 실사진 검증 프로토콜이다. ColorChecker는 색도학적
calibration을 지원하고, Protocol 2R는 동일 물리 장면의 교차 카메라 확장이다.
NARE가 묻는 것은 실제 장면의 복잡한 색·톤·노출·질감 조건에서 RAW로부터
제조사 SOOC JPEG appearance를 재현하는가이다.

## 1. 데이터와 주장 경계

기본 단위는 같은 촬영에서 나온 `(R_i, J_i)` RAW/SOOC JPEG pair다.
pairing, 편집 없음, Picture Style/Film Simulation/Creative Look, WB, exposure,
ISO, lens metadata와 source hash를 manifest에 고정한다.

\[
\hat J_i=f(R_i),\qquad J_i=\text{manufacturer SOOC JPEG}
\]

NARE는 관측된 JPEG appearance를 주어진 데이터 범위에서 재현했다는 주장만
허용한다. 제조사 내부 알고리즘 복원이나 미관측 장면 일반화는 별도 증거다.

## 2. 독립 단위와 taxonomy

통계 표본은 pixel이나 image가 아니라 기본적으로 `scene`이다.

```text
pixel → ROI → image → scene → session → contributor
```

manifest는 lighting(daylight/overcast/tungsten/fluorescent/mixed), time,
scene type(portrait/landscape/urban/indoor/still-life), dynamic range,
dominant chroma, exposure, ISO, skin, foliage, sky, artificial-light strata를
기록한다. 각 stratum의 표본 수와 미검증 범위를 함께 보고한다.

## 3. 세 층 측정

**Global appearance**: mean/median/p90 ΔE00, ΔL*, ΔC*, hue error,
luminance SSIM.

**Semantic appearance**: skin, sky, foliage, neutral, saturated object,
shadow, highlight mask별 ΔE00을 별도 계산한다. aggregate가 subgroup 회귀를
숨기지 못하게 한다.

**Spatial appearance**: local contrast, highlight rolloff, shadow compression,
edge/local tone, texture/grain, local saturation을 색 정확도와 분리해 기록한다.

## 4. 등록과 제외

`geometry registration → valid-overlap mask → color evaluation` 순서를 지킨다.
crop, distortion/CA/lens correction, JPEG rescale을 보정한 뒤 registration
threshold를 넘으면 `registration_failure`로 사전 제외한다. clipping, dead/hot
pixel, motion, boundary, severe blur, decode corruption은 별도 mask/사유로
기록한다. specular highlight와 deep shadow는 임의 삭제하지 않고 subgroup으로
남긴다.

## 5. 고정 baseline과 통계

최소 세 조건을 비교한다.

```text
B0 = identity / RAW decoder baseline
B1 = colorimetric foundation only
C  = HNCS appearance candidate
```

scene별 `d_s = E_baseline,s - E_candidate,s`를 계산하고 scene만 resample하는
paired bootstrap과 exact sign test를 적용한다. pixel bootstrap은 금지한다.
native-ish와 1024px long-edge(또는 50%) 두 scale을 평가해 color와 spatial
차이를 분리한다.

## 6. 분할과 robustness

증거 단계는 unseen image < unseen scene < unseen session < unseen contributor
< unseen body < unseen camera model 순으로 강해진다. 같은 scene의 모든 파생본은
한 split에만 둔다. Protocol 2R는 마지막 단계의 별도 cross-camera 절차다.

aggregate 승리만으로 채택하지 않는다. lighting, scene, DR, ISO, skin,
saturation 등 각 robustness stratum에서 catastrophic regression을 검사한다.
최소 ship gate는 독립 scene 수, 평균 개선 5% 이상, scene bootstrap CI 하한 > 0,
paired sign test, 주요 subgroup 무악화, controls, provenance/accounting이다.
appearance claim에는 최소 3 lighting condition과 3 scene category를 요구한다.

## 7. 실패 분류와 accounting

다음 사유를 EAGER accounting에 그대로 넣는다.

```text
decode_failure, pair_mismatch, registration_failure, edited_jpeg,
wrong_picture_style, metadata_missing, duplicate_scene, motion_mismatch,
insufficient_overlap, clipping_excess, unsupported_raw
```

`requested → downloaded → decoded → provenance_valid → paired → group_valid →
evaluated`와 사유별 제외 합계를 reconciliation한다.

## 8. 결과 표현과 역할

결과는 “62 independent scenes across daylight, overcast, tungsten and mixed
light; portraits, landscapes, indoor and night scenes”처럼 scene 수와 coverage,
CI, 개선 scene 수, subgroup 결과를 함께 쓴다. `300 photos, +13%`만으로
일반화라고 부르지 않는다.

EAGER는 claim/evidence/ship 규칙을 제공하고, NARE가 HNCS의 주 검증 경로다.
ColorChecker는 supporting colorimetric evidence, Protocol 2R는 target-camera
reference가 있는 cross-camera extension이다. 실제 NARE 결과가 없을 때는
합성 smoke 수치를 photographic performance로 승격하지 않는다.
