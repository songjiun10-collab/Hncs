# MEMORY.md

Living state snapshot, not instructions — see `CLAUDE.md` for rules. This
file answers "where does the project actually stand right now," so a new
session doesn't have to re-derive it from git log or ask. Append dated
entries below; don't rewrite old ones.

## Snapshot (2026-08-03, branch `claude/unknown-character-0x48vp`)

- 12 shipped brands (`brands/*.py`, excluding `__init__.py` and the
  `hasselblad_day`/`hasselblad_night`/`hasselblad_learned` legacy/
  experimental variants): Hasselblad, Canon, Fujifilm, Leica, Nikon,
  Olympus, Panasonic, Pentax, Phase One, Ricoh GR, Sigma, Sony.
- `python3 -m unittest discover -s tests` → 615 tests. 8 currently error
  in this container on `ModuleNotFoundError: torch` (upscale) and
  missing GUI deps (`gui/` tabs) — not a code regression, just packages
  this container never installed. Everything else green.
- Other sessions landed a lot on this branch concurrently while this one
  was running: a `gui/` desktop wrapper (PyQt, tabs for brand-look
  preview/hybrid convert/lens correction/RAW-Log/upscale), AI
  super-resolution (`core/upscale.py`, Real-ESRGAN via PyTorch or ONNX),
  SD-card deleted-photo recovery (`core/sdcard_undelete.py` +
  `core/sdcard_carve.py`, `tools/recover_sdcard.py`), PQ/HLG HDR output
  alongside the Log pipeline, White Patch/Shades-of-Gray AWB modes in
  `raw_pipeline`, and a v11 hybrid-engine recalibration on 65 pairs. None
  of this was reviewed by this session — treat `docs/project_structure.md`
  as the source of truth for what each new file does, not this bullet.
- `apply_hncs()` (Hasselblad) is the only calibration-fit brand; the
  other 11 population-fit brands are docstring-measured from
  imaging-resource.com galleries.
- Sigma (12th brand) is fully shipped: 5 bodies (Bayer fp/fp L + Foveon
  sd Quattro/dp2 Quattro/SD1 Merrill), n=83, `datasets/sigma/` pixel
  signatures present, in `tools/classify_brand.py`'s 10-brand LOO
  discriminability check.
- `apply_acros`/`apply_monochrome` (Fuji) are the only `apply_*`
  functions that return 2D single-channel output, not 3-channel BGR —
  see `brands/CLAUDE.md`.
- `.claude/skills/run-hncs/` exists and is verified working (driver +
  `env`/`smoke`/`sheet`/`look` subcommands) — the equivalent of a
  screenshot for a project with no GUI/server.
- CLAUDE.md was just restructured: short root file + per-directory
  `CLAUDE.md` in `brands/`, `tools/`, `hybrid_engine/`, `docs/`,
  `tests/`, `datasets/`.
- The 61-pair personal-library dataset (not dpreview — that source was a
  dead end, blocked by the site) landed as `datasets/hasselblad/
  contributed/local-mixed-2026-07/` (CFV 100C/907X 30, X2D 100C 24, X1D
  II 50C 6, X1D 1). Another session used it to re-run the HNCS
  illuminant-blend experiment at 74 pairs (13 official + 61 contributed):
  `tools/evaluate_hncs_blend.py`, recorded in `hybrid_engine/
  EVALUATION.md`. Result flipped from the 13-pair "inconclusive" verdict
  — both RB and CCT blending now beat hard-cluster classification by
  +1.8%, statistically significant but close to the boundary (RB sign
  test p=0.047, CCT bootstrap CI lower bound +0.017). RB vs. CCT is still
  inconclusive. `apply_hncs()` itself was not touched.

## Snapshot (2026-09-05, branch `develop`)

- `python3 -m unittest discover -s tests` → **855 tests, 0 failures, 0
  errors, 15 skipped** in this container (was 843 with 12 errors). The
  "errors are just packages this container lacks" caveat in the
  2026-08-03 snapshot above is obsolete: every environment-dependent
  test now skips instead of erroring. The 15 skips are 12 needing
  `exiftool` + 3 needing committed `.dcp`/`.icc`/`transicc`. CI installs
  `libimage-exiftool-perl`, so all 12 run there
  (`.github/workflows/tests.yml`).
- `tools/audit_repo_integrity.py` no longer dies on a machine without
  `exiftool` — it skips only that check and says so on the last line, so
  "이상 없음" never over-claims the verified scope. It also gained a
  pure-Python header check (`dcp_header_problems` /
  `icc_header_problems`) that catches what `exiftool -validate` cannot:
  a DCP with the standard TIFF magic (42) instead of Adobe's `0x4352`
  passes exiftool, and that magic was the real cause of the 2026-08-31
  "Lightroom won't read the profiles" bug. All 65 committed artifacts
  (3 DCP + 62 ICC) pass — a regression guard, not a fix.
- Default branch is `claude/hncs-v13-dpreview-calibration`; `develop` is
  51 commits ahead of it and 113 behind, so the two have long diverged.
  Work landed directly on `develop`.

## Open threads

- `apply_classic_negative` recalibration is **decided by the user, not
  open work**: `hybrid_engine/EVALUATION.md` (2026-09-04) measured that
  4 of its 47 pairs were mis-paired and its mode mean was inflated by
  1.0532 ΔE00. Nothing in `brands/fuji.py` or the profiles was touched.
- Otherwise nothing tracked here as blocking; check
  `.superpowers/sdd/progress.md` for any in-flight
  subagent-driven-development plan before assuming a clean slate.
