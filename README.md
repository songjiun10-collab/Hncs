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

New here? Read in this order: this README's [Supported
Brands](#supported-brands) table for what's shipped, then
[docs/project_structure.en.md](docs/project_structure.en.md) for the
file-level map, then the `CLAUDE.md` in whichever directory you're about
to touch (each area documents its own rules — `brands/`, `core/`,
`tools/`, `hybrid_engine/`, `gui/`, `tests/`, `datasets/`, `docs/`).
[docs/START_HERE.en.md](docs/START_HERE.en.md) has the full directory map
plus a "want to do X → read Y" table.

![Before/After - apply_hncs applied to a sample photo](docs/images/before_after_hncs.jpg)

![HNCS preset demo - 29 apply_* looks + original on one photo](docs/images/preset_demo.jpg)

*All 29 photo-mode `apply_*` looks from `brands/*.py` (+ the original) run
on the same source photo (a Nikon D5300 night shot, provided for this
demo). Not
an official calibration source photo - just a demo. See the links in the
[Supported Brands](#supported-brands) table for the actual population
evidence behind each brand.*

## Supported Brands

| Brand | Verification method | Details |
|---|---|---|
| ✅ Hasselblad | raw+jpeg pair calibration (grid search + learned LUT) | [docs/measurements.en.md](docs/measurements.en.md) |
| ✅ Fujifilm | 15 film-simulation presets, population + same-scene comparison charts + raw+jpeg (Provia/Classic Chrome/Classic Chrome v2/Nostalgic Neg v2/Nostalgic Neg v3) | [docs/brands.en.md](docs/brands.en.md#fujifilm-brandsfujipy) |
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
`np.ndarray` and returns a same-shape `np.ndarray`. The two monochrome
film simulations (`apply_acros`, `apply_monochrome`) return a
single-channel 2D array rather than 3-channel BGR - deliberate, and
covered by `tests/test_brands.py`. Run from the repo root so the
`core`/`brands`/`tools` import paths resolve correctly.

## Installation

```
pip install -r requirements.txt
```

`.claude/settings.json` is the sandbox config that auto-allows network access to `cdn.hasselblad.com`, `live.staticflickr.com`, etc. when running analysis scripts in this repo with Claude Code.

Reproducing `tools/evaluate_darktable_vs_rawpy.py` (a research-only RAW-decoder comparison experiment) requires `darktable-cli` to be installed on the system (`apt-get install darktable` or your distro's equivalent - a separate system package not covered by Python's `requirements.txt`). No other feature in this project requires darktable.

## RAW -> Log Colorspace Pipeline (Professional)

A separate module with a different purpose from the per-brand `apply_*` engine. Instead of approximating "the JPEG this specific camera actually produces," it standardizes RAW files - **regardless of camera** - into a common intermediate colorspace (ProPhoto RGB Linear), then encodes into whichever video camera's Log curve/gamut you want (F-Log2, S-Log3, V-Log, ARRI LogC3/4, etc.) so that camera's creative `.cube` LUTs can be applied to RAW photos without color drift ([inspired by raw-alchemy](https://github.com/shenmintao/raw-alchemy), reimplemented here on top of `colour-science`).

```
python3 -m tools.raw_pipeline photo.CR3 photo.tiff --log-space S-Log3
python3 -m tools.raw_pipeline photo.CR3 photo.exr --log-space S-Log3   # 32-bit float OpenEXR, scene-referred
python3 -m tools.raw_pipeline photo.ARW photo.tiff --log-space V-Log --lut looks/my_look.cube
python3 -m tools.raw_pipeline photo.NEF photo.tiff --log-space F-Log2 --exposure 1.0
python3 -m tools.raw_pipeline photo.CR3 photo.tiff --log-space V-Log --auto-expose-mode highlight_safe
python3 -m tools.raw_pipeline photo.CR3 photo.tiff --log-space V-Log --auto-expose-mode matrix
```

![RAW -> Log colorspace demo - sRGB decode vs V-Log encoding](docs/images/raw_pipeline_demo.jpg)

*The same RAW (Fujifilm X-T1) decoded to standard sRGB (left) vs encoded with
`tools.raw_pipeline --log-space V-Log` (right). The flat, low-contrast/
low-saturation look on the right is expected - it's the ungraded Log state
as-is.*

Output format is chosen by extension - `.tif`/`.tiff` for a 16-bit integer file (broadest viewer compatibility), `.exr` for 32-bit float OpenEXR (the actual industry-standard scene-referred format for Log/grading workflows - DaVinci Resolve, Nuke, etc. read it directly, and float means no clipping headroom is lost the way it can be with an integer format).

Three auto-exposure metering modes (`--auto-expose-mode`): `average` (whole-frame mean to middle gray - the original, simplest mode), `highlight_safe` (pins a high percentile, default 99.5th, to a target below clipping, default 0.9 - protects highlights at the cost of shadow detail, useful for high-contrast scenes), and `matrix` (center-weighted zone average, mimicking a camera's multi-zone evaluative metering - less swayed by extreme brightness at the frame edges than plain averaging). These fill a gap flagged directly in the module's own docstring since it was first written.

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

## Photoshop / DaVinci Resolve preset export (.cube LUT)

Bakes any of the `apply_*` brand/film-simulation functions already registered in `hybrid_engine/core/preset_inverse.py`'s `TARGET_FUNCS` registry into a standard Adobe `.cube` 3D LUT file (`core/lut_export.py`). Unlike a parametric ACR/`.xmp` preset, a `.cube` file just stores "input color -> output color" - it doesn't matter whether the source function's internals are an HSV rotation, a Lab curve, or CLAHE, so it can carry over a brand's look exactly as-is. Photoshop's Color Lookup adjustment layer reads `.cube` directly, and so do DaVinci Resolve, Premiere, and After Effects.

```
python3 -m tools.export_lut --list                            # list all available presets
python3 -m tools.export_lut hasselblad hasselblad.cube
python3 -m tools.export_lut fuji_astia fuji_astia.cube --size 33   # 33 is the Adobe-standard grid size
python3 -m tools.export_lut hasselblad hasselblad.cube --install-lightroom  # also copy into Lightroom/ACR's LUT Profiles folder
```

**Known limitation**: functions built on CLAHE (adaptive local contrast, e.g. `fuji.apply_pro_neg_hi`) produce output that depends on the surrounding pixel distribution, not just the input color alone - a 3D LUT is by definition a context-free per-pixel mapping (same input color always -> same output color), so this local adaptivity can't be represented exactly. `bake_lut_from_function()` passes the entire identity grid through as one synthetic image in a single call, so CLAHE at least produces a stable, grid-structure-dependent result instead of a meaningless per-point one - but the result still won't exactly match applying the same function to a real photo. This is a structural limitation of the `.cube` format itself, not a bug, and is flagged in `core/lut_export.py`'s module docstring following the project's "unverified/approximate" labeling convention.

**Lightroom Classic / Adobe Camera Raw**: no separate export path needed - since ACR 12.3 / Lightroom Classic 9.3, Adobe reads raw `.cube` files directly out of a fixed "LUT Profiles" folder (`~/Library/Application Support/Adobe/CameraRaw/LUT Profiles` on macOS, `%APPDATA%\Adobe\CameraRaw\LUT Profiles` on Windows) and lists them as Profiles in the Develop module's Profile Browser - unlike Photoshop, which needs a manual Color Lookup adjustment layer. `--install-lightroom` copies the just-baked `.cube` there for you (`--group` picks the Profile Browser subfolder, default `Hncs`); macOS/Windows only, since Adobe's own apps don't ship for Linux.

## DCP camera profile (colorimetric correction, X2D II only)

Where the `.cube` path above is a look layered onto an already-rendered
image, this one goes into the **color-conversion stage right after RAW
demosaic**. It least-squares-fits the 10 contributed X2D II ColorChecker
frames against XYZ(D50) references in camera-native RGB space (via
`decode_raw_native()`, which bypasses both libraw's color matrix and its
white balance), then exports the result as an Adobe `.dcp` profile that
Lightroom Classic/Camera Raw reads.

```
python3 -m tools.analyze_camera_native_matrix   # fit + cross-validated comparison against libraw's built-in matrix
```

Measured (patch-mean ΔE00 in XYZ D50): libraw's built-in matrix 7.81
-> chart-fit matrix **2.83** (leave-one-image-out cross-validation),
63.8% better than libraw. Full numbers and caveats in
`hybrid_engine/EVALUATION.md` ("후속 실측 21").

**Known limitations**: (1) the scene illuminant at capture time is
unrecoverable from this data - the contributed `manifest.csv`'s
`illuminant` column is empty, and since the chart references are
chromatically adapted to D50 before fitting, the resulting matrix is
D50-referenced by construction, so `CalibrationIlluminant1` is set to
**23 (D50)** to match the reference space, not a measured or assumed
scene illuminant; (2) all 10 frames come from a single burst, so there's
only one lighting condition and dual-illuminant interpolation isn't
possible; (3) **whether Lightroom actually renders this file as intended
is unverified** - there's no Adobe software in this project's dev
environment, so only TIFF structural validity (via exiftool) and numeric
round-tripping were checked; (4) X2D II 100C only (declared via
`UniqueCameraModel`).

## Brand-signature discriminability check (research)

`tools/classify_brand.py` runs in the opposite direction from this project's other tools - instead of building a new feature, it validates whether the already-computed population signatures for 10 brands (`datasets/<brand>/*_signature.json`, 852 photos total) actually carry enough signal to tell brands apart, via leave-one-out nearest-centroid classification. Distances are standardized (z-score), and the held-out photo is fully excluded from its own brand's centroid on every fold (no leakage). `npix`/`is_portrait`/`quality`/`subsampling` (image size, JPEG encoder settings) are deliberately excluded - keeping them would let the classifier learn "which brand uploads which resolution/JPEG setting" instead of an actual color-rendering difference. `ricoh_gr` is excluded from the classifier entirely: its `color_signature.json` stores `hue_median` instead of `hue_mean` like the other 10 brands (not the same statistic, and not comparable), so it's dropped rather than approximated - see the notice the CLI itself prints on every run. The LOO research validation itself has no predict mode - design rationale in `docs/superpowers/specs/2026-07-24-brand-classifier-design.md`. (The separate "for fun" predictor - `rank_brands_by_distance()` in `core/brand_classifier.py` / `tools/classify_brand.py predict` - is described a few paragraphs down and in `docs/superpowers/specs/2026-07-25-brand-predict-fun-design.md`.)

```
python3 -m tools.classify_brand                # Set A: tone+color+gamut (15-dim)
python3 -m tools.classify_brand --features all  # Set B: + texture (21-dim)
```

- Set A (no texture) - overall accuracy: `0.196`, macro accuracy: `0.232`
  (majority baseline `0.146`, uniform baseline `0.100` (1/10))
- Set B (with texture) - overall accuracy: `0.498`, macro accuracy: `0.490`

Texture's sharpening/micro_contrast use different formulas per brand (documented in `docs/project_structure.md` - Canon/Sony vs. Nikon/Leica/Pentax/Ricoh GR are on different scales), so if Set B scores higher than Set A, this result alone can't separate "genuine color difference" from "which formula was used." `leica` (45)/`pentax` (40)/`phaseone` (16) have thin samples, so those brands' recall figures are especially noisy.

**And for fun**: a `predict` subcommand built on top of the same validated tool - feed it any photo and it ranks which of the 10 brands' centroids it lands closest to, by distance. Texture is left out (Set A only, tone+color+gamut) - the same caveat as above, since texture's per-brand formulas can't be reconstructed for a new photo. Since measured accuracy is only 19.6%, it never shows a fabricated confidence number (no "87% Sony") - just the distance ranking, with that accuracy figure always printed alongside both the console and HTML output.

```
python3 -m tools.classify_brand predict photo.jpg
python3 -m tools.classify_brand predict photo.jpg --html result.html  # self-contained static HTML with the photo embedded as base64
```

## Video engine (frame-by-frame, engineering reuse - not a new measurement)

`tools/video_engine.py` applies an already-measured brand look to an actual video file (mp4), frame by frame - it does not add any new color-science measurement. 21 brands are supported: the 10 population-fit brands' measured tone-curve parameters (Canon/Leica/Nikon/Olympus/Panasonic/Pentax/Phase One/Ricoh GR/Sigma/Sony), plus Fujifilm's 10 film-simulation presets and Hasselblad's `apply_hncs` (`fuji_astia`/`fuji_pro_neg_std`/`fuji_pro_neg_hi`/`fuji_eterna_cinema`/`fuji_eterna_bleach_bypass`/`fuji_nostalgic_neg`/`fuji_reala_ace`/`fuji_classic_negative`/`fuji_acros`/`fuji_monochrome`/`hasselblad`) - see [docs/superpowers/specs/2026-07-26-video-engine-fuji-hasselblad-design.md](docs/superpowers/specs/2026-07-26-video-engine-fuji-hasselblad-design.md) for which presets needed a CLAHE-free variant and which didn't.

```
python3 -m tools.video_engine input.mp4 output.mp4 --brand canon
```

**Known limitations**: (1) audio is preserved by default via a lossless remux step (`imageio-ffmpeg`'s bundled static ffmpeg binary, `-c:v copy -c:a copy` - no re-encoding, first audio track only, no opt-out flag), and a remux failure aborts the whole run rather than falling back to a silent video; (2) for the 10 population-fit brands plus `fuji_pro_neg_hi` and `hasselblad` - the only 12 of 21 brands whose photo-mode `apply_*` actually uses CLAHE - the video path skips CLAHE (per-frame adaptive local-contrast correction) to avoid inter-frame flicker, so its output is not identical to the photo-mode look; the other 9 Fuji film-simulation presets never used CLAHE in the first place, so their video-mode output is applied unmodified from photo mode (the only difference is lossy video-codec compression); (3) this is not a video-specific color-science measurement - whether a camera brand actually renders video differently from its still JPEGs (different tone curve, sharpening, etc.) is unverified; (4) only validated against synthetic test video in this environment - no real camera mp4/mov sample was available for a smoke test.

## Browser demo (not measured data)

[`docs/demo/hncs_convert_demo.html`](docs/demo/hncs_convert_demo.html) is a standalone, offline-capable page that re-renders an uploaded photo's colors per brand entirely in the browser (canvas-based tone curve + saturation/temperature). **Its per-brand parameters are hand-picked for visual effect, not derived from this repo's measured population data or its `apply_*` pipelines** - the page states this prominently at the top. Open the file directly in a browser; no build step or server needed.

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
- [x] 15 Fujifilm film-simulation presets
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
- [docs/hncs_structural_research.en.md](docs/hncs_structural_research.en.md) -
  research-only comparison of HNCS's real 4-stage pipeline vs.
  `apply_hncs()`'s 3-stage simplification, with a leave-one-out ΔE
  experiment (result: inconclusive - the measured difference is not
  distinguishable from zero at n=13)
- [docs/hncs_external_sources_analysis.en.md](docs/hncs_external_sources_analysis.en.md) -
  analysis of 17 external documents (a Hasselblad-adjacent blog + a
  forum thread) about how HNCS actually works, cross-checked against
  this project's three structural experiments (all inconclusive/null
  at n=13)

## GUI (Desktop App)

A Tkinter desktop app that wraps the CLIs above into one window with 4
tabs - brand look preview, hybrid_engine conversion, RAW->Log pipeline,
and lens correction. Pure wrapper: no new color-science logic, just
point-and-click over the same commands shown throughout this README.

```
pip install -r requirements.txt   # now includes Pillow, needed to display images in Tk
python3 -m gui
```

Tkinter itself is in the Python standard library, but some distributions
(e.g. Homebrew Python on macOS) split it into a separate system package
(`python-tk`) - install that if `python3 -m gui` fails with a Tkinter
import error.

The lens-correction tab's usefulness depends entirely on the bundled
lensfun camera/lens database's coverage - e.g. it only has 4 old
Hasselblad camera entries with zero lens data, so it fails with
`lens_not_found` on every Hasselblad RAW sample.

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
