# Project Structure Details

*[한국어](project_structure.md)*

Back to the [main README](../README.md).

```
brands/       Per-brand color-approximation functions (apply_*)
core/         Tone-curve/LUT/stats/validation helpers shared across all brands
datasets/     Committed reference CSVs (official sample metadata, scraped gallery links)
tools/        Analysis (analyze) / download / calibration scripts
models/       Pretrained models used for e.g. face detection
docs/         Detailed documentation (this directory)
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
| `core/engine.py` | Shared engine for every population-fit brand (leica/phaseone/pentax/ricoh_gr and every other population-fit brand added since) - they all lack a raw baseline and plug their population target directly into `film_curve` with the same structure, so this was consolidated into one function |
| `core/stats.py` | Population statistics computation (`image_stats`: black-point p2 / white-point p99.5 / saturation / shadow fraction) |
| `core/validation.py` | "Is this genuinely unedited SOOC" EXIF verification, "does this actually decode intact" integrity check (`is_image_usable`), hue-measurement helper |
| `core/denoise.py` | Noise reduction (`denoise()`: nlm/bilateral) - used to clean up high-ISO samples before applying a brand look |
| `core/log_pipeline.py` | RAW -> Log colorspace pipeline, separate from the brand engine - standardizes RAW into ProPhoto RGB Linear, then encodes into a video camera's Log curve/gamut (F-Log2/S-Log3/V-Log/etc.), with optional `.cube` LUT application ([inspired by raw-alchemy](https://github.com/shenmintao/raw-alchemy), built on `colour-science`) |
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
| `tools/raw_pipeline.py` | RAW -> Log colorspace CLI - `python3 -m tools.raw_pipeline input.raw output.tiff\|.exr --log-space F-Log2 [--lut looks/x.cube] [--exposure EV] [--auto-expose-mode average\|highlight_safe\|matrix]` |
| `tools/verify_contributed_pairs.py` | Contributed-dataset verification CLI (manifest-vs-EXIF cross-check, raw/jpeg same-shutter sync, edit-contamination scan) - spec in `datasets/hasselblad/contributed/README.md` |
| `tools/highlight_rolloff_signal.py` | Explored whether shoulder_start/clahe_clip could be estimated per brand (conclusion: insufficient evidence, kept the defaults - see `core/engine.py`'s docstring) |
| `models/yunet.onnx` | Face detection model (OpenCV Zoo, YuNet 2023mar) - used by `tools/analyze.py portrait` |
