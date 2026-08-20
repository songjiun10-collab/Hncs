# HNCS 조명 블렌딩(illuminant blend) 실험 (설계)

## 배경

`hybrid_engine/research/hncs_structural.py`는 HNCS의 실제 4단계 구조
(RAW → 조명별 3x3 매트릭스 → 조명별 chroma LUT → 공유 필름커브)를
미러링하되, "조명 최소 4종" 대신 AsShotNeutral R/B 비율 기반
**2-클러스터 하드 분류**(임계값 0.9)로 단순화했다. 이 하드-클러스터
버전을 13쌍 LOO CV로 apply_hncs()와 비교한 결과는 "판정 보류"였다
(`hybrid_engine/EVALUATION.md` "HNCS 구조 실험" 절 - 평균 4.1% 개선이
n=13 노이즈와 구분 안 됨).

이번 요청은 Luminous Landscape 포럼 스레드("Hasselblad Natural Color
Solution (HNCS) - how it works (probably)", `forum.luminous-landscape.com`,
`blog.tonalphoto.com`의 HNCS 메커니즘 설명 글이 인용한 원출처)에서 얻은
새 정보를 실험으로 검증하는 것이다. 그 스레드가 설명하는 실제 구조:

- 최소 4개 조명(Tungsten ~2950K, Low Tungsten ~2100K, Flash ~5650K,
  Flash-Daylight), 각각 고유 3x3 매트릭스
- 색보정 LUT(chroma correction table)는 Tungsten/Flash 2개에만 존재
- **화이트밸런스 값 기준으로 매트릭스+LUT를 자동 선택하고, 중간값은
  블렌딩한다** - Lightroom의 dual-illuminant DCP와 같은 방식(조명
  개수만 더 많음)

즉 실제 HNCS는 "하드 분류"가 아니라 **연속 블렌딩**이다. 이 스펙은
그 블렌딩 가설이 우리 13쌍 데이터에서 기존 하드-클러스터 방식보다
ΔE를 낮추는지 검증한다.

## 표본 크기와 스코프 판단

13쌍으로 4개 조명을 전부 흉내내는 건 무리다(조명당 표본이 3~4장으로
붕괴). 대신 **조명 "개수"가 아니라 "블렌딩이라는 결합 방식" 자체를
검증**하는 것으로 스코프를 좁힌다: 기존과 같은 2개의 앵커
매트릭스/chroma LUT를 쓰되, 하드 분류 대신 연속 가중치로 블렌딩한다.
이러면 기존 실험과 앵커 개수가 같아서 "블렌딩 자체의 효과"만 격리해서
비교할 수 있고, 아래 가중 최소자승 피팅 방식 덕분에 오히려 기존
하드-클러스터(소수 클러스터가 3쌍뿐)보다 통계적으로 더 안정적이다.

## 조사한 것 (실측)

- 13쌍의 실제 AsShotNeutral R/B 비율(로컬 raw_calib_cache/에서 직접
  읽음): 최솟값 0.3649(`B0001395.jpg`), 최댓값 1.3163
  (`x1d-II-sample-09.jpg`) - 기존 하드-클러스터 임계값 0.9가 이
  범위(0.36~1.32) 중간 어딘가에 있다는 것과 일치.
- `hybrid_engine/core/raw_baseline.py`의 `fit_color_matrix(sources,
  targets, weights=None, ridge=0.0)`가 이미 **페어별 픽셀 가중치**를
  지원한다(각 source와 같은 (H,W) shape의 가중치 배열, 가중 최소자승은
  sqrt(weight)를 X/Y에 곱하는 표준 트릭으로 구현됨) - 새 피팅 함수를
  안 만들어도 그대로 재사용 가능.
- AsShotNeutral → 대략적 CCT 변환이 실제로 동작하는지 로컬에서 4개
  샘플로 확인: `colour.RGB_to_XYZ(as_shot_neutral, sRGB, apply_cctf_decoding=False)`
  → `colour.XYZ_to_xy` → `colour.temperature.xy_to_CCT(xy, method="McCamy 1992")`.
  결과가 물리적으로 말이 됨(R/B 비율이 높을수록(따뜻한 광원 추정)
  CCT가 낮게 나옴 - 예: `B0001395.jpg`(R/B=0.36) → 9376K, `x1d-II-sample-09.jpg`
  (R/B=1.32) → 5807K, 단조 감소 경향 확인).
- `tools/evaluate_hncs_structural.py`의 기존 chroma LUT 그리드
  (`SAT_MULT_GRID = [0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15]`,
  `HUE_SHIFT_GRID = [-6, -4, -2, 0, 2, 4, 6]`)를 그대로 재사용한다 -
  이미 이 데이터로 검증된 그리드 범위.
- 비교 기준점(재실행 불필요, 이미 기록됨): 하드-클러스터 구조 실험의
  LOO ΔE 평균 **10.191**(`hybrid_engine/EVALUATION.md` "HNCS 구조
  실험" 절).

## 설계

### 1. `hybrid_engine/research/hncs_structural.py`에 함수 추가 (기존 함수는 전부 유지)

```python
def compute_blend_weight_rb(as_shot_neutral, rb_min, rb_max):
    """AsShotNeutral의 R/B 비율을 [rb_min, rb_max] 범위 기준으로
    [0, 1]로 정규화한 블렌딩 가중치. 0에 가까울수록 앵커A(저 R/B,
    기존 cluster_a에 해당하는 방향), 1에 가까울수록 앵커B. rb_min/
    rb_max는 13쌍 전체에서 관측된 실제 최솟값/최댓값을 호출부(평가
    스크립트)가 넘긴다 - 하드코딩하지 않는다(관측 범위 밖 값이 오면
    [0,1] 밖으로 나갈 수 있고, 이는 의도된 외삽 허용이다)."""
    r_over_b = as_shot_neutral[0] / as_shot_neutral[2]
    return (r_over_b - rb_min) / (rb_max - rb_min)


def compute_blend_weight_cct(as_shot_neutral, mired_min, mired_max):
    """AsShotNeutral을 대략적 CCT로 변환(camera-native RGB를 sRGB
    선형 RGB로 근사하는 가정 1개 추가 - 실제 카메라 분광감도를 모르니
    엄밀하지 않다, 이 실험 안에서만 쓰는 근사) 후 mired(=1e6/CCT) 공간
    에서 [mired_min, mired_max] 기준 [0, 1]로 정규화. mired 공간에서
    보간하는 건 Adobe DCP의 실제 dual-illuminant 보간 관례와 동일."""
    rgb = np.array(as_shot_neutral[:3], dtype=np.float64)
    xyz = colour.RGB_to_XYZ(rgb, _SRGB, apply_cctf_decoding=False)
    xy = colour.XYZ_to_xy(xyz)
    cct = colour.temperature.xy_to_CCT(xy, method="McCamy 1992")
    mired = 1e6 / cct
    return (mired - mired_min) / (mired_max - mired_min)


def apply_hncs_structural_blend(raw_path, weight, matrix_a, matrix_b,
                                 chroma_lut_a, chroma_lut_b,
                                 toe_lift, shoulder_start, white_point):
    """블렌딩 버전 4단계 파이프라인: WB적용 네이티브 RGB -> 가중
    평균 매트릭스((1-weight)*matrix_a + weight*matrix_b) -> 가중 평균
    chroma LUT 파라미터 -> 공유 필름커브(하드클러스터 버전과 동일하게
    조명 무관 고정). weight는 이미 계산된 스칼라를 받는다(compute_blend_weight_*
    는 평가 스크립트에서 호출) - 이 함수는 블렌딩 로직만 담당."""
    wb_rgb = decode_and_white_balance(raw_path)
    blended_matrix = (1.0 - weight) * matrix_a + weight * matrix_b
    matrixed = apply_color_matrix(wb_rgb, blended_matrix)
    sat_a, hue_a = chroma_lut_a
    sat_b, hue_b = chroma_lut_b
    sat_mult = (1.0 - weight) * sat_a + weight * sat_b
    hue_shift_deg = (1.0 - weight) * hue_a + weight * hue_b
    chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
    return film_curve(chroma_applied, toe_lift=toe_lift,
                       shoulder_start=shoulder_start, white_point=white_point)
```

`hybrid_engine/research/hncs_structural.py` 상단에 `import colour`와
`_SRGB = colour.RGB_COLOURSPACES["sRGB"]` 모듈 상수를 추가한다(다른
연구 스크립트/`hybrid_engine/utils/evaluate.py`와 동일한 패턴).
기존 `classify_illuminant_cluster`/`apply_hncs_structural`은 손대지
않는다 - 새 함수만 추가.

### 2. `tools/evaluate_hncs_blend.py` (신규)

```
python3 -m tools.evaluate_hncs_blend
```

- `tools/evaluate_hncs_structural.py`의 13쌍 로드 패턴(`_pair_names()`/
  `_raw_path_for()`/`_target_path_for()`)과 페어별 디코드+축소 캐시
  패턴(`_pair_data()`, `DOWNSAMPLE_MAX_DIM = 512`)을 그대로 복사해
  재사용 - decode는 페어당 1회만(그리드서치가 캐시된 축소 이미지
  위에서 도니까 색수차 실험과 달리 디코드가 병목이 아니다).
- 13쌍 전체의 R/B 비율 최솟값/최댓값, CCT 기반 mired 최솟값/최댓값을
  먼저 한 번 계산(전체 population 기준 - LOO 매 폴드마다 다시 계산하지
  않는다, 정규화 범위 자체가 폴드별로 흔들리면 폴드 간 비교가 무의미해짐).
- **가중 최소자승 매트릭스 피팅** (두 가중치 방식 각각에 대해):
  ```python
  def fit_weighted_matrices(train_pairs, weight_fn):
      weights_b = [weight_fn(p) for p in train_pairs]  # 각 페어의 스칼라 가중치
      sources = [_pair_data(p)[0] for p in train_pairs]
      targets = [_pair_data(p)[1] for p in train_pairs]
      w_a = [np.full(s.shape[:2], 1.0 - w) for s, w in zip(sources, weights_b)]
      w_b = [np.full(s.shape[:2], w) for s, w in zip(sources, weights_b)]
      matrix_a = fit_color_matrix(sources, targets, weights=w_a, ridge=MATRIX_RIDGE)
      matrix_b = fit_color_matrix(sources, targets, weights=w_b, ridge=MATRIX_RIDGE)
      return matrix_a, matrix_b
  ```
  (`MATRIX_RIDGE = 1.0`, 기존 스크립트와 동일한 값 - 이미 사실상 no-op
  임이 그 스크립트에서 문서화됨, 재현성 위해 그대로 유지.)
- **가중 chroma LUT 그리드서치**: 기존 `SAT_MULT_GRID`/`HUE_SHIFT_GRID`
  (7x7=49 조합)를 훈련 페어에 대해 가중 평균 ΔE 최소화로 탐색 -
  앵커A용은 `(1-weight)` 가중, 앵커B용은 `weight` 가중, 매트릭스는
  이미 그 폴드에서 피팅된 blended matrix(각 페어 자기 가중치로
  블렌딩)를 먼저 적용한 뒤 후보 chroma 파라미터를 얹어 평가한다 -
  `apply_hncs_structural_blend()`가 예측 시 실제로 하는 순서와
  일치시키기 위함.
- **LOO CV**: 13개 폴드. held-out 페어를 훈련에서 완전히 제외(가중치
  0이 아니라 애초에 훈련 집합에서 빠짐 - 기존 하드-클러스터 스크립트와
  동일한 LOO 관례)하고 나머지 12쌍으로 위 가중 피팅, held-out 페어는
  자기 자신의 가중치로 예측해서 ΔE(CIEDE2000, `mean_delta_e`) 측정.
  두 가중치 방식(R/B, CCT) 각각 독립적으로 13폴드 전부 실행.
- `summarize()`/`_sign_test_p()`/`print_summary()`: 이 세션 표준
  패턴(`tools/evaluate_hncs_structural.py`와 동일 시그니처) - 각
  블렌딩 방식의 LOO ΔE를 **기존 하드-클러스터 ΔE(10.191, 상수로
  하드코딩 - 재실행 안 함)**와 폴드별로 비교. 하드-클러스터 쪽 폴드별
  개별값은 `hybrid_engine/EVALUATION.md` "HNCS 구조 실험" 절의 "폴드별
  상세" 표에 이미 13행 전부 기록돼 있으므로 그 값을 그대로 상수로
  가져와 페어드 비교(부호검정/t-검정/부트스트랩 CI/drop-one)에 쓴다.

### 3. 결과 기록

`hybrid_engine/EVALUATION.md`에 새 절 "HNCS 조명 블렌딩 실험" 추가
(이기든 지든 애매하든 정직하게):
- 13쌍 페어별 표: 하드-클러스터 ΔE(기존 기록값) / R-B블렌딩 ΔE /
  CCT블렌딩 ΔE
- 두 블렌딩 방식 각각 하드-클러스터 대비 유의성 검정 전체 출력
- R-B 블렌딩 vs CCT 블렌딩 두 방식끼리도 직접 비교(어느 쪽 가중치
  공식이 더 나은지)
- 판정: 각 비교의 95% CI가 0을 포함하면 "판정 보류"

### 4. 건드리지 않는 것

- `apply_hncs()`(`brands/hasselblad.py`) - 항상 보호.
- `hasselblad.json`/`.dcp` 캘리브레이션 아티팩트.
- `hncs_structural.py`의 기존 `classify_illuminant_cluster`/
  `apply_hncs_structural`/`CLUSTER_THRESHOLD_R_OVER_B` - 하드클러스터
  버전은 그대로 남겨 향후 비교 기준으로 계속 쓴다.

## 테스트 계획

- `compute_blend_weight_rb`/`compute_blend_weight_cct`: 알려진
  AsShotNeutral 입력에 대해 예상 범위([0,1] 안쪽, 경계값 근처 동작)를
  확인하는 단위 테스트.
- `apply_hncs_structural_blend`: `weight=0.0`일 때 `matrix_a`/
  `chroma_lut_a`만 적용한 것과 동일한 출력이 나오는지(블렌딩 공식의
  경계 조건 검증), `weight=1.0`일 때 앵커B와 동일한지 - 모킹된 작은
  배열로 검증.
- `tools/evaluate_hncs_blend.py`의 `summarize()`/`_sign_test_p()`는
  순수 함수이므로 하드코딩된 값으로 단위 테스트(기존 관례와 동일
  패턴).
- CSV/캐시 경로 파싱은 순수 단위 테스트, 실제 13쌍 LOO 실행(2가지
  가중치 방식 x 13폴드 x 12쌍 학습, 이미 디코드된 캐시 위에서 도는
  가중 최소자승+49그리드서치라 디코드-바운드였던 색수차 실험보다
  훨씬 빠를 것으로 예상되나 정확한 소요시간은 미실측 - 수동 실행 +
  보고서에 verbatim 결과 기록, 예상보다 오래 걸리면 백그라운드 실행
  + 모니터링으로 전환(이 세션에서 이미 확립된 패턴)).

## 다음 단계(이 스펙 밖)

- 두 블렌딩 방식 중 하나(또는 둘 다)가 하드-클러스터를 유의미하게
  이기면: `apply_hncs()`에 반영할지는 별도 논의(표본 13개로 배포용
  파라미터를 바꾸는 결정은 신중해야 한다는 이 프로젝트의 반복된
  원칙).
- 조명 4종(2종이 아니라)까지 시도하는 건 표본 부족으로 이 스펙에서
  제외 - 만약 2-앵커 블렌딩이 하드-클러스터를 유의미하게 이기면
  후속으로 검토 가치가 생긴다.
