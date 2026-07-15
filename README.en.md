# HNCS

*[한국어 README](README.md)*

A project that measures official (or near-official) sample images from camera/digital-back manufacturers and approximates each brand's color science as code. It originally covered only Hasselblad's HNCS (Hasselblad Natural Colour Solution), but as the same methodology was extended to Fuji/Leica/Phase One/Pentax/Ricoh GR, the per-brand files grew and were reorganized into the structure below.

## Structure

```
brands/       Per-brand color-approximation functions (apply_*)
core/         Tone-curve/LUT/stats/validation helpers shared across all brands
datasets/     Committed reference CSVs (official sample metadata, scraped gallery links)
tools/        Analysis (analyze) / download / calibration scripts
models/       Pretrained models used for e.g. face detection
```

| File | Role |
|---|---|
| `brands/hasselblad.py` | ⭐ Official Stable - `apply_hncs` (parametric approximation unifying the X System HNCS) |
| `brands/hasselblad_learned.py` | Experimental - `apply_hncs_learned` (a LUT learned directly from raw+jpeg pairs; lower RMSE but only 10 samples) |
| `brands/hasselblad_day.py` / `brands/hasselblad_night.py` | Legacy - `apply_hasselblad_day`/`apply_hasselblad_night` (the day/night targets are converging toward `apply_hncs`'s overall population target, weakening the case for keeping them separate) |
| `brands/fuji.py` | 10 Fujifilm-style film simulation presets (Astia, PRO Neg, Eterna, Acros, Classic Negative, etc.) - Astia/Pro Neg Std/Eterna Bleach Bypass/Classic Negative are verified against real population data; Pro Neg Hi/Eterna Cinema/Nostalgic Neg have been further verified/recalibrated against same-scene comparison charts (n=1-3 samples, low confidence) |
| `brands/leica.py` | Leica color approximation - `apply_leica_look()` (population-fit, v1) |
| `brands/phaseone.py` | Phase One (Capture One's default rendering) color approximation - `apply_phaseone_look()` |
| `brands/pentax.py` | Pentax color approximation - `apply_pentax_look()` |
| `brands/ricoh_gr.py` | Ricoh GR color approximation - `apply_ricoh_gr_look()` |
| `brands/canon.py` | Canon color approximation (EOS R5/R6/R8/R3/R, 5-body population) - `apply_canon_look()` |
| `brands/nikon.py` | Nikon color approximation (Z6/Z6 II/D780, 3-body population - the Z9/D850 galleries only had placeholder images with stripped EXIF, so they were excluded) - `apply_nikon_look()` |
| `brands/sony.py` | Sony color approximation (A7/A7R/A7S/A7 III/A7 IV, 5-body population, 23 photos per body) - `apply_sony_look()` |
| `brands/panasonic.py` | Panasonic (Lumix) color approximation (GH5/GH6/G9 MFT + S5/S1 full-frame, 5-body population, n=120) - `apply_panasonic_look()` |
| `brands/olympus.py` | Olympus (now OM System) color approximation (OM-1/OM-5/E-M1 Mark III/E-M1X/PEN-F, 5-body population, n=122) - `apply_olympus_look()` |
| `brands/sigma.py` | Sigma color approximation (Bayer fp/fp L + Foveon sd Quattro/dp2 Quattro/SD1 Merrill, 5-body population, n=83) - `apply_sigma_look()` |
| `core/curve.py` | Tone-curve math (`film_curve`/`s_curve`/`apply_highlight_rolloff`/`shadow_lift`) - shared by multiple brand modules |
| `core/lut.py` | LUT application helper |
| `core/engine.py` | Shared engine for population-fit brands (leica/phaseone/pentax/ricoh_gr, and by extension every other population-fit brand added later) - all of them lack a raw baseline and plug their population target directly into `film_curve` with the same structure, so this was consolidated into one function |
| `core/stats.py` | Population statistics computation (`image_stats`: black-point p2 / white-point p99.5 / saturation / shadow fraction) |
| `core/validation.py` | "Is this genuinely unedited SOOC" EXIF verification, "does this actually decode intact" integrity check (`is_image_usable`), hue-measurement helper |
| `core/denoise.py` | Noise reduction (`denoise()`: nlm/bilateral) - used to clean up high-ISO samples before applying a brand look |
| `datasets/hasselblad/hasselblad_sample_images.csv` | Hasselblad's official sample metadata (camera/lens/photographer/jpeg_url/raw_url) |
| `datasets/hasselblad/texture_signature_recomputed.json` | The existing `texture_signature.json`'s filenames are just `orig_N.jpg`, so matching back to the original CSV rows is unreliable (positional guess only - 3 mismatches found out of 78 spot-checked). Rebuilt from scratch by re-downloading the originals from the CSV's jpeg_url column, with filenames that match the CSV exactly (n=123, includes the noise off-by-one fix). The original file is left untouched to preserve the historical record |
| `datasets/fuji/fuji_sample_pages.csv` | RAW/JPEG Google Drive links for Fuji galleries on mirrorlesscomparison.com |
| `datasets/fuji/fuji_imaging_resource_filmmodes.json` | 269 photos collected from imaging-resource.com's X100V/X-T5/X-T4 review galleries, including exiftool FilmMode tags (Velvia/Provia/Classic Negative/Bleach Bypass/Classic Chrome) - the evidentiary basis for the Eterna Bleach Bypass recalibration and the new Classic Negative preset |
| `datasets/fuji/chart_comparisons/manifest.json` + `chart_comparison_stats.json` | Crop boxes (manifest) and real-delta-vs-preset-delta comparison results (stats) for 8 "same-scene multi-film-mode comparison chart" images the user personally found and shared - unlike the population approach, this pairs a fixed scene/exposure, giving stronger evidence. The original chart images themselves are third-party work and are not committed (`downloaded_samples_fuji_charts/`, gitignored) |
| `datasets/<brand>/{tone,color,texture,gamut}_signature.json` + `joint_distribution.npz` | Pixel-level 5-part signature analysis (present for hasselblad/leica/pentax/ricoh_gr/phaseone/canon/sony/nikon/panasonic/olympus/sigma) - tone, saturation/hue, sharpening/micro-contrast/noise/edge-halo, Lab gamut, using a photo-count-weighted mean methodology (pooling raw pixels distorts the result due to resolution variance - see the `methodology` field in `tone_signature.json`). **Caution**: the texture fields' sharpening/micro_contrast were re-derived independently per brand since the original computation scripts were never committed, and the scales drifted - Sony's initial sharpening came out 15-20x too large and was rescaled to match Canon's formula (/15), and Canon/Sony's micro_contrast (DoG sigma 1,2) isn't directly comparable to Nikon/Leica/Pentax/Ricoh GR's (sigma 1,4 estimated, landing an order of magnitude higher) - see each brand's `.py` docstring and `texture_signature.json`'s methodology field for details. Starting with Panasonic/Olympus/Sigma, agents were explicitly instructed to reuse Canon's formula verbatim to prevent a repeat, and sharpening/micro_contrast for those brands do land close to Canon's, confirming consistency |
| `tools/analyze.py` | Population statistics/validation CLI - `hasselblad`/`leica`/`phaseone`/`pentax`/`ricoh_gr`/`fuji_film_modes`/`portrait` modes |
| `tools/download.py` | Shared imaging-resource.com gallery scraper + Fuji Google Drive RAW/JPEG pair downloader |
| `tools/calibrate.py` | Hasselblad raw+jpeg pair calibration CLI - `grid_search`/`learn_curve`/`regularize` modes |
| `tools/fuji_chart_calibrate.py` | Fuji "same-scene comparison chart" verification CLI - `python3 -m tools.fuji_chart_calibrate report` (extracts strips using manifest.json's crop boxes -> prints a real-delta vs preset-delta table) |
| `tools/denoise.py` | Noise reduction CLI - `python3 -m tools.denoise input.jpg output.jpg [--strength N] [--method nlm\|bilateral]` |
| `models/yunet.onnx` | Face detection model (OpenCV Zoo, YuNet 2023mar) - used by `tools/analyze.py portrait` |

## Image trustworthiness policy (2026-07~)

We found that imaging-resource.com's media CDN stores genuinely corrupted originals across several camera review galleries (72% of the Hasselblad X2D 100C gallery, 100% of the Phase One XF 100MP gallery, 40% of the Pentax 645Z/K-1 galleries had decoding stop partway through with the rest saved as blank rows - repeated re-downloads via different methods reproduced the exact same result, confirming this is a defect in the files as stored on the site, not a transfer issue). `cv2.imread()` silently "succeeds" on these files too, only printing a "Premature end of JPEG file" warning and filling the rest with black pixels - load success or shape alone can't filter these out.

**So from this point on, every population analysis only uses images that pass `core/validation.py`'s `is_image_usable()`** (which judges corruption via row-wise standard deviation). This is already applied across every download path in `tools/analyze.py` (Hasselblad's official CDN + the 4 imaging-resource.com brands) and `tools/download.py`'s Fuji Google Drive download path (`download_fuji_pairs()`), so newly scraped images are automatically filtered going forward.

Re-verifying all previously committed/cached population data:
  - Leica (45 photos), Fuji (mirrorlesscomparison.com, 40 JPEGs across 10 bodies): 0 corrupted - no change in numbers
  - Ricoh GR: the existing 40 photos (GR III+IIIx) had 0 corrupted. Later expanded to n=80 by finding additional GR/GR II galleries (GR II's HDR on/off comparison shots were filtered out) - replaced with the re-verified numbers
  - Pentax (16 of 40 corrupted): re-collected to keep n=40, replaced with re-verified numbers
  - Phase One (all 30 of 30 corrupted): re-collected from the whole gallery (110 candidates), but 91 of those were also corrupted, shrinking to n=16 - replaced with re-verified numbers (also tried the Phase One XT gallery to expand the sample, but the surviving images were all shot on a color-less Achromatic back, unusable for a color population, so it was excluded)
See each brand file's docstring for exact numbers.

## Brand-function QA verification (2026-07)

After adding Canon/Sony/Nikon, ran every `apply_*` function in `brands/*.py` (4 Hasselblad variants + 10 Fuji presets + 7 population-fit brands (Leica/Phase One/Pentax/Ricoh GR/Canon/Sony/Nikon), 21 total) on a random BGR array and confirmed shape/dtype are preserved. Everything works correctly - no bugs found
(note: `apply_acros`/`apply_monochrome` return single-channel grayscale by design and need separate handling in shape comparisons; `apply_highlight_rolloff`/`apply_lut`, re-exported into `fuji.py` from `core.curve`/`core.lut`, are general-purpose helpers rather than brand presets and are out of scope for this test). This started as a manual smoke test and was later formalized into `tests/test_brands.py` - in the process, discovered the README had been incorrectly stating the Fuji preset count as 9 and corrected it to 10 (the code itself was already correct; only the docs were stale).

Canon/Sony/Nikon were also extended with the same pixel-level 5-part signature analysis (tone/color/texture/gamut/joint_distribution) as the other 5 brands (`datasets/canon,sony,nikon/`) - in the process, 3 parallel agents each independently guessed the sharpening/micro_contrast formulas and the scales drifted, so Sony was recomputed and a Canon/Sony-vs-Nikon micro_contrast non-comparability caveat was left in place (see each brand's docstring). Also investigated whether these three brands could be upgraded to raw-baseline calibration (Hasselblad-grade) via a raw+jpeg pair source, but concluded it's not possible on either mirrorlesscomparison.com (no actual pairing) or imaging-resource.com (raw download links are dead) - kept the population-fit approach.

**Population-statistics reproducibility audit (2026-07)**: for all 10 population-fit brands out of the 13 total (leica/phaseone/pentax/ricoh_gr/canon/sony/nikon/panasonic/olympus/sigma), fully re-verified whether the population numbers documented in each brand's docstring still reproduce from scratch using the currently locally cached images, via `core.stats.image_stats()` (834 cached files total, integrity re-confirmed with `is_image_array_usable()` - 0 corruption). Result: **10/10 matched**, zero real discrepancies. Sigma's re-implemented burst-deduplication logic reproduced a false positive already documented in `brands/sigma.py` (mistaking two photos with different filename prefixes but coincidentally close frame numbers for the same scene - "YC-78.jpg" vs "YSDIM0080.jpg"), but this was traced to the audit script not re-implementing the original collection script's prefix-matching refinement, not a problem with the actual committed data. The `_TOE_LIFT`/`_WHITE_POINT` constants also matched each docstring's final adopted values exactly across all 10 brands.

## Tests

There's an `unittest`-based test suite under `tests/` (no pytest or other external dependency added, keeping `requirements.txt`'s minimal-dependency principle). Covers `core/curve.py` (tone-curve math, boundary conditions/monotonicity/continuity) / `core/stats.py` (population statistics computation) / `core/validation.py` (integrity validation, reproducing the CDN corruption pattern) / `core/engine.py` (the population-fit engine) / `brands/*.py` (shape/dtype preservation for every `apply_*` look function, Fuji preset count consistency) / `tools/fuji_chart_calibrate.py` (crop-box extraction, delta aggregation) / `tools/download.py` (imaging-resource.com HTML parsing, filtering, Google Drive URL classification - network calls are mocked) / all of `datasets/*/texture_signature.json` (whether sharpening/micro_contrast/noise fall within a sane cross-brand range - a regression guard against a Sony-scale-bug-style order-of-magnitude error). `.github/workflows/tests.yml` runs this suite automatically on every push/PR.

```
python3 -m unittest discover -s tests -v
```

## Installation

```
pip install -r requirements.txt
```

`.claude/settings.json` is the sandbox config that auto-allows network access to `cdn.hasselblad.com`, `live.staticflickr.com`, etc. when running analysis scripts in this repo with Claude Code.

## Usage

```python
import cv2
from brands.hasselblad import apply_hncs

img = cv2.imread("photo.jpg")
result = apply_hncs(img)
cv2.imwrite("photo_hncs.jpg", result)
```

Every `apply_*` function in `brands/*.py` uniformly takes a BGR `np.ndarray` and returns a BGR `np.ndarray`. Run from the repo root so the `core`/`brands`/`tools` import paths resolve correctly.

### Reproducing/re-verifying the measurements

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

## Conclusions from measurements so far (as of v12/day-night v3, see `brands/hasselblad.py`'s docstring)

- **Pixel-level 5-part signature analysis (2026-07, all 124 official samples, genuine originals)**:
  saved to `datasets/hasselblad/{tone,color,texture,gamut}_signature.json` +
  `joint_distribution.npz`. Computed tone/saturation-hue/sharpening-noise-halo/Lab a·b gamut
  pixel-by-pixel against genuine originals (no resize/re-encoding).
  - **Confirmed empirically that you must NOT just pool all pixels and take percentiles**:
    the 124 photos range from 300K to 200M pixels, a 676x spread, so pixel-pooling lets a few
    large photos dominate the statistics (pooled b2 collapses to 1.0, vs. 18.1 for the
    per-photo-equal-weight average - more than a 10x difference). The population target must
    be computed as a "per-photo equal-weight average" - the pooled histogram itself is still
    kept in `joint_distribution.npz`, but it isn't used as the target.
  - **Cross-checked the cache (`downloaded_samples/`, resize + re-encoded) against the genuine
    originals 1:1 for all 124 photos**: over the 94 shadow-valid (dark_pct>5%) photos, black-point
    p2 was 11.27 (cache) vs 10.63 (original) - a 0.6 / 5.7% difference. White-point p99.5 was
    223.85 (cache) vs 225.56 (original) - a 1.7 / 0.8% difference. Both are noise-level
    differences, **confirming the cache did not distort the tone-curve correction target
    (b2/w995)** - the existing target (11.3/223.9) that v9/`apply_hncs` is based on remains valid.
    (Note: during this re-verification, a file-index mapping mistake initially produced a false
    conclusion that "cache vs. original differ by 60%" - this was caught and corrected by
    re-cross-referencing all 124 photos 1:1; the numbers above are the corrected ones.)
  - **Conclusion: no changes needed to `apply_hncs`/day-night parameters.** The tone target was
    already accurate, and saturation/hue/texture/gamut (the color/texture/gamut signatures) are
    channels HNCS was never designed to touch in the first place, so they aren't a "target" -
    they're stored purely as reference data recording what the population actually looks like.
- **Pipeline signature analysis (2026-07, re-downloaded all 124 official samples as genuine
  originals)**: bypassed `downloaded_samples/` (the project's own cache, which distorts noise
  metrics via resize + re-encoding) and freshly `curl`'d all 124 unprocessed originals
  (`/tmp/true_originals/`, 4.5GB) to measure sharpening strength/micro-contrast/noise/edge halo/
  JPEG compression characteristics. The download URL list had 18 overlaps with an earlier
  5-photo pilot sample, which were removed (105 unique). Note, though: the `orig_*.jpg` set
  (124 photos, 1:1 with CSV rows) that was actually used for the population statistics and the
  day/night v3 correction has no internal duplicates at all - the existing recalibration results
  are unaffected.
  - JPEG quality: 77% (81/105) are Q99 · YCbCr 4:4:4 (effectively lossless), with a minority
    (17 photos, filenames suggesting early X1D-series bodies) at Q75 · 4:2:0. The brand filter
    itself doesn't re-encode to JPEG, so this figure is reference metadata only.
  - Sharpening energy (mean absolute high-frequency value, median 2.65) and micro-contrast
    (DoG std, median 6.37) are strongly correlated (r=0.77) - a signal of a consistent local-
    contrast processing style. However, since these values are self-referential statistics
    between finished JPEGs rather than a paired comparison against an unprocessed original,
    there's no baseline to quantify how much stronger they are than a neutral render → judged
    insufficient grounds to add a new sharpening parameter to the curve module, deferred.
  - Edge halo (overshoot): the median is essentially flat across quality tiers (7-8%, Q<=80 /
    81-95 / >95 all similar) - the "lower quality → bigger halo" pattern seen in the 5-photo
    pilot disappears once the sample grows (the mean spikes because of a few extreme outliers,
    irrelevant on a median basis). Correlation with sharpening energy is also weak (r=0.24).
    Outliers (orig_133 at 129.9%, orig_68 at 45.6%, etc.) appear to be genuine specular-highlight
    edges misdetected as halo - reconfirming the existing caveat that this metric can't
    distinguish JPEG ringing / genuine halo / a scene's own bright reflections.
    → halo-based parameters also deferred
  - Noise: per-file variance is extreme (0.001-6.6) and the per-subsampling-group means overlap
    heavily (4:2:0 0.34 / 4:4:4 1.19 / 4:2:2 0.32, n=7-81), so it isn't explained by chroma
    subsampling or JPEG quality - reconfirming the existing conclusion that it's scene-content-
    dependent (ISO, light level, texture). No grounds for a new brand-wide fixed grain/denoise
    parameter.
  - **Conclusion**: even scaling the sample up to the full 124 photos, none of
    sharpening/halo/noise produced a signal clean and confident enough to say "encode this value
    as a new parameter in the code." Per the project's existing overfitting-avoidance principle,
    decided not to change `brands/hasselblad.py` - the real output of this analysis is the
    evidence-backed conclusion that "not changing anything is correct."
- **Re-verification (2026-07, after the brands/core/tools refactor)**: re-ran `apply_hncs`
  (parametric) and `apply_hncs_learned` (learned) through `tools.calibrate grid_search`/
  `learn_curve` and confirmed the RMSE reproduces exactly as before the refactor
  (23.31→16.51 for grid_search, 23.31→15.41 for learn_curve) - there are still only 10 raw+jpeg
  pairs (the rest are dead links), so there's no new data to recalibrate against
- **day/night v3**: built a contact sheet from all 124 official samples and reviewed each one by
  eye, picking out 12 unambiguous night scenes (streetlights/neon/aurora/Milky Way/city night
  views, etc.) and reclassifying the remaining 112 as day (v2 had only 5 day + 4 night samples).
  New targets: day black-p2=11.5/white-p99.5=224.1 (n=112), night black-p2=9.7/white-p99.5=221.3
  (n=12) - a much larger sample than v2, and it converges (even more so) toward the overall
  population target (11.3/223.9). `apply_hasselblad_day` was refit against the new target
  (midtone_gamma 0.95→0.85, contrast_n 1.15→1.35, white_point 0.96→0.92, RMSE 22.01→18.65);
  `apply_hasselblad_night`'s grid search landed back on the existing defaults as optimal, no
  change. The case for keeping day/night as separate presets keeps weakening (not yet merged)

- Over the full pool of 124 official samples: black-p2=11.3, white-p99.5=223.9; the portrait
  subset (43 photos) is 10.2/226.3 - no major shift from v8 (19-20 photos)
- Automated verification on the 43 portrait photos found skin-tone hue is essentially unchanged
  before/after `apply_hncs` (mean |delta|=0.21, max 2.0, on a hue scale of 0-179)
- Grid-searching against genuine raw→JPEG before/after pairs (10 photos) revealed the curve had
  no global exposure/gamma correction step (`exposure_gamma`), so it couldn't close the
  brightness gap between the pre/post-grading images (v10) → added an `exposure_gamma`
  parameter, excluded an extreme high-key sample (an indoor Oculus shot with no shadows) from
  the black-point fit, and re-searched (v11)
- Final adoption (`apply_hncs`, v11): applied `white_point=1.0`, `exposure_gamma=0.7`, kept
  `toe_lift`/`shoulder_start` at their original values (0.001/0.78) - RMSE improved from 36.3 to
  23.3. Lowering the shoulder start point to 0.5 drops RMSE further to 16.5, but with only 8
  shadow-valid samples, changing the curve's shape itself was judged an overfitting risk and
  deferred
- Tried switching the raw-rendering baseline to a linear gamma (1,1), which seemed more
  "accurate" on paper, but RMSE actually got worse (23.3→28.2) - rawpy's own demosaic/color-
  matrix algorithm differs from Hasselblad's actual pipeline, so getting "closer to the sensor"
  didn't help (a negative result, reverted)
- `apply_hncs_learned` (v12): without assuming a toe/shoulder shape, learned the
  neutral_L→target_L mapping directly from raw+jpeg pairs at the pixel level (10.78 million
  pairs) - RMSE 15.4, better than the parametric version's 23.3. The sample-size constraint
  (still only 10 raw+jpeg pairs) remains the same, and the hue error introduced by the round-
  trip through 8-bit conversion is slightly larger than `apply_hncs`'s (mean |delta|~3.0/179,
  still visually negligible)
- Tried regularizing the learned LUT toward the parametric curve out of concern for the small
  sample, but a 10-fold leave-one-out cross-validation showed the pure unregularized empirical
  LUT performs best (LOO RMSE 14.6, getting worse - 20.7→28.0 - as regularization strength
  increases) - because there are enough pixel samples per bin that variance isn't the problem;
  the parametric curve's own shape bias is the bigger source of error. `apply_hncs_learned` is
  kept without regularization

## Fujifilm (`brands/fuji.py`)

Fuji has multiple built-in film-simulation presets (Provia/Astia/Velvia/Classic Chrome/Pro Neg Std, etc.), so a different verification method was used than for Hasselblad: gather genuinely unedited SOOC JPEGs from mirrorlesscomparison.com review galleries, and compare population statistics grouped by the actual Film Mode tag read via exiftool, to confirm each preset moves saturation/tone in the same direction as the real measurements (`tools/analyze.py fuji_film_modes`).

- Tried to find same-photo raw+jpeg pairs (`tools/download.py fuji-pairs`), but this site's "RAW samples" and "SOOC JPG samples" folders were never actually paired by shoot to begin with - just separate photos each - across 10 cameras, 57 RAW + 40 JPEG downloads yielded only 3 pairs whose EXIF capture time matched exactly (and even those were all Provia). Abandoned raw-based calibration (Hasselblad v10-v12 grade) in favor of population comparison.
- Comparing measured direction (n=8-15) against applying `apply_astia`/`apply_pro_neg_std` to Provia photos, both moved saturation in the opposite direction from the real measurement (Astia measured -12.9 vs. preset +9.4; Pro Neg Std measured -19.4 vs. preset +11.3). The cause was applying the tone curve to each BGR channel individually, letting the gap between channels widen and saturation re-rise (original 125.0 → 109.4 after HSV desaturation → 139.7 after the per-BGR-channel curve, higher than the original). Fixed both presets to apply the curve only on the Lab L channel.
- Pro Neg Std was still moving the wrong direction even after switching to the L channel - it turned out the curve shape itself was wrong. The old version used a contrast-boosting S-curve (n=1.4), but the real measurement showed Pro Neg Std actually has a flatter profile with lower contrast than Provia (black-p2 +2.7, white-p99.5 -19.0). Replaced with a contrast-reducing curve (n=0.65).
- Re-verification after the fix: Astia went from 1/3 to 2/3 direction matches; Pro Neg Std went from 0/3 to 3/3.

## Leica (`brands/leica.py`)

Leica has no Fuji-style multiple film simulations, and no raw+jpeg pair set like Hasselblad's official kit could be found (dpreview/kenrockwell/photographyblog are Cloudflare-bot-blocked, stevehuffphoto.com's samples are Photoshop/Lightroom-edited and not SOOC, the DNGs linked from leicarumors.com sit in a Dropbox folder that's JS-rendered so the listing can't be scraped - `gdown` worked around Google Drive for Fuji, but there's no equivalent tool for Dropbox. Also dug into Leica's official site down to its Drupal jsonapi, still nothing exposed there; on imaging-resource.com, every additional slug tried beyond M9/X Vario/SL2 was invalid). Instead, gathered 45 unedited SOOC JPEGs from imaging-resource.com camera review galleries (M9/X Vario/SL2, excluding Photoshop/Lightroom-edited files via the exiftool Software tag) and computed population statistics only - the same tier as Hasselblad v8/v9, with no genuine before/after fit against raw yet.

- Population statistics (n=45): black-p2=9.2, white-p99.5=229.8, saturation=98.6. Per-camera variance is large (SL2 white-p99.5=192.1 vs. M9 251.6), so the overall average is used as the target until more samples are gathered
- `apply_leica_look()` is a v1 built by plugging this population target directly into `film_curve`'s toe_lift/white_point - there's no raw baseline, so it wasn't fit by grid search, and the shoulder_start/clahe_clip/hue-saturation-untouched assumptions are all borrowed from Hasselblad's values, unverified. The first thing to verify if a raw pair is ever found

## Phase One (`brands/phaseone.py`)

Phase One digital backs are studio/tethering-centric, so there's effectively no in-camera JPEG engine like a consumer camera has - every sample pulled from imaging-resource.com had EXIF Software = "Capture One" (Phase One's own RAW converter). So what this project reproduces isn't "camera JPEG" but "Capture One's default rendering." No raw (IIQ) download link could be found in imaging-resource.com's current site template (same as Leica's SL2 - looks like a feature that disappeared in a site redesign) - approached with the same population-statistics method as Leica.

- The first run (n=20) had 8/20 that were ISO noise test charts (ISO 50-25600, the same scene shot repeatedly), which distorted the population - mean saturation came out at 76.9, then jumped to 118.6 once the chart shots were removed. Added a "-iso-" filename filter and re-ran with the sample expanded to 30
- Population statistics (n=30, ISO charts excluded): black-p2=11.4 (9 shadow-valid), white-p99.5=228.4, saturation=96.0
- `apply_phaseone_look()` uses the same method as Leica (no raw baseline, population target plugged directly into toe_lift/white_point) - same unverified shoulder_start/clahe_clip/hue-saturation-untouched assumptions

## Pentax (`brands/pentax.py`)

Gathered 40 unedited SOOC JPEGs from imaging-resource.com review galleries (645Z medium format + K-1 full-frame). Confirmed genuine SOOC via EXIF Make="RICOH IMAGING COMPANY, LTD." (Pentax is a brand owned by Ricoh Imaging) and Software being a camera firmware version string. Couldn't find a DNG link on this site either, same as Leica/Phase One, so only population statistics are used.

- Population statistics (n=40): overall black-p2=10.8, white-p99.5=239.1, saturation=124.1
- Per body: 645Z (n=20) black-p2=10.4/white-p99.5=247.2/saturation=141.1, K-1 (n=20) black-p2=11.1/white-p99.5=231.0/saturation=107.1 - the black point is nearly identical but 645Z is higher on both white point and saturation. Whether this is a medium-format characteristic or sample bias (a single reviewer) is unconfirmed - can't be determined without a raw pair
- `apply_pentax_look()` uses the same population-fit method and has the same unverified limitations (shoulder_start/clahe_clip/hue-saturation-untouched)

## Ricoh GR (`brands/ricoh_gr.py`)

Extracted population statistics from imaging-resource.com review galleries (GR III + GR IIIx). Same Ricoh Imaging brand as Pentax, so the EXIF pattern is identical.

- The first collection (n=40) had GR IIIx aperture-bracketing test shots mixed in (-f2.8/-f4.0/-f8.0, etc., the same scene shot 6 times), distorting the population - the same class of problem as Phase One's ISO chart. Filtered out via a filename regex (`-f\d`) and recomputed (the effect was small: saturation 87.7→84.9, since these made up 15% of the sample vs. the ISO test's 30%). Reflected into `tools/analyze.py`'s skip patterns so future runs exclude them automatically
- Population statistics (n=34, f-value tests excluded): black-p2=10.3, white-p99.5=243.9, saturation=84.9
- `apply_ricoh_gr_look()` uses the same population-fit method with the same unverified limitations
