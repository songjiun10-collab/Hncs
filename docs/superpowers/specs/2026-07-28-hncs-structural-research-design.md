# HNCS 공식 파이프라인 구조 리서치 + 구조 동일시 실험 모듈

## 배경 / 문제

`brands/hasselblad.py`의 `apply_hncs()`(⭐ 공식 Stable, v8~v12에 걸쳐
raw+jpeg 페어 10~13장으로 반복 보정, RMSE 23.3)는 Hasselblad 공식
사이트에서 조사한 "문서화된 HNCS 설계 원칙" 5가지(필름커브 톤, 지각보상
대비, rich saturation 무조작, 스킨톤 hue/채도 무조작, X시스템 전체 일관
적용)를 근거로 만들어졌다. 그런데 이 원칙들은 "hue/채도를 아예 안
건드린다"는 단순화를 전제로 하고, 실제 파이프라인은 `exposure_gamma`
LUT → CLAHE → `film_curve` LUT 3단계뿐이다.

이 스펙은 HNCS의 실제 렌더 파이프라인 구조를 다시 조사하고, 지금
구현이 놓치고 있는 구조적 차이가 있다면 그 구조를 반영한 별도의
**실험적** 모듈을 만들어 "구조를 더 정확히 따라가면 실제로 정확도가
좋아지는가"를 실측으로 확인한다. `apply_hncs()`(이미 실측 검증되고
실사용 중인 Stable 버전)는 전혀 건드리지 않는다.

## 조사 결과 (설계 단계에서 확인)

**출처**: Hasselblad 공식 사이트(hasselblad.com/learn/hasselblad-natural-colour-solution)
+ Phocus `.phos` 사이드카를 실제로 바이트 단위로 diff한 독립 기술 분석
(blog.tonalphoto.com, "How HNCS Actually Works" - 저자 본인이 명시:
"공식 지원/가이드 아님, 개인적 조사와 테스트"). **공식 화이트페이퍼는
존재하지 않는다** - 검색으로 확인.

**실제 렌더 파이프라인은 4단계**(Phocus가 3FR을 열 때마다 실행, 화이트밸런스가
바뀌면 2단계부터 전체 재실행):
1. RAW 센서 데이터 (16비트)
2. **조명별(illuminant-specific) 3×3 컬러 매트릭스** - 최소 4종
   (Tungsten/Low Tungsten/Flash/Flash-Daylight, 이 구체적 개수는
   Luminous Landscape 포럼의 커뮤니티 기술 분석 출처이지 Hasselblad가
   공개한 숫자는 아님) 중 WB 설정에 따라 선택
3. **그 매트릭스와 짝지어진 chroma LUT** - 해당 광원에 맞춘 hue/채도 보정
4. Hasselblad Film Curve (하이라이트 롤오프 + 섀도우 전환을 다루는
   톤커브)

**프리셋(Standard/Nature/Portrait/Product/Square Crop)은 색과학을 안
바꾼다** - `.phos` 사이드카 직접 비교 결과 Brightness/Contrast/Saturation은
5개 프리셋 전부 0/0/0으로 동일, 차이는 샤프닝 강도와 톤커브뿐. 즉
"프리셋 간에는 채도 조작이 없다"는 지금 코드의 가정은 **프리셋
비교에서는 맞지만**, 그게 "파이프라인 전체에 채도 보정이 없다"는
뜻은 아니었다 - 3단계(조명별 chroma LUT)는 프리셋과 무관하게 항상
존재하는 별도 단계다.

**데이터 재확인**(설계 단계 실측): 이 프로젝트가 이미 캐시해둔 raw+jpeg
페어 원본 파일(`raw_calib_cache/*.3FR`, `*.fff`, 15장)에서 `exiftool
-AsShotNeutral`을 직접 뽑아봤다. R/B 비율이 뚜렷이 두 클러스터로
갈린다: 0.34~0.45(데이라이트/그늘 계열, 예: x1d-II-sample-01/02/06,
x1d-xcd45-01/03/04, x2dii-chart-*) vs 0.48~0.57(따뜻한/텅스텐 계열,
예: B0000994, x1d-II-sample-09, 02709). 공식 구조가 말하는 "최소 4개
조명"까지 표본이 안 되지만(15장을 4개로 쪼개면 클러스터당 3~4장),
**2-클러스터 모델은 이 데이터로 시도해볼 근거가 있다**.

## 목표

1. HNCS 실제 파이프라인 구조를 출처와 함께 정리한 리서치 문서를
   남긴다 - 지금 `apply_hncs()`가 어디서 어떻게 단순화했는지 구조
   대비로 명시.
2. 그 구조(조명별 매트릭스 + 조명별 chroma LUT + 공유 필름커브)를
   반영한 실험적 코드 모듈을 `apply_hncs()`와 완전히 별도로 만든다.
3. leave-one-out 교차검증으로 "구조를 실제에 더 가깝게 만들면 ΔE가
   실제로 좋아지는가"를 실측하고, 이기든 지든 `hybrid_engine/EVALUATION.md`에
   정직하게 기록한다(이 프로젝트의 기존 관례).

## 범위 밖

- **`brands/hasselblad.py`의 `apply_hncs()` 수정** - Stable 버전은
  건드리지 않는다. 이 실험이 이기더라도 이 스펙에서 교체하지 않는다
  (승격은 별도 논의 - 최소한 이 스펙에서는 "실험 결과 기록"까지만).
- **4개 이상의 조명 클러스터** - 표본(15장)이 못 뒷받침한다.
  2-클러스터(데이라이트계/따뜻한계)로 제한.
- **비디오 엔진 통합** - 이 실험 모듈은 정지 RAW 한 장을 다루는
  연구용 코드고, `tools/video_engine.py`에 새 브랜드로 추가하지
  않는다(그 자체로 별도 스펙 - Stable로 승격된 뒤에나 고려할 일).
- **Phocus의 실제 조명별 매트릭스/LUT 값 재현** - Hasselblad 비공개
  자산이라 우리가 가진 데이터로 새로 피팅한 근사치일 뿐, Phocus와
  동일한 숫자가 아니다. 이 한계를 코드/문서에 명시.
- **HDR 파이프라인** - 조사 출처(tonalphoto.com)가 명시적으로 "HNCS
  위에 별도로 얹히는 파이프라인이라 이 글에서 안 다룬다"고 한 부분 -
  이 스펙도 동일하게 범위 밖.

## 설계

### 리서치 문서

`docs/hncs_structural_research.md` + `docs/hncs_structural_research.en.md`
(가칭, 이 프로젝트의 기존 `docs/*.md`는 전부 한/영 쌍으로 존재하는
관례 - `brands.md`/`brands.en.md`, `measurements.md`/`measurements.en.md`
등과 동일하게 두 언어 다 작성) - 위 "조사 결과" 섹션의 내용을 출처
각주와 함께 정리하고, `apply_hncs()`의 실제 코드(3단계: exposure_gamma
LUT → CLAHE → film_curve LUT)와 실제 HNCS 구조(4단계: 조명별 매트릭스
→ 조명별 chroma LUT → film curve, WB 재실행)를 표로 나란히 대비한다.
순수 문서 - 코드 없음.

### 실험 모듈: `hybrid_engine/research/hncs_structural.py`

기존 `hybrid_engine/`이 RAW 기반 매트릭스 피팅 인프라
(`decode_raw_native()`, `raw_baseline.fit_color_matrix()`)를 이미
갖고 있어 `brands/*.py`(JPEG 톤커브 근사)보다 이 구조에 잘 맞는다.
새 하위 패키지 `hybrid_engine/research/`(연구용 실험, 아직 Stable
파이프라인에 안 얹는 것들을 담는 새 위치 - 이 스펙에서 처음 만듦)에
배치.

파이프라인(4단계 미러링):

```python
def decode_and_white_balance(raw_path):
    """decode_raw_native()(WB 미적용 카메라 네이티브 RGB)에
    AsShotNeutral로 직접 WB 게인을 곱한다 - decode_raw()는 libraw
    자체 매트릭스까지 같이 적용해버려서 "WB만 적용, 매트릭스는 아직"
    상태를 못 만든다. HNCS 2단계(조명별 매트릭스)가 이 상태의 데이터에
    대고 동작하므로 이 함수의 출력이 그 입력에 해당."""
    native_rgb = decode_raw_native(raw_path)
    as_shot_neutral = read_as_shot_neutral(raw_path)  # 기존 함수, exif.py
    return native_rgb / np.array(as_shot_neutral)


def classify_illuminant_cluster(as_shot_neutral):
    """AsShotNeutral의 R/B 비율(as_shot_neutral[0] / as_shot_neutral[2])로
    2-클러스터 분류: 0.46 미만이면 "daylight", 이상이면 "warm".
    임계값 0.46은 설계 단계 실측에서 확인한 두 클러스터
    (0.34~0.45 vs 0.48~0.57) 사이의 중간값."""
    r_over_b = as_shot_neutral[0] / as_shot_neutral[2]
    return "daylight" if r_over_b < 0.46 else "warm"


def apply_chroma_lut(img_rgb, sat_mult, hue_shift_deg):
    """조명 클러스터별 hue/채도 보정 - 그리드서치로 피팅한
    (sat_mult, hue_shift_deg) 2개 파라미터만 씀(표본이 작아 저차원
    유지). HSV로 변환해 S 채널에 sat_mult, H 채널에 hue_shift_deg
    가산."""
    ...


def apply_hncs_structural(raw_path, illuminant_matrices, chroma_lut_params,
                           toe_lift, shoulder_start, white_point):
    """4단계 파이프라인: WB적용 네이티브 RGB -> 클러스터별 3x3 매트릭스
    -> 클러스터별 chroma LUT -> 공유 필름커브. illuminant_matrices/
    chroma_lut_params는 {"daylight": ..., "warm": ...} 형태의 피팅
    결과를 받는다(피팅 자체는 별도 캘리브레이션 스크립트)."""
    ...
```

**클러스터별 매트릭스 피팅**: 기존 `fit_color_matrix(sources, targets)`를
그대로 재사용 - `sources`=`decode_and_white_balance()` 출력(클러스터에
속한 raw들만), `targets`=대응 JPEG의 linear RGB. 클러스터당 3~7장뿐이라
정규화(`ridge=` 인자, 이미 `fit_color_matrix()`가 지원) 필요 - 표본
대비 3×3(자유도 9)이 과적합 위험이 크므로 ridge 정규화를 기본으로
켠다.

**chroma LUT 피팅**: 새로 만들어야 하는 부분. 클러스터별로
(`sat_mult`, `hue_shift_deg`) 2개 파라미터만 그리드서치 - 매트릭스
적용 후 이미지의 population 채도/hue 통계(기존 `core/hue_core.py`나
`datasets/hasselblad/color_signature.json` 계산에 쓴 방식 재사용)를
목표 JPEG의 실측 채도/hue에 맞춘다. 저차원으로 제한하는 이유:
클러스터당 3~7장으로 그 이상의 파라미터(예: hue-conditional 배열)를
피팅하면 이 프로젝트가 반복적으로 경고해온 과적합(예: EVALUATION.md의
3D residual LUT in-sample +11.1%/CV -5.7% 사례)과 같은 함정에 빠진다.

**공유 필름커브**: 클러스터로 나누지 않고 전체 13~15장으로 공유
피팅(기존 `film_curve()`/`core/curve.py` 재사용) - 톤(밝기 분포)은
조명보다 노출/장면에 더 좌우된다고 보고, 표본을 쪼개지 않는 쪽을
택함(v11에서 이미 밝힌 것처럼 toe_lift/shoulder_start는 표본이 작아
바꾸지 않은 전례와 같은 판단).

### 평가

`tools/evaluate_hncs_structural.py`(가칭, 기존
`tools/analyze_camera_native_matrix.py`류의 "1회성 실험 스크립트는
`tools/`에 둔다"는 전례를 따름 - `hybrid_engine/evaluation/`은
재사용 가능한 평가 프로토콜/메트릭용이라 이 1회성 실험과는 결이
다름) - leave-one-out
교차검증: 15장 중 1장을 held-out으로 빼고 나머지로 클러스터별
매트릭스+chroma LUT+공유 필름커브를 피팅, held-out 이미지에 적용해
ΔE(CIEDE2000, 기존 프로젝트 관례대로)를 측정, 15번 반복해 평균.
같은 15장에 대해 기존 `apply_hncs()`(공식 사이트에서 그대로 적용,
raw 없이 jpeg 대비)의 ΔE도 같이 재는 게 아니라, **공정 비교를 위해
`apply_hncs()`도 raw 입력 기준으로 같은 15장에 대해 ΔE를 잰다**
(현재 v8~v12 이력의 RMSE 23.3은 다른 표본/다른 측정 방식일 수 있어
그대로 갖다 쓰지 않고 이 실험 안에서 재측정).

결과는 승패 관계없이 `hybrid_engine/EVALUATION.md`에 새 섹션으로
기록(이 프로젝트의 기존 "이기든 지든 정직하게 기록" 관례).

## 한계 (문서화 대상: 리서치 문서, 모듈 docstring, EVALUATION.md)

- **Phocus의 실제 매트릭스/LUT 값과 다르다** - 우리가 가진 15장짜리
  raw+jpeg 페어로 새로 피팅한 근사치. Hasselblad의 비공개 자산을
  재현한 게 아니다.
- **조사 출처가 비공식이다** - 공식 화이트페이퍼 없음, tonalphoto.com은
  저자 본인이 "개인적 조사, 공식 지원 아님"이라고 명시한 블로그.
  "최소 4개 조명" 숫자는 그 안에서도 재차 커뮤니티(Luminous
  Landscape) 출처로 표시됨 - 확실성 등급이 다른 정보가 섞여 있다는
  점을 리서치 문서에 명시.
- **2-클러스터는 실제 구조(4개 이상)의 축소판** - 표본 부족으로
  인한 타협이지 "2개가 맞다"는 주장이 아니다.
- **표본 15장으로 클러스터당 3~7장** - 통계적으로 매우 얇음. 교차검증
  결과가 양수든 음수든 "표본이 늘어나면 재확인 필요"라는 단서를
  반드시 붙인다.
- **`apply_hncs()`를 대체하지 않는다** - 이 실험이 이겨도 이 스펙
  범위에서는 Stable로 승격하지 않는다(별도 논의).
