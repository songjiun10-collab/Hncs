# 평가 도구 공통 헬퍼 리팩토링 사양

## 목표

세 평가 도구에 반복된 기여 데이터셋 수집 및 sRGB/DeltaE 변환 로직을 하나의
도구 전용 모듈로 모아, CSV 핸들 누수와 구현 드리프트를 줄인다.

## 범위

- 대상 모듈:
  - `tools/evaluate_expanded_clahe_shoulder_refit.py`
  - `tools/measure_all_brand_baselines.py`
  - `tools/fit_population_body_de00_grid.py`
- 신규 모듈: `tools/evaluation_common.py`
- 신규 테스트: `tests/test_evaluation_common.py`
- 도구 인벤토리: `docs/project_structure.md`, `docs/project_structure.en.md`
- `brands/*` shipped 함수, profile asset, 데이터셋 파일, CLI 인자와 출력 형식은
  변경하지 않는다.

## 공통 인터페이스

`tools.evaluation_common`은 다음 함수를 제공한다.

```python
collect_contributed_pairs(
    brand: str,
    model_filter: str | None = None,
    film_mode_filter: str | None = None,
) -> list[dict[str, str]]
load_target_linear(jpg_path: str, shape_hw: tuple[int, int]) -> np.ndarray
bgr_u8_to_linear(bgr_u8: np.ndarray) -> np.ndarray
mean_delta_e(linear_a: np.ndarray, linear_b: np.ndarray) -> float
```

`collect_contributed_pairs`의 반환 dict 키는 기존과 동일하게 `name`,
`raw_path`, `jpeg_path`다. 세트 이름 정렬, `filename_raw` 첫 등장 우선 중복 제거,
`utf-8-sig` manifest 인코딩, 선택적 camera/EXIF FilmMode 필터, 파일 존재 필터를
그대로 유지한다. Manifest 파일은 context manager로 연다.

`load_target_linear`, `bgr_u8_to_linear`, `mean_delta_e`는 현재 세 모듈의
구현을 그대로 옮긴다. 즉 OpenCV BGR uint8 입력을 RGB sRGB linear로 바꾸고,
`colour`/`skimage` 경로로 CIEDE2000 평균을 계산한다. 기존 `hybrid_engine.utils`
구현으로 교체하지 않아 재실행 수치가 달라지지 않게 한다.

## 검증 기준

- 신규 테스트가 manifest BOM/정렬/중복 제거/모델 필터/FilmMode 필터와 색 변환
  shape 및 동일 이미지의 DeltaE 0을 검증한다.
- 세 대상 모듈이 공통 모듈을 import하고 로컬 중복 정의를 갖지 않는다.
- `python3 -m unittest discover -s tests` 전체 통과.
- `python3 -m tools.audit_repo_integrity` exit 0 with no unlisted-file warnings.
- `git diff --check` 통과.
