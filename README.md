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
    raw+jpeg pair calibration (124 photos, RMSE 15.4)
- Pixel-level **5-part signature analysis** (tone/color/texture/gamut/
  joint distribution) records each brand's color science as data
- **Population-statistics reproducibility audit: 10/10 matched** - every
  committed number reproduces from scratch against the cached images
  (2026-07)
- `unittest` test suite + GitHub Actions CI verifies automatically on
  every push/PR

![Before/After - apply_hncs applied to a sample photo](docs/images/before_after_hncs.jpg)

![HNCS preset demo - all 25 apply_* looks on one photo](docs/images/preset_demo.jpg)

*All 24 `apply_*` functions from `brands/*.py` (+ the original) run on the
same source photo (a Nikon D5300 night shot, provided for this demo). Not
an official calibration source photo - just a demo. See the links in the
[Supported Brands](#supported-brands) table for the actual population
evidence behind each brand.*

## Supported Brands

| Brand | Verification method | Details |
|---|---|---|
| ✅ Hasselblad | raw+jpeg pair calibration (grid search + learned LUT) | [docs/measurements.en.md](docs/measurements.en.md) |
| ✅ Fujifilm | 10 film-simulation presets, population + same-scene comparison charts | [docs/brands.en.md](docs/brands.en.md#fujifilm-brandsfujipy) |
| ✅ Leica | population-fit (45 SOOC JPEGs) | [docs/brands.en.md](docs/brands.en.md#leica-brandsleicapy) |
| ✅ Phase One | population-fit (Capture One's default rendering) | [docs/brands.en.md](docs/brands.en.md#phase-one-brandsphaseonepy) |
| ✅ Pentax | population-fit (645Z + K-1, 40 photos) | [docs/brands.en.md](docs/brands.en.md#pentax-brandspentaxpy) |
| ✅ Ricoh GR | population-fit (GR III/IIIx/II) | [docs/brands.en.md](docs/brands.en.md#ricoh-gr-brandsricoh_grpy) |
| ✅ Canon | population-fit (EOS R5/R6/R8/R3/R, n=115) | `brands/canon.py` docstring |
| ✅ Nikon | population-fit (Z6/Z6 II/D780, n=69) | `brands/nikon.py` docstring |
| ✅ Sony | population-fit (A7/A7R/A7S/A7 III/A7 IV, n=115) | `brands/sony.py` docstring |
| ✅ Panasonic | population-fit (GH5/GH6/G9/S5/S1, n=120) | `brands/panasonic.py` docstring |
| ✅ Olympus | population-fit (OM-1/OM-5/E-M1 III/E-M1X/PEN-F, n=122) | `brands/olympus.py` docstring |
| ✅ Sigma | population-fit (Bayer + Foveon, 5 bodies, n=83) | `brands/sigma.py` docstring |

The shared limitations of the population-fit approach (no raw baseline;
some parameters like shoulder_start/clahe_clip are borrowed from
Hasselblad's values and unverified) are documented in detail in
[docs/brands.en.md](docs/brands.en.md) and each `brands/*.py` docstring.

## Quick Example

```python
import cv2
from brands.hasselblad import apply_hncs

img = cv2.imread("photo.jpg")
result = apply_hncs(img)
cv2.imwrite("photo_hncs.jpg", result)
```

Every `apply_*` function in `brands/*.py` uniformly takes a BGR
`np.ndarray` and returns a BGR `np.ndarray`. Run from the repo root so
the `core`/`brands`/`tools` import paths resolve correctly.

## Installation

```
pip install -r requirements.txt
```

`.claude/settings.json` is the sandbox config that auto-allows network access to `cdn.hasselblad.com`, `live.staticflickr.com`, etc. when running analysis scripts in this repo with Claude Code.

## RAW -> Log Colorspace Pipeline (Professional)

A separate module with a different purpose from the per-brand `apply_*` engine. Instead of approximating "the JPEG this specific camera actually produces," it standardizes RAW files - **regardless of camera** - into a common intermediate colorspace (ProPhoto RGB Linear), then encodes into whichever video camera's Log curve/gamut you want (F-Log2, S-Log3, V-Log, ARRI LogC3/4, etc.) so that camera's creative `.cube` LUTs can be applied to RAW photos without color drift ([inspired by raw-alchemy](https://github.com/shenmintao/raw-alchemy), reimplemented here on top of `colour-science`).

```
python3 -m tools.raw_pipeline photo.CR3 photo.tiff --log-space S-Log3
python3 -m tools.raw_pipeline photo.ARW photo.tiff --log-space V-Log --lut looks/my_look.cube
python3 -m tools.raw_pipeline photo.NEF photo.tiff --log-space F-Log2 --exposure 1.0
```

![RAW -> Log colorspace demo - sRGB decode vs V-Log encoding](docs/images/raw_pipeline_demo.jpg)

*The same RAW (Fujifilm X-T1) decoded to standard sRGB (left) vs encoded with
`tools.raw_pipeline --log-space V-Log` (right). The flat, low-contrast/
low-saturation look on the right is expected - it's the ungraded Log state
as-is.*

Supported Log spaces: see `LOG_SPACES` in `core/log_pipeline.py` (F-Log/F-Log2/V-Log/N-Log/Canon Log 2·3/S-Log3/S-Log3.Cine/Arri LogC3·4/Log3G10/D-Log). The curve-gamut pairings use `colour-science`'s own definitions as-is - they haven't been cross-checked exhaustively against each manufacturer's official spec, the same kind of "unverified" caveat as the rest of this project's flagged items.

## Lens distortion correction

A purely geometric tool, independent of the color-rendering engines above - undoes barrel/pincushion distortion using the camera+lens profile database bundled with [lensfun](https://lensfun.github.io/) (via `lensfunpy`, 948 cameras / 1304 lenses, no extra system package needed beyond `pip install -r requirements.txt`). Reads Make/Model/LensModel/FocalLength/FNumber from EXIF (`exiftool`) and looks up the matching profile automatically; accepts both RAW and already-rendered JPEG/TIFF/PNG input.

```
python3 -m tools.lens_correction photo.RAF corrected.jpg
python3 -m tools.lens_correction photo.jpg corrected.jpg --lens "XF10-24mmF4 R OIS" --focal-length 10 --aperture 8
```

If the camera or lens isn't in the database, or the matched lens profile has no distortion calibration data, the tool fails loudly (`camera_not_found` / `lens_not_found` / `no_distortion_data`) instead of silently passing the image through uncorrected - see `core/lens_correction.py`'s `correct_from_exif()`. Vignetting and chromatic-aberration correction are out of scope for now (only `ModifyFlags.DISTORTION` is applied).

## hybrid_engine/ - EXIF-driven cross-camera color conversion (V0.1)

`hybrid_engine/` at the repo root is a third, independent module with yet another purpose: "re-render a finished JPEG shot on camera A as if camera B had shot it." There are two entry points - one for RAW input (`HybridCameraEngine`: Phase 0 color unification + Gray World normalization + LAB tone/saturation curves) and one for JPEG-only input (`preset_inverse`: detects the source brand from EXIF, inverts that brand's population-fit tone curve from `brands/*.py`, then re-applies the real target brand's existing `apply_*` function).

```
# JPEG only - auto-detects the source camera from EXIF
python3 -m hybrid_engine.convert photo.jpg out.jpg --target hasselblad

# RAW available - full pipeline (matrix + WB unification + Gray World +
# tone/color curves), also auto-detects the camera from EXIF and picks the
# matching profile; --profile only needed to override that
python3 -m hybrid_engine.main photo.3FR out.jpg
python3 -m hybrid_engine.main photo.3FR out.tiff --profile hasselblad  # 16-bit for further editing
```

![hybrid_engine demo - Nikon JPEG converted to a Hasselblad look](docs/images/hybrid_engine_demo.jpg)

*A Nikon D5300 JPEG of the Budapest Parliament at night (left, provided for
this demo - the same source photo as `docs/images/preset_demo.jpg`/
`before_after_hncs.jpg`) converted with `hybrid_engine.convert --target
hasselblad` (right) - EXIF auto-detects Nikon, inverts its tone curve back
toward a neutral baseline, then re-applies `apply_hncs`.*

![hybrid_engine demo, 4 more photos - cathedral interior/flag/street](docs/images/hybrid_engine_demo_more.jpg)

*Four more photos from the same trip (all provided for this demo) - the two
cathedral-interior shots had no EXIF at all (likely stripped in transit
through a messaging app), so `--source nikon` was passed explicitly; all
four were shot in portrait and needed `PIL.ImageOps.exif_transpose()` to
fix orientation before conversion.*

**Known limitations** (also documented in each module's docstring):
- `core/color_matrix.py`: even with camera-specific color-matrix normalization, sensor spectral sensitivities are never exactly proportional to the CIE standard observer (metamerism), so a physically perfect camera-agnostic colorspace isn't possible - the residual can only be reduced via the ΔE loop, not eliminated
- `core/preset_inverse.py`: only the L-channel tone curve of population-fit brands can be inverted (it has a closed-form inverse) - CLAHE (perceptual contrast compensation) is an adaptive operation and isn't inverted, and brands without a raw+jpeg pair (e.g. Fuji) simply aren't this kind of curve to begin with, so they're out of scope by design
- `calibrate_profile.py` runs the CIEDE2000 ΔE loop against the 13 real Hasselblad raw+jpeg pairs. Every experiment below is judged by cross-validated ΔE, not in-sample - several looked good in-sample and then failed (or reversed sign) once properly validated, which is itself a recurring finding worth reading the table with in mind. `recalibrate.py` wraps the actual "matrix + retrain, nested CV, only update if the cross-validated ΔE genuinely improves" procedure used to ship v1.2 into one command (`python3 -m hybrid_engine.recalibrate --write`, dry-run by default, `--cache-dir` to point at a different raw+jpeg pair directory) - useful once a larger dataset (e.g. issue #4's real-scene X2D pairs) arrives:

  | Experiment | Method | In-sample | Cross-validated | Verdict |
  |---|---|---|---|---|
  | v1.1 baseline | coordinate descent over `tone_core`/`color_core` params | ΔE00 15.01 | - | starting point |
  | Learned tone LUT | 1D LUT, 256 bins, on L | +4.9% | not run (added CV after this) | rejected, below bar |
  | Learned hue LUT (v1.1) | 1D circular LUT, 36 bins | +2.1% | not run | rejected, below bar |
  | 3D residual LUT | joint L/a/b grid, 729 cells | +11.1% | **-5.7%** | rejected, pure overfitting |
  | 2D residual LUT | joint a/b grid, 81 cells | +1.4% | -2.7% | rejected |
  | Spatial/local contrast (v1.1) | unsharp-mask L-channel clarity | +0.0% | +2.0% (noise) | rejected, null result |
  | **Raw-baseline 3x3 matrix (standalone)** | global least-squares color matrix, no color chart (GitHub issue #4) | +42.4% | **+32.6%** | first real win |
  | Matrix wired into the pipeline (1st attempt) | matrix + existing Phase 0/1/2 | - | +0.0% | bug: forced exposure normalization was erasing the matrix's gain |
  | Matrix + retrained tone/color (fixed) | `--mode raw_baseline_pipeline`, nested CV | +34.8% | **+29.7%** | **shipped as v1.2** |
  | Hue LUT retried on v1.2 | same 1D circular LUT, new baseline | +4.6% | +1.4% | rejected, below bar |
  | Spatial retried on v1.2 | same local-contrast stage, new baseline | +0.3% | -1.6% | rejected |
  | Robust (percentile) Gray World | exclude high-saturation pixels from the neutral-cast estimate | +0.0% (best candidate = off) | -3.4% | rejected, targeted night-scene sky over-correction but didn't help |
  | Hue-conditional chroma LUT | 36-bin circular chroma gain, orthogonal to the hue-rotation LUT | **-2.0%** | -4.0% | rejected - first LUT experiment negative even in-sample |
  | Gray World removed entirely | rely only on camera as-shot WB (`unify_to_d65`), no pixel-content neutral-cast estimate | - | **-90.3%** (ΔE00 9.69 → 18.43) | rejected hard - Gray World is load-bearing on all 13 pairs, not just noise |
  | Zoned Gray World (2-5 luma zones) | independent neutral-cast estimate per brightness zone, Gaussian-blended | +0.0% (best = 1 zone) | +0.0%, monotonically worse past 1 zone, all 13 LOO folds picked the baseline | rejected - more degrees of freedom just adds noise at this sample size |
  | Gray World strength (fine-tune) | single blend-strength knob interpolating identity ↔ full correction, fine grid 0.6-1.4 | +0.7% (best=0.95) | **-0.0%** (essentially a wash) | rejected - even the most conservative possible adjustment (1 free parameter) finds no real signal |
  | X2D II chart pairs pooled into calibration | 13 X1D + 2 curated X2D II ColorChecker pairs (9-frame burst deduped to 2, all-9 diluted the gain) | -2.5% | **+3.7%** (true LOO, held-out X1D pair never in training) | first pooling attempt that helped rather than hurt |
  | Gray Edge color-cast algorithm | swap Gray World for spatial-derivative-based neutral-cast estimation (van de Weijer 2007), matrix/tone/color otherwise unchanged | - | **+2.1%** | adopted (White Patch was -18.5%, Shades of Gray a weak +1.9%) |
  | **Gray Edge + chart pooling, retrained together** | matrix + tone/color refit from scratch with `color_cast_algorithm=gray_edge` and 15 pairs | +9.9% | **+11.1%** | **shipped as v1.3** - first result to clear the 5% bar since v1.2 |

  The shipped v1.3 profile refits the matrix and tone/color curves from 15 pairs (13 X1D + 2 curated X2D II ColorChecker pairs) with Gray Edge instead of Gray World for Phase 0's color-cast correction - `hybrid_engine/EVALUATION.md` follow-up 17/18 has the full comparison table and the reasoning for why the combination beats either change alone. A non-linear RBF color-matching prototype (`scipy.interpolate.RBFInterpolator`, inspired by [ethan-ou/camera-match](https://github.com/ethan-ou/camera-match)) and a pixel-level gradient-boosting regressor were also tried as full matrix replacements - both showed the same failure pattern (big gains on already-hard scenes, but net losses on already-easy ones) and neither cleared the bar, so neither is in the shipped pipeline.

  The shipped v1.2 profile (superseded by v1.3 above) measured ΔE00 15.01 → **9.82** on the official evaluation harness (-34.6%, a CIE 2000 tier upgrade from "completely different colors" to "different at a glance"). Full methodology, the failed-then-diagnosed-then-fixed integration story, and remaining limitations (midtone residual, hue barely moved) are in `hybrid_engine/EVALUATION.md`; the rejected LUT experiments have their own detailed writeup in `hybrid_engine/assets/luts/README.md`. Pixel-level diagnosis (`EVALUATION.md` follow-up 10) pinned the worst remaining failure mode to a specific mechanism: Gray World's single global scale factor can't satisfy a night scene's sky and street-light-dominated foreground at the same time - four different fixes for that (above), spanning from "more degrees of freedom" to "fewer," were all tried and rejected on cross-validation, so it stays a documented, unresolved limitation rather than a shipped workaround.

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
- [x] 10 Fujifilm film-simulation presets
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
brands/       Per-brand color-approximation functions (apply_*)
core/         Tone-curve/LUT/stats/validation helpers shared across all brands
datasets/     Committed reference CSVs (official sample metadata, scraped gallery links)
tools/        Analysis (analyze) / download / calibration scripts
models/       Pretrained models used for e.g. face detection
docs/         Detailed docs (methodology / measurements / per-brand notes / file map)
```

See [docs/project_structure.en.md](docs/project_structure.en.md) for a
full file-by-file breakdown.

## Tests

There's an `unittest`-based test suite under `tests/` (no pytest or other external dependency added, keeping `requirements.txt`'s minimal-dependency principle). Covers `core/curve.py` (tone-curve math, boundary conditions/monotonicity/continuity) / `core/stats.py` (population statistics computation) / `core/validation.py` (integrity validation, reproducing the CDN corruption pattern) / `core/engine.py` (the population-fit engine) / `brands/*.py` (shape/dtype preservation for every `apply_*` look function, Fuji preset count consistency) / `tools/fuji_chart_calibrate.py` (crop-box extraction, delta aggregation) / `tools/download.py` (imaging-resource.com HTML parsing, filtering, Google Drive URL classification - network calls are mocked) / all of `datasets/*/texture_signature.json` (whether sharpening/micro_contrast/noise fall within a sane cross-brand range - a regression guard against a Sony-scale-bug-style order-of-magnitude error) / `core/lut.py` / `core/denoise.py` / `tools/iso_noise.py` (including a regression test for the patch-grid off-by-one bug) / `core/log_pipeline.py` (exposure adjustment, Log encoding, `.cube` LUT application, every supported `LOG_SPACES` entry) / `hybrid_engine/` (normalization/tone/color/color-matrix/pipeline/ΔE evaluation/EXIF brand detection and preset inversion, end to end - 32 tests). `.github/workflows/tests.yml` runs this suite automatically on every push/PR.

```
python3 -m unittest discover -s tests -v
```

## Reproducing/re-verifying the measurements

```
python3 -m tools.analyze hasselblad       # Full population statistics over Hasselblad's official samples
python3 -m tools.analyze portrait         # Portrait subset + skin-tone hue-invariance verification
python3 -m tools.analyze leica            # Leica imaging-resource.com population
python3 -m tools.analyze phaseone         # Phase One, same
python3 -m tools.analyze pentax           # Pentax, same
python3 -m tools.analyze ricoh_gr         # Ricoh GR, same
python3 -m tools.analyze fuji_film_modes  # Population per Fuji Film Mode + preset-direction verification

python3 -m tools.download fuji-links      # Collect Fuji RAW/JPEG Google Drive links
python3 -m tools.download fuji-pairs      # Download RAW+JPEG pairs from those links (requires gdown)

python3 -m tools.calibrate grid_search    # True before/after grid search from Hasselblad raw (requires rawpy, large downloads)
python3 -m tools.calibrate learn_curve    # Learn a tone curve directly from raw+jpeg pixel correspondence (requires rawpy)
python3 -m tools.calibrate regularize     # Regularize the learned LUT + leave-one-out cross-validation
```

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

## License

[MIT](LICENSE)
