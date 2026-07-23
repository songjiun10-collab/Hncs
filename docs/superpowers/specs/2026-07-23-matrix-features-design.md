# 매트릭스 피팅 확장: root-polynomial feature + 가중 최소자승(WLS)

## 배경 / 문제

`hybrid_engine`의 Hasselblad 캘리브레이션은 v1.3(Gray Edge 색치우침 보정 +
챠트 2장 pooling)까지 ΔE00 9.687 → 8.976(in-sample)/약 8.6~8.9(CV 추정)로
개선했지만, 목표("9→7")에는 아직 못 미친다. `hybrid_engine/EVALUATION.md`에
기록된 후속 실측 1~19를 보면 이미 ~20개의 독립적인 축(톤/hue/2D/3D LUT,
LUT 스태킹, Gray World 변종 4종, 색치우침 알고리즘 4종, 파이프라인 순서
전탐색, 챠트 개수 스윕, RBF 비선형 매칭, 잔차 기반 로컬 RBF, gradient
boosting 회귀, Huber loss 강건 매트릭스)를 시도했고, 대부분 기각됐다.
문서의 결론은 "이 데이터 규모(13~15쌍)에서 유연한/비파라메트릭 모델은
구조적으로 과적합한다 - 지금까지 유일하게 성공한 두 축(raw_baseline 3x3
매트릭스, Gray Edge)은 자유도가 매우 낮다(각각 9개, 사실상 알고리즘
선택)"는 것이다.

이 스펙은 그 교훈을 지키면서 **자유도를 통제된 방식으로만 늘리는** 두 개의
새 축을 시도한다 - 아직 시도되지 않은 조합이다.

## 목표

1. `hybrid_engine/core/raw_baseline.py`의 `fit_color_matrix()`를 확장해서
   (a) root-polynomial feature와 (b) 가중 최소자승(WLS)을 지원한다.
2. `calibrate_profile.py`에 새 모드를 추가해서 기존 관례(그리드서치 →
   교차검증 → 5% 배포 기준)대로 두 축을 독립적으로, 그리고 신호가 있으면
   함께 검증한다.
3. 결과(성공이든 실패든)를 `EVALUATION.md`에 "후속 실측 20"으로 문서화한다.
4. 교차검증 기준 5% 이상 개선이 확인될 때만 `hasselblad.json`을 갱신한다.

## 범위 밖

- 새 raw+jpeg 페어 데이터 확보(issue #4) - 이 스펙은 기존 15쌍(X1D 13 +
  챠트 2장)으로만 작업한다.
- LUT 계열, RBF, gradient boosting 등 이미 기각된 축 재시도.
- `brands/*.py`의 population-fit 엔진(hybrid_engine과 무관한 별도 모듈) 변경.

## 설계

### 1. Root-polynomial feature

현재 `fit_color_matrix(sources, targets)`는 선형 RGB 3항(r, g, b)만으로
`Y ≈ X @ M` 최소자승을 푼다(자유도 9 = 3x3 행렬).

Finlayson et al. 2015의 root-polynomial 방식을 따라 6항 feature로 확장한다:

```
features(r, g, b) = [r, g, b, sqrt(r*g), sqrt(r*b), sqrt(g*b)]
```

일반 2차 다항식(r², g², rg 등)이 아니라 **제곱근 교차항**을 쓰는 이유는
전역 노출(밝기) 스케일에 대한 불변성 때문이다 - 사진 전체 밝기가 k배
바뀌면 선형항은 k배, 제곱근 교차항도 k배로 같이 스케일되어 매트릭스가
그대로 유효하다(반면 r² 같은 순수 제곱항은 k²배로 스케일되어 불변성이
깨진다). 이 프로젝트는 이미 페어별 평균 밝기가 0.034~0.44로 13배 넘게
벌어지는 상황에서 노출 정규화 버그를 겪은 적이 있어(후속 실측 6),
노출 불변 feature가 특히 중요하다.

이 확장으로 행렬은 (6, 3) 형태(자유도 18)가 된다 - 기존 9개보다는 늘지만
지금까지 기각된 2D/3D LUT(81~729개 격자점)에 비하면 여전히 훨씬 저차원.

**정규화**: 자유도가 늘어난 만큼 ridge 정규화를 필수로 추가한다:

```
minimize ||W^0.5 (Y - X @ M)||^2 + lambda * ||M||^2
```

`lambda`는 하드코딩하지 않고 아래 그리드서치 대상에 포함한다(lambda=0 포함 -
정규화가 실제로 필요한지 자체도 실측으로 확인).

### 2. 가중 최소자승(WLS) - 두 가중치 스킴

`fit_color_matrix()`에 `weights` 인자를 추가해서 픽셀별 가중치를 받는다.
두 가지 방식을 구현하고 실측으로 비교한다 (사용자 지시: "둘 다 구현해서
비교해보고 싶다"):

**(a) 밀도 기반 재가중치**: pooled 데이터셋 전체(현재 15쌍) 기준으로 소스
linear RGB 공간에 성긴 3D 히스토그램(16³ bin)을 만들고,
`weight = 1/sqrt(count_in_bin)`으로 과대표집된 색 영역을 다운웨이트한다.
이건 EVALUATION.md가 이미 명시적으로 지적한 두 문제(챠트 버스트 9장이
사실상 9배 가중치로 작용해서 매트릭스를 챠트 쪽으로 과도하게 끌어당김 -
후속 실측 16; 그레이 월드의 전역 스칼라 하나로는 야경 하늘처럼 압도적으로
큰 균일 영역을 못 당해냄 - 후속 실측 10/11/13)을 직접 겨냥한다. 후속
실측 19에서 기각된 Huber loss(잔차 크기 기반 다운웨이트)와는 다른 축 -
밀도 재가중치는 잔차와 무관하게 **픽셀 발생 빈도**만 본다.

**(b) 채도(chroma) 기반 재가중치**: `weight = chroma^p`, chroma는 소스
linear RGB에서 `max(r,g,b) - min(r,g,b)`로 근사(무채색 근처 픽셀은
색 매칭 정보가 거의 없다는 직관 - 어차피 회색은 어느 매트릭스를 곱해도
그레이축 근처에 남는다). `p`도 그리드서치 대상(0 포함 - p=0이면 균등
가중치와 동일해서 자연스러운 기준선 역할).

### 3. 평가 프로토콜

`calibrate_profile.py`에 새 모드 `matrix_features`를 추가한다. 기존
`run_raw_baseline_mode`/`run_color_cast_algorithm_mode`와 같은 패턴을
따른다:

1. **입력 고정**: 현재 v1.3 기준 그대로(`color_cast_algorithm=gray_edge`,
   15쌍 = X1D 13 + 챠트 2장)로 Phase 0을 거친 뒤의 linear RGB를 소스로
   쓴다 - Phase 0 자체는 이 실험의 변수가 아니다.
2. **1단계 (스크리닝, 4-fold CV)**: 아래 조합을 전수 그리드서치.
   - `feature_set ∈ {linear, root_polynomial}`
   - `weight_scheme ∈ {none, density, chroma}` (chroma는 p ∈ {0.5, 1, 2}도 스윕)
   - `ridge ∈ {0, 1e-4, 1e-3, 1e-2, 1e-1}` (root_polynomial일 때만 의미 있지만
     linear에도 동일하게 적용해서 공정 비교)
3. **2단계 (확정, 13-fold LOO)**: 1단계 스크리닝에서 4-fold CV 기준
   기준선(현재 v1.3 매트릭스 방식) 대비 개선을 보인 상위 후보만 13-fold
   leave-one-out으로 재검증 - 과거 후속 실측 17→18과 동일하게 "스크리닝은
   빠르게, 확정은 엄격하게"를 따른다.
4. **결합 시도**: root-polynomial과 WLS 각각이 2단계에서 독립적으로 신호를
   보이면(기준선 대비 명확한 양의 방향), Gray Edge+챠트pooling 선례(후속
   실측 18 - 개별 효과의 합보다 큰 시너지)를 따라 **처음부터 같이
   재학습**해서 조합 효과를 확인한다. 어느 한쪽만 신호가 있으면 결합
   시도는 생략.
5. **배포 기준**: 프로젝트 관례 그대로 - 13-fold LOO 교차검증 기준 5%
   이상 개선일 때만 `hasselblad.json`을 갱신한다(`recalibrate.py --write`
   경로 재사용).

### 4. 하위 호환성

`fit_color_matrix()`의 새 인자(`feature_fn`, `weights`, `ridge`)는 전부
기본값(`feature_fn=None` → 기존 선형 3항, `weights=None` → 균등 가중치,
`ridge=0.0`)을 가져서, 기존 호출부(`pipeline/engine.py`의 Phase 0 등)는
코드 변경 없이 기존과 동일하게 동작한다.

### 5. 문서화

결과는 성공/실패 관계없이 `hybrid_engine/EVALUATION.md`에 "후속 실측 20"
섹션으로 추가한다 - 그리드서치 전체 표(4-fold), 확정 후보의 13-fold LOO
결과, 결합 시도 결과(있었다면), 배포 여부와 근거를 포함. 채택 시
`hasselblad.json`의 `_comment`와 README.ko.md의 실험 표도 갱신한다.

## 테스트 계획

- `tests/test_raw_baseline.py`에 신규 케이스 추가:
  - `feature_fn` 지정 시 (N, 6) 설계 행렬이 올바르게 만들어지는지
  - root-polynomial feature의 노출 불변성(같은 이미지를 k배 스케일해도
    피팅된 매트릭스가 동일한 예측을 내는지) 회귀 테스트
  - `weights` 지정 시 WLS가 numpy 표준 결과(예: `np.linalg.lstsq`를
    가중치로 직접 검증 가능한 소규모 합성 케이스)와 일치하는지
  - `ridge > 0`일 때 행렬 노름이 `ridge=0`보다 작아지는지(정규화 효과
    최소 확인)
  - 기존 `fit_color_matrix(sources, targets)` 호출(인자 생략)이 기존과
    동일한 결과를 내는지(하위 호환 회귀 테스트)
- `calibrate_profile.py --mode matrix_features`는 기존 모드들처럼 실제
  `raw_calib_cache/` 데이터로 수동 실행해서 결과를 확인(자동화된 unit
  test 범위 밖 - 이 프로젝트의 다른 calibrate 모드들과 동일한 관례).

## 실패 시나리오

이미 20개 가까운 축이 기각된 프로젝트라, 이번 시도도 5% 기준을 못 넘길
가능성이 낮지 않다. 그 경우에도:
- `EVALUATION.md`에 실측 결과를 그대로 기록한다(삭제 안 함).
- `hasselblad.json`은 갱신하지 않는다.
- `fit_color_matrix()`의 확장 자체(feature_fn/weights/ridge 인자)는
  코드에 남겨둔다 - 향후 issue #4의 새 데이터가 들어왔을 때 재시도할
  수 있는 도구로 남기는 것이 이 프로젝트의 문서화 철학과 일치한다.
