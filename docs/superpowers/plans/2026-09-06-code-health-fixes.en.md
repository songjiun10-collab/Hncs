# Code Health Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task.

**Goal:** Restore a green, reproducible test and CLI baseline for the reported
color-science, chart-detection, research-tool, and resource-management defects.

**Architecture:** Keep shipped look functions unchanged. Centralize compatibility
at existing utility boundaries, convert BGR uint8 research inputs to linear RGB
before ΔE calculations, and fail early with clear messages when required raw
pairs are absent.

**Tech stack:** Python 3.11/3.12, unittest, OpenCV contrib, colour-science,
NumPy.

**Spec:** User request “다 고쳐” following the repository code evaluation findings.

## Global constraints

- Do not modify protected shipped `apply_*` behavior or profile assets.
- Every production fix gets a regression test first and is verified with the full unittest suite.
- Preserve existing research outputs and document platform-only golden-hash behavior.

### Task 1: Colour/OpenCV compatibility

**Files:**

- Modify: `hybrid_engine/utils/evaluate.py`
- Modify: `hybrid_engine/core/chart_baseline.py`
- Test: `tests/test_hybrid_engine.py`, `tests/test_chart_baseline.py`

- [x] Add tests proving weighted CIEDE2000 works when the installed colour-science lacks the private intermediate helper, and chart detection does not call unavailable OpenCV methods.
- [x] Implement a public-API CIEDE2000 fallback and conditional MCC24 setup compatible with OpenCV 4.x/5.x.
- [x] Run the focused tests, then the full suite.

### Task 2: Correct research-tool color domain

**Files:**

- Modify: `tools/fuji/evaluate_fuji_classic_negative_v2_grid.py`
- Modify: `tools/fuji/diagnose_fuji_autobright_vs_look.py`
- Test: `tests/test_fuji_classic_negative_recalibration.py`

- [x] Add a regression test that the ΔE helper receives linear RGB and BGR uint8 targets are converted before comparison.
- [x] Add one shared conversion helper in the evaluation utility and use it at all affected call sites.
- [x] Run focused tests and inspect that no reported metric path uses raw BGR bytes.

### Task 3: Empty dataset and file-handle safety

**Files:**

- Modify: `tools/fuji/evaluate_fuji_classic_negative_v2_grid.py`
- Modify: `tools/fuji/diagnose_fuji_autobright_vs_look.py`
- Modify: `tools/fuji/diagnose_fuji_neutral_render_offset.py`
- Modify: `tools/fuji/probe_fuji_classic_negative_v2_boundary.py`
- Modify: `tools/maintenance/audit_repo_integrity.py`
- Test: `tests/test_fuji_classic_negative_recalibration.py`, relevant tool tests

- [x] Add tests for zero usable pairs producing a clear, non-zero failure instead of NaN/TypeError.
- [x] Add early validation and context-managed CSV/JSON reads.
- [x] Run focused tests and the full suite.

### Task 4: Cross-platform golden verification

**Files:**

- Modify: `tests/test_population_fit_look_golden.py`
- Test: existing golden test module

- [x] Add a platform-tolerant assertion for known OpenCV HSV round-trip functions using a bounded pixel-difference check while retaining exact hashes for stable functions.
- [x] Run the golden tests on the current environment and the full suite.

### Task 5: Final verification

- [x] Run `.venv/bin/python -m unittest discover -s tests` (928 tests, OK).
- [x] Run CLI import/help smoke tests and report remaining dependency-only skips or failures.
- [x] Review the diff for protected-file violations and summarize exact test counts; the integrity audit exits 0 and no protected files changed.
