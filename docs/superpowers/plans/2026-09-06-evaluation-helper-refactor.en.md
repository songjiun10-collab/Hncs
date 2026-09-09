# Evaluation Helper Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract duplicated contributed-pair and color-error helpers from three
evaluation tools without changing their CLI behavior or research numbers.

**Architecture:** Add one tool-layer module, `tools/fit/evaluation_common.py`,
that owns manifest traversal and the exact existing conversion/DeltaE
implementations. The three callers import these functions and retain their
existing orchestration, constants, and output paths.

**Tech stack:** Python 3, `csv`, OpenCV, NumPy, `colour-science`, scikit-image,
`unittest`.

**Spec:** `docs/superpowers/specs/2026-09-06-evaluation-helper-refactor.md`

## Global constraints

- Do not modify any shipped `brands/*` apply function or `hybrid_engine/assets/profiles/*` asset.
- Preserve existing function outputs, manifest ordering/deduplication, filters, CLI arguments, report paths, and numeric implementations.
- Open manifest CSV files with context managers.
- Verify with the full test suite, repository audit, and `git diff --check`.

### Task 1: Extract common evaluation helpers

**Files:**

- Create: `tools/fit/evaluation_common.py`
- Modify: `tools/fit/evaluate_expanded_clahe_shoulder_refit.py`
- Modify: `tools/fit/measure_all_brand_baselines.py`
- Modify: `tools/fit/fit_population_body_de00_grid.py`
- Modify: `docs/project_structure.md`
- Modify: `docs/project_structure.en.md`
- Test: `tests/test_evaluation_common.py`

**Interfaces:**

- `tools.fit.evaluation_common.collect_contributed_pairs(brand, model_filter=None, film_mode_filter=None)` returns the existing `name/raw_path/jpeg_path` dictionaries.
- `tools.fit.evaluation_common.load_target_linear(jpg_path, shape_hw)` returns resized sRGB-linear float64 RGB.
- `tools.fit.evaluation_common.bgr_u8_to_linear(bgr_u8)` returns sRGB-linear float64 RGB.
- `tools.fit.evaluation_common.mean_delta_e(linear_a, linear_b)` returns the existing scalar CIEDE2000 mean.

- [ ] **Step 1: Write regression tests for the shared helpers**

  Create a temporary `datasets/<brand>/contributed`-shaped tree and patch the
  module `BASE` so the test can assert BOM decoding, sorted set traversal,
  duplicate raw-file first-wins behavior, camera filtering, and EXIF filter
  forwarding. Also assert conversion shapes, linear output dtype, and zero
  DeltaE for identical arrays.

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `./.venv/bin/python -m unittest tests.test_evaluation_common`

  Expected: FAIL because `tools.fit.evaluation_common` does not yet exist.

- [ ] **Step 3: Implement `tools/fit/evaluation_common.py`**

  Move the exact implementations currently duplicated in the three target
  modules. Keep `collect_contributed_pairs`'s set-name sort, `filename_raw`
  deduplication, existence checks, optional camera filter, and optional
  `_exif_film_mode` filter. Use `with open(manifest, encoding="utf-8-sig",
  newline="")` around `csv.DictReader`. Keep the existing OpenCV/colour/
  scikit-image math unchanged.

- [ ] **Step 4: Replace caller-local definitions with imports**

  Import the four helpers from `tools.fit.evaluation_common` in each target
  module, delete only duplicate definitions and imports made unused by that
  deletion, and leave all callers and call signatures unchanged.

- [ ] **Step 5: Run focused tests and all affected module tests**

  Run: `./.venv/bin/python -m unittest tests.test_evaluation_common`

  Expected: PASS.

  Run: `./.venv/bin/python -m unittest discover -s tests`

  Expected: all tests PASS with no new warnings.

- [ ] **Step 6: Verify repository integrity and diff hygiene**

  Run: `./.venv/bin/python -m tools.maintenance.audit_repo_integrity` (exit 0
  with no unlisted-file warnings) and `git diff --check` (no output).

- [ ] **Step 7: Commit the bounded refactor**

  ```bash
  git add tools/fit/evaluation_common.py tools/fit/evaluate_expanded_clahe_shoulder_refit.py tools/fit/measure_all_brand_baselines.py tools/fit/fit_population_body_de00_grid.py tests/test_evaluation_common.py docs/project_structure.md docs/project_structure.en.md docs/superpowers/specs/2026-09-06-evaluation-helper-refactor.md docs/superpowers/plans/2026-09-06-evaluation-helper-refactor.md
  git commit -m "refactor: share evaluation tool helpers"
  ```
