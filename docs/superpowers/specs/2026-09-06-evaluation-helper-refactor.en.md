# Evaluation Tool Shared Helper Refactor Specification

[한국어](2026-09-06-evaluation-helper-refactor.md)

## Goal

Gather the repeated contributed-dataset collection and sRGB/DeltaE conversion
logic from three evaluation tools into one tool-only module, reducing CSV handle
leaks and implementation drift.

## Scope

- Target modules:
  - `tools/fit/evaluate_expanded_clahe_shoulder_refit.py`
  - `tools/fit/measure_all_brand_baselines.py`
  - `tools/fit/fit_population_body_de00_grid.py`
- New module: `tools/fit/evaluation_common.py`
- New tests: `tests/test_evaluation_common.py`
- Tool inventories: `docs/project_structure.md`, `docs/project_structure.en.md`
- Do not change shipped `brands/*` functions, profile assets, dataset files, CLI
  arguments, or output formats.

## Shared interface

`tools.fit.evaluation_common` provides:

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

The returned dictionaries from `collect_contributed_pairs` keep the existing
keys: `name`, `raw_path`, and `jpeg_path`. Preserve set-name sorting,
first-occurrence deduplication by `filename_raw`, `utf-8-sig` manifest decoding,
optional camera/EXIF FilmMode filters, and file-existence filtering. Open
manifest files with a context manager.

`load_target_linear`, `bgr_u8_to_linear`, and `mean_delta_e` move the current
implementations from the three modules without alteration. They convert OpenCV
BGR uint8 input to RGB sRGB-linear values and compute mean CIEDE2000 through the
existing `colour`/`skimage` path. Do not replace them with the existing
`hybrid_engine.utils` implementation, so rerun numbers remain unchanged.

## Verification criteria

- New tests verify manifest BOM handling, sorting, deduplication, model and
  FilmMode filters, color-conversion shapes, and DeltaE 0 for identical images.
- The three target modules import the shared module and contain no local duplicate definitions.
- `python3 -m unittest discover -s tests` passes in full.
- `python3 -m tools.maintenance.audit_repo_integrity` exits 0 with no unlisted-file warnings.
- `git diff --check` passes.
