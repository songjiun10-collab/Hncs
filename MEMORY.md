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
- `python3 -m unittest discover -s tests` → 534 tests, ~35s, all green.
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

## Open threads

- None tracked here as blocking; check `.superpowers/sdd/progress.md`
  for any in-flight subagent-driven-development plan before assuming a
  clean slate.
