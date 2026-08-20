# 색수차 보정(chromatic_aberration) 실험 (설계)

## 배경

이번 세션에서 핫셀블라드 색재현 개선을 위해 20여 회의 후속 실측이
쌓였는데(`hybrid_engine/EVALUATION.md`), 전부 **디코드 이후 단계**
(그레이월드 화이트밸런스 추정, 톤커브, hue/chroma LUT, 공간 연산)만
건드렸다. `decode_raw()`가 rawpy 기본값 그대로 쓰는 **디코드 단계
자체**는 한 번도 튜닝 대상이 아니었다.

rawpy(`raw.postprocess()`)는 `chromatic_aberration=(red_scale,
blue_scale)` 파라미터를 지원한다(기본값 `(1, 1)` = 보정 없음) - R/B
채널을 스케일링해서 렌즈의 횡색수차(lateral CA)를 보정하는 기능. 렌즈
주변부의 색 프린징은 컬러차트 패치의 ΔE를 계통적으로 끌어올릴 수 있는데,
지금까지의 모든 실험은 이 단계를 그대로 두고 그 위 단계만 조정해왔다.
이번 실험은 **정말 다른 각도**(디코드 단계)에서 개선 여지가 있는지
확인한다.

FBDD 노이즈 감소, 하이라이트 복구 모드도 후보로 검토했으나 범위에서
제외했다: 노이즈 감소는 노이즈를 줄일 뿐 계통 색오차와 메커니즘적
연관이 약하고, 하이라이트 복구는 극단적으로 밝은(클리핑되는) 패치에만
관여해 이 population의 표준 조리개/노출 컬러차트 촬영에는 해당 사항이
거의 없다. YAGNI 원칙상 색수차 하나로 스코프를 좁힌다.

## 조사한 것

- `rawpy.Params.__init__`의 실제 시그니처(로컬 확인):
  `chromatic_aberration: Optional[Tuple[float, float]] = None`, docstring:
  "pair (red_scale, blue_scale), default is (1,1), corrects chromatic
  aberration by scaling the red and blue channels".
- `hybrid_engine/utils/io.py`의 현재 `decode_raw(raw_path,
  demosaic_algorithm=None)` (Fuji 데모자이크 실험 때 추가된 옵션 인자
  패턴 그대로 재사용 가능):
  ```python
  def decode_raw(raw_path, demosaic_algorithm=None):
      kwargs = dict(
          use_camera_wb=True, no_auto_bright=True, output_bps=16,
          output_color=rawpy.ColorSpace.sRGB, gamma=(1, 1),
      )
      if demosaic_algorithm is not None:
          kwargs["demosaic_algorithm"] = demosaic_algorithm
      with rawpy.imread(raw_path) as raw:
          rgb16 = raw.postprocess(**kwargs)
      return rgb16.astype(np.float64) / 65535.0
  ```
- 핫셀블라드 raw+jpeg 13쌍은 이미 로컬에 있다
  (`datasets/hasselblad/hasselblad_raw_jpeg_pairs.csv` + gitignore된
  `raw_calib_cache/`, `{jpeg_basename}.{ext}` RAW + `{jpeg_basename}.target.jpg`
  타깃 패턴) - `tools/evaluate_hncs_structural.py`가 이미 이 페어를
  로드하는 코드(`_pair_names()`/`_raw_path_for()`/`_target_path_for()`)를
  갖고 있어 그대로 재사용한다.
- ΔE 측정은 이 프로젝트 표준: `hybrid_engine.utils.evaluate.mean_delta_e`
  (CIEDE2000, `colour.delta_E(method="CIE 2000")`).
- LOO 교차검증 + 통계 검정(`summarize()`/`_sign_test_p()`) 패턴은
  `tools/evaluate_hncs_structural.py`에 이미 구현돼 있고
  `tools/evaluate_darktable_vs_rawpy.py`에도 그대로 복제된 전례가 있다 -
  이번에도 같은 패턴을 재사용한다(부호검정은 `math.comb` 기반 정확
  이항검정, scipy 의존 없음).

## 표본 크기에 대한 솔직한 전제

n=13은 이번 세션에서 이미 여러 번 확인됐듯 paired t-test/부호검정
어느 쪽도 강한 신호가 나오기 쉽지 않은 규모다. 이 실험도 "색수차
보정이 확실히 이긴다"를 증명하는 게 목적이 아니라, **디코드 단계에서
건드릴 여지가 있는지 없는지를 정직하게 확인**하는 예비 점검이다.
결과가 애매하면(신뢰구간이 0을 포함하면) "판정 보류"로 기록한다 -
HNCS 구조 실험과 동일한 태도.

## 설계

### 1. `hybrid_engine/utils/io.py`: `decode_raw()`에 옵션 파라미터 추가

```python
def decode_raw(raw_path, demosaic_algorithm=None, chromatic_aberration=None):
    """... (기존 docstring 유지, chromatic_aberration 설명 한 줄 추가)
    chromatic_aberration: None(기본값)이면 기존과 100% 동일 동작.
    (red_scale, blue_scale) 튜플을 넘기면 raw.postprocess()에 그대로
    전달 - R/B 채널 스케일링으로 렌즈 색수차를 보정한다(tools/
    evaluate_chromatic_aberration.py 참고)."""
    kwargs = dict(
        use_camera_wb=True,
        no_auto_bright=True,
        output_bps=16,
        output_color=rawpy.ColorSpace.sRGB,
        gamma=(1, 1),
    )
    if demosaic_algorithm is not None:
        kwargs["demosaic_algorithm"] = demosaic_algorithm
    if chromatic_aberration is not None:
        kwargs["chromatic_aberration"] = chromatic_aberration
    with rawpy.imread(raw_path) as raw:
        rgb16 = raw.postprocess(**kwargs)
    return rgb16.astype(np.float64) / 65535.0
```

기존 호출부는 전부 `decode_raw(path)` 또는 `decode_raw(path,
demosaic_algorithm=...)`처럼 위치 인자 + 기존 키워드만 쓰므로 새 키워드
인자 추가로 영향 없음 - 회귀 테스트(전체 스위트 재실행)로 확인.

`decode_raw_native()`는 DCP 프로필용 별도 경로(WB/매트릭스까지 우회)라
이 실험과 무관, 변경하지 않는다.

### 2. `tools/evaluate_chromatic_aberration.py` (신규)

```
python3 -m tools.evaluate_chromatic_aberration
```

- 핫셀블라드 13쌍 로드(`tools/evaluate_hncs_structural.py`의
  `_pair_names()`/`_raw_path_for()`/`_target_path_for()`와 동일한 CSV +
  캐시 경로 패턴을 이 스크립트 안에 자체 구현 - 모듈 간 import로 얽지
  않고 독립 스크립트로 유지, 기존 연구 스크립트들의 관례).
- 그리드: `red_scale`, `blue_scale` 각각
  `[0.98, 0.985, 0.99, 0.995, 1.0, 1.005, 1.01, 1.015, 1.02]`(9개 값,
  0.005 간격) - `itertools.product`로 9x9=81 조합.
- **Leave-one-out 교차검증**: 13개 fold. 각 fold에서 나머지 12쌍에 대해
  81개 조합 전부 시도, 12쌍 평균 ΔE(CIEDE2000)가 최소인 조합을 선택 →
  held-out 1쌍에 그 조합을 적용해 검증 ΔE 측정. 베이스라인은 같은
  held-out 쌍에 `decode_raw(raw_path)`(보정 없음, 기본값) 적용 ΔE.
  `evaluate_hncs_structural.py`의 `run_loocv()`와 동일 구조.
- 디코드가 느리고(RAW 파일당) 그리드서치가 페어당 81회 반복되므로
  `DOWNSAMPLE_MAX_DIM = 512`로 축소본 캐시(`_resize_max_dim()`,
  `evaluate_hncs_structural.py`/`evaluate_darktable_vs_rawpy.py`와 동일
  패턴) - 색수차 보정은 전역 채널 스케일링이라 다운샘플이 평가 결과를
  실질적으로 왜곡하지 않는다.
- `summarize()`/`_sign_test_p()`/`print_summary()`를
  `evaluate_hncs_structural.py`와 동일한 시그니처로 이 스크립트 안에
  구현(순수 함수, 폴드 결과 리스트만 받음) - 평균 ΔE, 승패, 부호검정
  p값, 대응표본 t-검정, 부트스트랩 95% CI, drop-one 민감도까지 전부
  포함해 "평균 차이 하나로 승부 판정 안 함" 원칙을 지킨다.
- 폴드별 (name, ΔE 보정없음, ΔE 최적보정, 선택된 (red_scale,
  blue_scale)) 출력.

### 3. 결과 기록

`hybrid_engine/EVALUATION.md`에 새 섹션 "색수차 보정(chromatic
aberration) 실험" 추가 - 이기든 지든 애매하든 정직하게(이 프로젝트
관례):
- 13쌍 전체 페어별 표(보정없음 ΔE, LOO 최적보정 ΔE, 선택된 스케일)
- `summarize()`가 낸 통계 전부(평균/부호검정 p/t-검정/부트스트랩
  CI/drop-one)
- 판정: CI가 0을 포함하면 "판정 보류", 아니면 방향과 크기를 명시해
  결론.

### 4. 건드리지 않는 것

- `apply_hncs()`(`brands/hasselblad.py`) - 이번 실험과 무관, 규칙상 항상
  보호.
- `hasselblad.json`/`.dcp` 캘리브레이션 아티팩트 - 연구 스크립트가
  건드리지 않는다(이 프로젝트 표준 규칙).
- `decode_raw_native()` - 위에서 설명한 이유로 범위 밖.

## 테스트 계획

- `decode_raw(path)`(인자 없이 호출)와 `decode_raw(path,
  demosaic_algorithm=...)`(Fuji 실험의 기존 호출)가 새 키워드 인자
  추가 이후에도 이전과 동일하게 동작하는지 - 전체 테스트 스위트
  재실행으로 회귀 확인.
- `decode_raw(path, chromatic_aberration=(1.01, 0.99))`가 정상적으로
  유효한 범위의 이미지를 반환하는지 확인하는 단위 테스트 - 실제 RAW
  캐시 의존적이라 이 프로젝트 관례대로(Fuji/darktable 실험과 동일)
  커밋되는 자동화 테스트 없이 수동 실행으로 검증.
- `evaluate_chromatic_aberration.py`의 `_sign_test_p()`/`summarize()`는
  순수 함수이므로 `tools/evaluate_hncs_structural.py`/
  `tools/evaluate_darktable_vs_rawpy.py`와 동일하게 하드코딩된 값으로
  단위 테스트 가능(실제 13쌍 LOO 실행 결과를 기록한 뒤 회귀 테스트로
  고정 - `tests/test_evaluate_darktable_vs_rawpy.py`의
  `TestSummarizeRecordedRun` 패턴).
- CSV/캐시 경로 파싱 로직은 순수 단위 테스트, 실제 13쌍 LOO 실행(81
  조합 x 13 폴드 x 12쌍 = 수천 회 ΔE 계산, 느림)은 수동 실행 + 보고서에
  verbatim 결과 기록.

## 다음 단계(이 스펙 밖)

- 색수차 보정이 방향적으로 유의미하면: `apply_hncs()` 자체를 바꾸는 게
  아니라(규칙상 보호 대상), `decode_raw()`를 쓰는 population-fit
  캘리브레이션 파이프라인(예: `hybrid_engine/calibrate_profile.py`)에
  이 보정을 기본값으로 넣을지 별도로 논의.
- FBDD 노이즈 감소, 하이라이트 복구 모드는 이번엔 범위 밖으로 뺐지만
  색수차가 유의미하면 같은 패턴으로 후속 실험 가능.
