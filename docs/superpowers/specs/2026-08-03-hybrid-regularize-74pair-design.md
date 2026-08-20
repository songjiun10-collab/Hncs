# v11↔v12 하이브리드(regularize) 74쌍 재실행 + 유의성 검정 (설계)

## 배경

`tools/calibrate.py`의 `regularize` 모드(`run_regularize()`)는 이미
v11(파라메트릭)↔v12(학습 LUT) **하이브리드 메커니즘 그 자체**다:

```python
lut = (sums + lam * prior) / (counts + lam)
```

`prior`가 v11 파라메트릭 커브, `sums/counts`가 페어 픽셀에서 뽑은
경험적(v12류) 커브. `lam=0`이면 순수 v12, `lam=1e9`면 사실상 순수 v11,
중간값이 실제 혼합이다. 그런데 이 실험은 여전히 **공식 10~13쌍(전량
X1D 계열)으로만** 돌아간다 - `_collect_pair_pixels()`가
`collect_pairs()`(공식, 원격)만 쓰고 `local-mixed-2026-07`(61쌍, 4세대)을
안 쓴다. 원래 결과(lambda=0이 LOO RMSE 14.6으로 최적, `brands/hasselblad_learned.py`
docstring)는 X1D 10장짜리 표본에서 나온 것이고, 그 표본으로 학습한 v12가
74쌍(4세대) 재검증에서는 오히려 v11에 뒤졌다(RMSE 22.20 vs 19.94,
`docs/measurements.md` "로컬 기여 데이터셋으로 세대 간 pooling 첫 실측"
절). 즉 "하이브리드가 유리한 지점"이 표본이 늘면서 이동했을 가능성이
있고, 이번 요청은 그걸 74쌍으로 다시 확인하는 것이다.

또한 기존 `run_regularize()`는 각 lambda의 LOO RMSE 점추정만 찍고
유의성 검정이 없다 - "does X beat Y"에는 CI가 0을 걸치는지 봐야 한다는
루트 CLAUDE.md 원칙을 아직 적용받지 않은 코드다. 이번 재실행에서 같이
붙인다.

## 조사한 것 (실측)

- `_collect_pair_pixels()`는 현재 `collect_pairs()`만 순회하고
  `raw_url`에서 캐시 경로를 재구성한다. `run_learn_curve()`는 이미
  `_resolve_pairs()`(공식 다운로드 + `collect_local_pairs()` 병합,
  통일된 `filename/raw_path/jpeg_path` 포맷)를 쓴다 - `_collect_pair_pixels()`도
  이걸로 바꾸면 74쌍이 된다. 별도 병합 로직 재발명 불필요.
- 현재 알고리즘은 매 lambda x 매 폴드마다 훈련 페어(최대 73쌍)의
  픽셀을 `np.concatenate` + `np.bincount`로 다시 계산한다 - 74쌍
  규모에서 이건 9 lambda x 74 폴드 = 666회, 매번 최대 ~90M 픽셀
  재처리라 실측은 안 했지만 다른 3개 evaluate 스크립트가 74쌍에서
  전부 시간당 병렬화가 필요했던 것에 비춰보면 부담이 크다.
  **LOO는 뺄셈으로 대체 가능하다**: `_build_lut`가 쓰는
  `counts/sums`는 페어별로 독립적으로 계산 가능한 `bincount` 결과이므로
  - 페어별 `(counts_i, sums_i)`를 한 번씩만 계산(전체 74쌍, O(총 픽셀수))
  - 전체 합 `(counts_all, sums_all)`을 한 번 구함
  - 폴드마다 `train = all - counts_i`(O(256), 사실상 공짜)
  로 바꾸면 병렬화 없이도 전체 스윕이 수 초~수 분에 끝난다. 정확히
  같은 결과를 내면서(뺄셈이 재계산과 수학적으로 동일) 워커 로직 자체가
  필요 없어진다 - 이번 작업에서 가장 중요한 설계 결정.
- 세대 라벨: 공식 13쌍은 전부 `"공식 샘플(X1D 계열)"` 한 버킷(기존
  `docs/measurements.md` 컨벤션과 동일 - 공식 출처는 세대 안 나눔).
  로컬 61쌍은 manifest.csv `camera` 컬럼을 그대로 매핑: `"CFV 100C/907X"`,
  `"X2D 100C"`는 그대로, `"Hasselblad X1D II 50C"` -> `"X1D II 50C"`,
  `"Hasselblad X1D"` -> `"X1D"`. `collect_local_pairs()`가 지금
  `camera` 필드를 버리고 있어서 반환 dict에 추가해야 한다.
- 페어드 유의성 검정용 폴드별 스칼라: 기존 `e = (w995 오차)^2 [+ b2 오차)^2]`
  (그림자 무효 페어는 b2 제외)를 그대로 쓰되, 폴드별로는 `sqrt(e)`를
  비교 스칼라로 쓴다(제곱합 대신 폴드별 크기 - 이 프로젝트가 다른
  실험에서 ΔE를 폴드별 스칼라로 쓰는 것과 같은 역할, RMSE 자체는
  집계 후에만 sqrt하므로 폴드별로는 근사).
- 통계 함수(부호검정 `math.comb` 기반, 부트스트랩 95% CI 20000회
  고정시드, drop-one)는 `tools/evaluate_hncs_blend.py`에 이미 있는
  코드를 그대로 복사한다(`tools/CLAUDE.md`: "Standalone. Never import
  from a sibling evaluate_*.py — copy the loader instead", 같은 원칙을
  calibrate.py에도 적용).

## 설계

### 1. `tools/calibrate.py` 변경

- `collect_local_pairs()`: 반환 dict에 `camera=row["camera"]` 필드
  추가(기존 소비자 `_resolve_pairs()`/`run_learn_curve()`는 새 필드를
  무시하므로 영향 없음).
- `_collect_pair_pixels()`: `collect_pairs()` 직접 순회 대신
  `_resolve_pairs()` 사용. 공식 페어는 `generation="공식 샘플(X1D 계열)"`
  고정, 로컬 페어는 위 매핑 테이블로 `camera` -> `generation` 변환해
  `dataset`의 각 entry에 `generation` 키 추가.
- 페어별 `(counts, sums)` 사전계산 함수 추가:
  ```python
  def _pair_counts_sums(neutral_l, target_l):
      counts = np.bincount(neutral_l, minlength=256).astype(np.float64)
      sums = np.bincount(neutral_l, weights=target_l.astype(np.float64), minlength=256)
      return counts, sums
  ```
- `run_regularize()`를 뺄셈 기반 LOO로 재작성:
  - 전체 74쌍에 대해 `_pair_counts_sums`를 한 번씩 계산해 리스트로 보관.
  - `counts_all = sum(counts_i)`, `sums_all = sum(sums_i)`.
  - lambda별로, 폴드(held-out pair)별로 `train_counts = counts_all - counts_i`,
    `train_sums = sums_all - sums_i`로 `_build_lut(train_counts, train_sums, prior, lam)`
    (기존 `_build_lut`은 `neutral_l/target_l` 원본 배열을 받는데, 이제
    이미 집계된 `counts/sums`를 받도록 시그니처 변경 - 내부 bincount
    두 줄만 제거하면 됨, 로직 동일).
  - 폴드별 `sqrt(e)`를 `(lambda, fold_name, generation, sqrt_e)`로 수집.
  - 기존처럼 lambda별 RMSE 출력 + 최적 lambda 선정은 유지.
- 유의성 검정 추가: 최적 lambda vs `lambda=0`(순수 v12), 최적 lambda vs
  `lambda=1e9`(순수 v11) 각각 폴드별 `sqrt(e)` 페어드 비교(부호검정+
  부트스트랩 95% CI+drop-one) - `tools/evaluate_hncs_blend.py`의
  `_sign_test_p`/`summarize`/`print_summary` 패턴을 복사해 이식(ΔE
  대신 `sqrt_e`를 그 자리에 넣는 정도의 변경).
- 세대별 RMSE 분해 표 출력: 최적 lambda LUT으로 전체 74쌍 예측한 뒤
  `generation`별로 그룹핑해 RMSE 계산(v11/v12/하이브리드 3열, 기존
  `docs/measurements.md` 표에 하이브리드 열만 추가하는 형태).
- 최종 `regularized_tone_lut.npy` 저장은 유지(74쌍 전체로 최적 lambda
  재학습).

### 2. 테스트 (`tests/test_calibrate.py`, 신규 - 지금 이 파일 없음)

- `_build_lut`(counts/sums 시그니처로 변경 후): 알려진 작은 합성
  counts/sums로 lambda=0(순수 경험적 평균)과 lambda=1e9(prior에
  수렴)의 경계 동작 확인.
- `_pair_counts_sums`: 알려진 작은 neutral_l/target_l 배열에 대해
  bincount 결과가 손으로 계산한 값과 일치하는지.
- 뺄셈 LOO가 재계산 LOO와 동일한 결과를 내는지: 합성 데이터(페어 3~4개,
  각 몇십 픽셀)로 "전체 재계산 방식"과 "뺄셈 방식" 두 경로를 직접 돌려
  bit-level로 일치하는지 확인(이번 리팩토링의 핵심 불변조건).
- 복사해온 `_sign_test_p`/`summarize`: 기존 `evaluate_hncs_blend.py`
  테스트와 동일한 하드코딩 케이스로 회귀 테스트.
- `collect_local_pairs()`의 `camera` 필드 통과 확인(기존 파일 존재
  체크 로직은 안 건드림).

### 3. 결과 기록

- `brands/hasselblad_learned.py` docstring: 기존 "실험 기록 (음성
  결과): ... lambda=0이 LOO RMSE 14.6으로 제일 좋고..." 문단 뒤에
  **날짜 붙여 추가**(덮어쓰지 않음) - 74쌍 재실행 결과, 최적 lambda,
  유의성 검정 결과, 판정.
- `docs/measurements.md` "로컬 기여 데이터셋으로 세대 간 pooling 첫
  실측" 절의 기존 표(파라메트릭/학습LUT 2열) 아래에 **하이브리드
  세대별 RMSE 표**를 별도로 추가(기존 표는 손 안 댐 - 새 표만 추가).
- `docs/measurements.en.md`(짝 파일, "First real cross-generation
  pooling test via a local contributed dataset" 절 확인됨)에도 대응
  영문 문단 추가 - `docs/CLAUDE.md`: 이중 언어 필수.

### 4. 건드리지 않는 것

- `apply_hncs()`(`brands/hasselblad.py`) - 항상 보호. 이 실험은 순수
  연구/재검증이고, `regularized_tone_lut.npy` 채택 여부는 별도 결정.
- `hasselblad.json`/`.dcp`.
- `run_grid_search()`/`run_learn_curve()` - 손 안 댐(단
  `collect_local_pairs()`에 필드 추가는 이 둘의 소비 방식과 호환).
- `regularized_tone_lut.npy`는 `.gitignore`에 이미 등록된 미채택
  로컬 산출물(배포 아티팩트 아님) - 재실행이 항상 덮어쓰는 기존 동작
  그대로 유지.

## 다음 단계 (이 스펙 밖)

- 하이브리드가 v11/v12 둘 다 유의미하게 이기면: `apply_hncs()` 기본값
  교체는 별도 논의(루트 CLAUDE.md: 배포용 파라미터 변경은 신중하게).
- 세대별로 각각 회귀시킨 LUT(전역 하나가 아니라)은 표본이 세대당
  30장 안팎이라 이 스펙 밖(`docs/measurements.md`에 이미 명시된 한계).
