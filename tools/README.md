# tools/

*[한국어 README](README.ko.md)*

CLIs and research scripts. Nothing here is imported by shipped code -
see this directory's `CLAUDE.md` for conventions. Run everything below
from the repo root so the `core`/`brands`/`tools` import paths resolve.

## RAW -> Log Colorspace Pipeline (Professional)

A separate module with a different purpose from the per-brand `apply_*` engine in `brands/`. Instead of approximating "the JPEG this specific camera actually produces," it standardizes RAW files - **regardless of camera** - into a common intermediate colorspace (ProPhoto RGB Linear), then encodes into whichever video camera's Log curve/gamut you want (F-Log2, S-Log3, V-Log, ARRI LogC3/4, etc.) so that camera's creative `.cube` LUTs can be applied to RAW photos without color drift ([inspired by raw-alchemy](https://github.com/shenmintao/raw-alchemy), reimplemented here on top of `colour-science`).

```
python3 -m tools.raw_pipeline photo.CR3 photo.tiff --log-space S-Log3
python3 -m tools.raw_pipeline photo.CR3 photo.exr --log-space S-Log3   # 32-bit float OpenEXR, scene-referred
python3 -m tools.raw_pipeline photo.ARW photo.tiff --log-space V-Log --lut looks/my_look.cube
python3 -m tools.raw_pipeline photo.NEF photo.tiff --log-space F-Log2 --exposure 1.0
python3 -m tools.raw_pipeline photo.CR3 photo.tiff --log-space V-Log --auto-expose-mode highlight_safe
python3 -m tools.raw_pipeline photo.CR3 photo.tiff --log-space V-Log --auto-expose-mode matrix
python3 -m tools.raw_pipeline photo.CR3 photo.tiff --log-space S-Log3 --auto-wb-mode white_patch
python3 -m tools.raw_pipeline photo.CR3 photo.tiff --log-space S-Log3 --auto-wb-mode shades_of_gray
python3 -m tools.raw_pipeline photo.CR3 photo.tiff --hdr-space HLG
python3 -m tools.raw_pipeline photo.CR3 photo.exr --hdr-space PQ --hdr-peak-nits 4000
python3 -m tools.raw_pipeline photo.RAF photo.tiff --log-space F-Log2 --lens-correct
```

`--log-space` and `--hdr-space` (BT.2020 PQ/HLG, unverified - never checked against a real HDR10/HLG display) are mutually exclusive; `--lut` is `--log-space`-only.

Two automatic estimation knobs, both off by default (camera WB / manual exposure are the defaults): `--auto-expose-mode` (`average`/`highlight_safe`/`matrix` - see below) and `--auto-wb-mode` (`white_patch`/`shades_of_gray`, Finlayson&Trezzi 2004 - measured ΔE00 14-16 vs the camera's actual white balance on the 13-pair Hasselblad calibration set, i.e. clearly different color, not recommended for real use, kept for lighting-unknown creative experiments).

`--lens-correct` runs the same EXIF/lensfun geometric distortion correction as `lens_correction.py` below (shares its `resolve_lens_params()`), applied to the linear ProPhoto RGB image right after RAW decode, before auto-WB/exposure/Log/HDR/LUT - since it only repositions pixels it doesn't touch color, so every later stage sees the same corrected geometry. Off by default; when on, a lensfun match failure aborts the run (`--make`/`--model`/`--lens`/`--focal-length`/`--aperture`/`--lens-distance` override EXIF, same as `lens_correction.py`).

![RAW -> Log colorspace demo - sRGB decode vs V-Log encoding](../docs/images/raw_pipeline_demo.jpg)

*The same RAW (Fujifilm X-T1) decoded to standard sRGB (left) vs encoded with
`raw_pipeline --log-space V-Log` (right). The flat, low-contrast/
low-saturation look on the right is expected - it's the ungraded Log state
as-is.*

Output format is chosen by extension - `.tif`/`.tiff` for a 16-bit integer file (broadest viewer compatibility), `.exr` for 32-bit float OpenEXR (the actual industry-standard scene-referred format for Log/grading workflows - DaVinci Resolve, Nuke, etc. read it directly, and float means no clipping headroom is lost the way it can be with an integer format).

Three auto-exposure metering modes (`--auto-expose-mode`): `average` (whole-frame mean to middle gray - the original, simplest mode), `highlight_safe` (pins a high percentile, default 99.5th, to a target below clipping, default 0.9 - protects highlights at the cost of shadow detail, useful for high-contrast scenes), and `matrix` (center-weighted zone average, mimicking a camera's multi-zone evaluative metering - less swayed by extreme brightness at the frame edges than plain averaging). These fill a gap flagged directly in the module's own docstring since it was first written.

Supported Log spaces: see `LOG_SPACES` in `../core/log_pipeline.py` (F-Log/F-Log2/V-Log/N-Log/Canon Log 2·3/S-Log3/S-Log3.Cine/Arri LogC3·4/Log3G10/D-Log). The curve-gamut pairings use `colour-science`'s own definitions as-is - they haven't been cross-checked exhaustively against each manufacturer's official spec, the same kind of "unverified" caveat as the rest of this project's flagged items.

## Lens distortion correction

A purely geometric tool, independent of the color-rendering engines above - undoes barrel/pincushion distortion using the camera+lens profile database bundled with [lensfun](https://lensfun.github.io/) (via `lensfunpy`, 948 cameras / 1304 lenses, no extra system package needed beyond `pip install -r requirements.txt`). Reads Make/Model/LensModel/FocalLength/FNumber from EXIF (`exiftool`) and looks up the matching profile automatically; accepts both RAW and already-rendered JPEG/TIFF/PNG input.

```
python3 -m tools.lens_correction photo.RAF corrected.jpg
python3 -m tools.lens_correction photo.jpg corrected.jpg --lens "XF10-24mmF4 R OIS" --focal-length 10 --aperture 8
```

If the camera or lens isn't in the database, or the matched lens profile has no distortion calibration data, the tool fails loudly (`camera_not_found` / `lens_not_found` / `no_distortion_data`) instead of silently passing the image through uncorrected - see `../core/lens_correction.py`'s `correct_from_exif()`. Vignetting and chromatic-aberration correction are out of scope for now (only `ModifyFlags.DISTORTION` is applied).

`resolve_lens_params()` in this file (EXIF read + override merge, `--make`/`--model`/`--lens`/`--focal-length`/`--aperture`) is shared with `raw_pipeline.py`'s `--lens-correct` above, so both CLIs resolve missing/incorrect EXIF the same way.

## Photoshop / DaVinci Resolve preset export (.cube LUT)

Bakes any of the `apply_*` brand/film-simulation functions already registered in `../hybrid_engine/core/preset_inverse.py`'s `TARGET_FUNCS` registry into a standard Adobe `.cube` 3D LUT file (`../core/lut_export.py`). Unlike a parametric ACR/`.xmp` preset, a `.cube` file just stores "input color -> output color" - it doesn't matter whether the source function's internals are an HSV rotation, a Lab curve, or CLAHE, so it can carry over a brand's look exactly as-is. Photoshop's Color Lookup adjustment layer reads `.cube` directly, and so do DaVinci Resolve, Premiere, and After Effects.

```
python3 -m tools.export_lut --list                            # list all available presets
python3 -m tools.export_lut hasselblad hasselblad.cube
python3 -m tools.export_lut fuji_astia fuji_astia.cube --size 33   # 33 is the Adobe-standard grid size
python3 -m tools.export_lut hasselblad hasselblad.cube --install-lightroom  # also copy into Lightroom/ACR's LUT Profiles folder
```

**Known limitation**: functions built on CLAHE (adaptive local contrast, e.g. `fuji.apply_pro_neg_hi`) produce output that depends on the surrounding pixel distribution, not just the input color alone - a 3D LUT is by definition a context-free per-pixel mapping (same input color always -> same output color), so this local adaptivity can't be represented exactly. `bake_lut_from_function()` passes the entire identity grid through as one synthetic image in a single call, so CLAHE at least produces a stable, grid-structure-dependent result instead of a meaningless per-point one - but the result still won't exactly match applying the same function to a real photo. This is a structural limitation of the `.cube` format itself, not a bug, and is flagged in `../core/lut_export.py`'s module docstring following the project's "unverified/approximate" labeling convention.

**Lightroom Classic / Adobe Camera Raw**: no separate export path needed - since ACR 12.3 / Lightroom Classic 9.3, Adobe reads raw `.cube` files directly out of a fixed "LUT Profiles" folder (`~/Library/Application Support/Adobe/CameraRaw/LUT Profiles` on macOS, `%APPDATA%\Adobe\CameraRaw\LUT Profiles` on Windows) and lists them as Profiles in the Develop module's Profile Browser - unlike Photoshop, which needs a manual Color Lookup adjustment layer. `--install-lightroom` copies the just-baked `.cube` there for you (`--group` picks the Profile Browser subfolder, default `Hncs`); macOS/Windows only, since Adobe's own apps don't ship for Linux.

## DCP camera profile (colorimetric correction, X2D II only)

Where the `.cube` path above is a look layered onto an already-rendered
image, this one goes into the **color-conversion stage right after RAW
demosaic**. It least-squares-fits the 10 contributed X2D II ColorChecker
frames against XYZ(D50) references in camera-native RGB space (via
`decode_raw_native()`, which bypasses both libraw's color matrix and its
white balance), then exports the result as an Adobe `.dcp` profile
(`../core/dcp_export.py`) that Lightroom Classic/Camera Raw reads.

```
python3 -m tools.analyze_camera_native_matrix   # fit + cross-validated comparison against libraw's built-in matrix
```

Measured (patch-mean ΔE00 in XYZ D50): libraw's built-in matrix 7.81
-> chart-fit matrix **2.83** (leave-one-image-out cross-validation),
63.8% better than libraw. Full numbers and caveats in
`../hybrid_engine/EVALUATION.md` ("후속 실측 21").

**Known limitations**: (1) the scene illuminant at capture time is
unrecoverable from this data - the contributed `manifest.csv`'s
`illuminant` column is empty, and since the chart references are
chromatically adapted to D50 before fitting, the resulting matrix is
D50-referenced by construction, so `CalibrationIlluminant1` is set to
**23 (D50)** to match the reference space, not a measured or assumed
scene illuminant; (2) all 10 frames come from a single burst, so there's
only one lighting condition and dual-illuminant interpolation isn't
possible; (3) whether Lightroom actually renders this file as intended
was unverified for a long time (no Adobe software in this project's dev
environment, only TIFF structural validity via exiftool and numeric
round-tripping were checked) - as of 2026-08-31 this is confirmed for
the file-loading step specifically: a real-user test (Chris Schmauch)
found the file wasn't loading in Lightroom, root-caused it to a wrong
header magic number and a wrong `UniqueCameraModel` value, and confirmed
the fix loads correctly - see `../core/dcp_export.py`'s module docstring
for the full story; (4) X2D II 100C only (declared via
`UniqueCameraModel`).

## Brand-signature discriminability check (research)

`classify_brand.py` runs in the opposite direction from this project's other tools - instead of building a new feature, it validates whether the already-computed population signatures for 10 brands (`datasets/<brand>/*_signature.json`, 852 photos total) actually carry enough signal to tell brands apart, via leave-one-out nearest-centroid classification. Distances are standardized (z-score), and the held-out photo is fully excluded from its own brand's centroid on every fold (no leakage). `npix`/`is_portrait`/`quality`/`subsampling` (image size, JPEG encoder settings) are deliberately excluded - keeping them would let the classifier learn "which brand uploads which resolution/JPEG setting" instead of an actual color-rendering difference. `ricoh_gr` is excluded from the classifier entirely: its `color_signature.json` stores `hue_median` instead of `hue_mean` like the other 10 brands (not the same statistic, and not comparable), so it's dropped rather than approximated - see the notice the CLI itself prints on every run. The LOO research validation itself has no predict mode - design rationale in `../docs/superpowers/specs/2026-07-24-brand-classifier-design.md`. (The separate "for fun" predictor - `rank_brands_by_distance()` in `../core/brand_classifier.py` / `classify_brand.py predict` - is described a few paragraphs down and in `../docs/superpowers/specs/2026-07-25-brand-predict-fun-design.md`.)

```
python3 -m tools.classify_brand                # Set A: tone+color+gamut (15-dim)
python3 -m tools.classify_brand --features all  # Set B: + texture (21-dim)
```

- Set A (no texture) - overall accuracy: `0.196`, macro accuracy: `0.232`
  (majority baseline `0.146`, uniform baseline `0.100` (1/10))
- Set B (with texture) - overall accuracy: `0.498`, macro accuracy: `0.490`

Texture's sharpening/micro_contrast use different formulas per brand (documented in `../docs/project_structure.en.md` - Canon/Sony vs. Nikon/Leica/Pentax/Ricoh GR are on different scales), so if Set B scores higher than Set A, this result alone can't separate "genuine color difference" from "which formula was used." `leica` (45)/`pentax` (40)/`phaseone` (16) have thin samples, so those brands' recall figures are especially noisy.

**And for fun**: a `predict` subcommand built on top of the same validated tool - feed it any photo and it ranks which of the 10 brands' centroids it lands closest to, by distance. Texture is left out (Set A only, tone+color+gamut) - the same caveat as above, since texture's per-brand formulas can't be reconstructed for a new photo. Since measured accuracy is only 19.6%, it never shows a fabricated confidence number (no "87% Sony") - just the distance ranking, with that accuracy figure always printed alongside both the console and HTML output.

```
python3 -m tools.classify_brand predict photo.jpg
python3 -m tools.classify_brand predict photo.jpg --html result.html  # self-contained static HTML with the photo embedded as base64
```

## Video engine (frame-by-frame, engineering reuse - not a new measurement)

`video_engine.py` applies an already-measured brand look to an actual video file (mp4), frame by frame - it does not add any new color-science measurement. 21 brands are supported: the 10 population-fit brands' measured tone-curve parameters (Canon/Leica/Nikon/Olympus/Panasonic/Pentax/Phase One/Ricoh GR/Sigma/Sony), plus Fujifilm's 10 film-simulation presets and Hasselblad's `apply_hncs` (`fuji_astia`/`fuji_pro_neg_std`/`fuji_pro_neg_hi`/`fuji_eterna_cinema`/`fuji_eterna_bleach_bypass`/`fuji_nostalgic_neg`/`fuji_reala_ace`/`fuji_classic_negative`/`fuji_acros`/`fuji_monochrome`/`hasselblad`) - see [docs/superpowers/specs/2026-07-26-video-engine-fuji-hasselblad-design.md](../docs/superpowers/specs/2026-07-26-video-engine-fuji-hasselblad-design.md) for which presets needed a CLAHE-free variant and which didn't.

```
python3 -m tools.video_engine input.mp4 output.mp4 --brand canon
```

**Known limitations**: (1) audio is preserved by default via a lossless remux step (`imageio-ffmpeg`'s bundled static ffmpeg binary, `-c:v copy -c:a copy` - no re-encoding, first audio track only, no opt-out flag), and a remux failure aborts the whole run rather than falling back to a silent video; (2) for the 10 population-fit brands plus `fuji_pro_neg_hi` and `hasselblad` - the only 12 of 21 brands whose photo-mode `apply_*` actually uses CLAHE - the video path skips CLAHE (per-frame adaptive local-contrast correction) to avoid inter-frame flicker, so its output is not identical to the photo-mode look; the other 9 Fuji film-simulation presets never used CLAHE in the first place, so their video-mode output is applied unmodified from photo mode (the only difference is lossy video-codec compression); (3) this is not a video-specific color-science measurement - whether a camera brand actually renders video differently from its still JPEGs (different tone curve, sharpening, etc.) is unverified; (4) only validated against synthetic test video in this environment - no real camera mp4/mov sample was available for a smoke test.

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

Reproducing `evaluate_darktable_vs_rawpy.py` (a research-only
RAW-decoder comparison experiment) requires `darktable-cli` installed on
the system (`apt-get install darktable` or your distro's equivalent - a
separate system package not covered by Python's `requirements.txt`). No
other tool here requires darktable.
