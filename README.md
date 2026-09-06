# HNCS

*[한국어 README](README.ko.md)*

[![tests](https://github.com/songjiun10-collab/Hncs/actions/workflows/tests.yml/badge.svg)](https://github.com/songjiun10-collab/Hncs/actions/workflows/tests.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A project that measures official (or near-official) sample images from camera/digital-back manufacturers and approximates each brand's color science as code. It originally covered only Hasselblad's HNCS (Hasselblad Natural Colour Solution), and the same methodology has since been extended to 11 more brands.

## TL;DR

- **12 brands**: Hasselblad/Fujifilm/Leica/Phase One/Pentax/Ricoh GR/
  Canon/Nikon/Sony/Panasonic/Olympus/Sigma
- Every brand is grounded in **measurements from official sample images**
  - 834 photos total across the 10 population-fit brands, plus Hasselblad's
    raw+jpeg pair calibration (74 pairs across 4 camera generations as of
    2026-08, parametric RMSE 19.94 - see [docs/measurements.en.md](docs/measurements.en.md#first-real-cross-generation-pooling-test-via-a-local-contributed-dataset-2026-08-local-mixed-2026-07))
- Pixel-level **5-part signature analysis** (tone/color/texture/gamut/
  joint distribution) records each brand's color science as data
- **Population-statistics reproducibility audit: 10/10 matched** - every
  committed number reproduces from scratch against the cached images
  (2026-07)
- `unittest` test suite + GitHub Actions CI verifies automatically on
  every push/PR

## Where to start reading

New here? Read in this order: this README, then
[docs/project_structure.en.md](docs/project_structure.en.md) for the
file-level map, then whichever area's own `README.md` (usage/examples)
and `CLAUDE.md` (contribution rules) you're about to touch -
[brands/README.md](brands/README.md), [tools/README.md](tools/README.md),
[hybrid_engine/README.md](hybrid_engine/README.md),
[gui/README.md](gui/README.md), [tests/README.md](tests/README.md).
[docs/START_HERE.en.md](docs/START_HERE.en.md) has the full directory map
plus a "want to do X → read Y" table.

![Before/After - apply_hncs applied to a sample photo](docs/images/before_after_hncs.jpg)

*`apply_hncs` (the Hasselblad look) applied to a Seoul street-crossing
snapshot shot on a Fuji GFX50S II - `DSCF9447.RAF`, from the same
raw+jpeg library used for this session's Classic Chrome/Nostalgic Neg
calibration. The person in frame is seen from behind/the side only, not
identifiable.*

![HNCS preset demo - 44 apply_* looks + original on one photo](docs/images/preset_demo.jpg)

*All 44 photo-mode `apply_*` looks from `brands/*.py` (+ the original) run
on the same source photo (a street snapshot from Itaewon, Seoul, shot on a
Fuji GFX50S II - `DSCF9556.RAF`, from the same raw+jpeg library used for
this session's Classic Chrome/Nostalgic Neg calibration, not a close-up of
any specific person). Built with `tools/build_readme_demo.py`, which
re-runs automatically as new looks ship.*

## Supported Brands

**12 brands**: Hasselblad, Fujifilm, Leica, Phase One, Pentax, Ricoh GR,
Canon, Nikon, Sony, Panasonic, Olympus, Sigma. Full verification-method
table, per-brand evidence links, shared limitations, and a quick-start
code example are in [brands/README.md](brands/README.md).

## Installation

```
pip install -r requirements.txt
```

`.claude/settings.json` is the sandbox config that auto-allows network access to `cdn.hasselblad.com`, `live.staticflickr.com`, etc. when running analysis scripts in this repo with Claude Code.

## Other modules

Three engines live alongside the per-brand `apply_*` functions, each
with its own `README.md`:

- [tools/README.md](tools/README.md) - RAW -> Log colorspace pipeline
  (`raw_pipeline.py`), lens distortion correction, `.cube` LUT export for
  Photoshop/DaVinci, DCP camera profile export (X2D II), brand-signature
  discriminability check, frame-by-frame video engine, and the commands
  to reproduce/re-verify every measurement in this project
- [hybrid_engine/README.md](hybrid_engine/README.md) - EXIF-driven
  cross-camera color conversion (V0.1): re-render a JPEG/RAW shot on
  camera A as if camera B had shot it, plus the full raw-baseline
  calibration experiment history
- [gui/README.md](gui/README.md) - a Tkinter desktop app wrapping all of
  the above into one point-and-click window

[`docs/demo/hncs_convert_demo.html`](docs/demo/hncs_convert_demo.html) is
a separate, standalone browser-only demo page - **its per-brand
parameters are hand-picked for visual effect, not derived from this
repo's measured data**, the page says so at the top. No build step
needed, just open it.

## Goals / Philosophy

- Parameters are grounded in **measured data** - population statistics,
  raw+jpeg pairs, same-scene comparison charts - rather than subjective
  descriptions of "film character"
- Unverified values are never hidden - they're **explicitly labeled
  "unverified"** in code and docs (e.g. several brands' `shoulder_start`/
  `clahe_clip` are documented as borrowed from Hasselblad's values without
  independent verification)
- **Reproducibility**: committed population numbers must reproduce from
  scratch against the cached images, and are periodically audited
- When the sample is small, **conservative choices are preferred over
  overfitting**, even when a grid search finds a lower RMSE - several
  brands document cases where a better-scoring fit was deliberately
  deferred due to insufficient sample size
- Failed attempts (couldn't find a raw pair, sample contamination, sites
  blocking access, etc.) are documented as-is, not erased

## Features

- [x] Hasselblad raw-based parametric/learned calibration (`apply_hncs`,
      `apply_hncs_learned`)
- [x] 13 Fujifilm film-simulation presets
- [x] Population-fit color-approximation engine shared by 10 brands
      (`core/engine.py`)
- [x] Pixel-level 5-part signature analysis (tone/color/texture/gamut/
      joint_distribution)
- [x] Image-integrity validation pipeline (`core/validation.py`,
      automatic CDN-corruption filtering)
- [x] `unittest`-based automated test suite
- [x] GitHub Actions CI (runs automatically on every push/PR)
- [x] Population-statistics reproducibility audit tooling
- [x] RAW -> Log colorspace (F-Log2/S-Log3/V-Log/etc.) + `.cube` LUT
      pipeline (`tools/raw_pipeline.py`, separate from the brand engine)
- [x] EXIF-driven cross-camera color conversion engine V0.1
      (`hybrid_engine/`, supports both RAW and JPEG input, brand tone-curve
      inversion + a ΔE evaluation loop)

## Structure

```
brands/       Per-brand color-approximation functions (apply_*) - README.md, CLAUDE.md
core/         Tone-curve/LUT/stats/validation helpers shared across all brands
datasets/     Committed reference CSVs (official sample metadata, scraped gallery links) - CLAUDE.md
tools/        Analysis/download/calibration scripts, RAW->Log, lens correction, DCP/LUT export - README.md, CLAUDE.md
hybrid_engine/ Cross-camera color conversion + calibration machinery - README.md, CLAUDE.md
gui/          Tkinter desktop app - README.md, CLAUDE.md
tests/        unittest test suite - README.md, CLAUDE.md
models/       Pretrained models used for e.g. face detection
docs/         Detailed docs (methodology / measurements / per-brand notes / file map) - CLAUDE.md
```

Each area's own `README.md` (where present) covers usage/examples;
`CLAUDE.md` covers the rules for changes there. See
[docs/project_structure.en.md](docs/project_structure.en.md) for a full
file-by-file breakdown.

## Further Reading

The README is kept short and skimmable; the detailed measurement history
lives in `docs/`.

- [docs/methodology.en.md](docs/methodology.en.md) - image trustworthiness
  policy, brand-function QA verification, population-statistics
  reproducibility audit
- [docs/measurements.en.md](docs/measurements.en.md) - the full Hasselblad
  measurement history (v8-v12, day/night)
- [docs/brands.en.md](docs/brands.en.md) - detailed methodology for
  Fujifilm/Leica/Phase One/Pentax/Ricoh GR
- [docs/project_structure.en.md](docs/project_structure.en.md) - full
  file-by-file breakdown
- [docs/hncs_structural_research.en.md](docs/hncs_structural_research.en.md) -
  research-only comparison of HNCS's real 4-stage pipeline vs.
  `apply_hncs()`'s 3-stage simplification, with leave-one-out ΔE
  experiments across sample sizes (13 -> 94 -> 364 pairs); the 364-pair
  result is statistically significant and confirms `apply_hncs()`'s
  simplification wins
- [docs/hncs_external_sources_analysis.en.md](docs/hncs_external_sources_analysis.en.md) -
  analysis of 17 external documents (a Hasselblad-adjacent blog + a
  forum thread) about how HNCS actually works, cross-checked against
  this project's structural experiments above

## Contributing

Issues and PRs are welcome. This project holds to a "no parameter change
without measured evidence" principle, so if your PR adjusts a brand's
parameters, please include the population numbers or comparison method
that back the change - it'll make review much faster.

## Acknowledgments

Thanks to GitHub user **kmichels** (Reddit: Big_Rip4015), who read the
project closely enough to file [issue #4](https://github.com/songjiun10-collab/Hncs/issues/4)
with methodology feedback that directly led to real fixes (an edited-photo
filter bug, a properly characterized raw baseline) - and then followed up
by shooting and contributing 10 Hasselblad X2D II 100C ColorChecker
Classic captures, which made the chart-based raw-baseline characterization
in `hybrid_engine/EVALUATION.md` possible. Real external review and real
data, credited where they landed.

Thanks also to Chris Schmauch, who real-user-tested the DCP camera
profile export (`core/dcp_export.py`) in actual Lightroom and traced why
it wasn't loading down to the exact header magic number and
`UniqueCameraModel` value Adobe expects - see [tools/README.md](tools/README.md#dcp-camera-profile-colorimetric-correction-x2d-ii-only).

## License

[MIT](LICENSE)
