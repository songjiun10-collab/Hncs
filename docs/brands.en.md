# Per-Brand Detailed Methodology

*[한국어](brands.md)*

Back to the [main README](../README.md).

Detailed notes for the 5 population-fit brands (Fujifilm/Leica/Phase
One/Pentax/Ricoh GR) whose collection approach differed enough brand to
brand to be worth writing up separately. Canon/Sony/Nikon/Panasonic/
Olympus/Sigma follow nearly identical methodology (imaging-resource.com
population + the 5-part signature analysis) and are documented only in
each `brands/*.py` docstring.

## Fujifilm (`brands/fuji.py`)

Fuji has multiple built-in film-simulation presets (Provia/Astia/Velvia/Classic Chrome/Pro Neg Std, etc.), so a different verification method was used than for Hasselblad: gather genuinely unedited SOOC JPEGs from mirrorlesscomparison.com review galleries, and compare population statistics grouped by the actual Film Mode tag read via exiftool, to confirm each preset moves saturation/tone in the same direction as the real measurements (`tools/analyze.py fuji_film_modes`).

- Tried to find same-photo raw+jpeg pairs (`tools/download.py fuji-pairs`), but this site's "RAW samples" and "SOOC JPG samples" folders were never actually paired by shoot to begin with - just separate photos each - across 10 cameras, 57 RAW + 40 JPEG downloads yielded only 3 pairs whose EXIF capture time matched exactly (and even those were all Provia). Abandoned raw-based calibration (Hasselblad v10-v12 grade) in favor of population comparison.
- Comparing measured direction (n=8-15) against applying `apply_astia`/`apply_pro_neg_std` to Provia photos, both moved saturation in the opposite direction from the real measurement (Astia measured -12.9 vs. preset +9.4; Pro Neg Std measured -19.4 vs. preset +11.3). The cause was applying the tone curve to each BGR channel individually, letting the gap between channels widen and saturation re-rise (original 125.0 → 109.4 after HSV desaturation → 139.7 after the per-BGR-channel curve, higher than the original). Fixed both presets to apply the curve only on the Lab L channel.
- Pro Neg Std was still moving the wrong direction even after switching to the L channel - it turned out the curve shape itself was wrong. The old version used a contrast-boosting S-curve (n=1.4), but the real measurement showed Pro Neg Std actually has a flatter profile with lower contrast than Provia (black-p2 +2.7, white-p99.5 -19.0). Replaced with a contrast-reducing curve (n=0.65).
- Re-verification after the fix: Astia went from 1/3 to 2/3 direction matches; Pro Neg Std went from 0/3 to 3/3.
- **(2026-08 update)** Retried the raw+jpeg calibration abandoned above once genuinely paired GFX100RF/X-T30 III raw+jpeg pairs (matching capture timestamps) landed in the local library - both used Provia, which had no matching preset, so a new `apply_provia()` was built from a direct ΔE00 grid search against raw (native-pixel improvement: GFX100RF +18.8% / X-T30 III +23.7%). See [measurements.en.md](measurements.en.md#apply_provia-added---fuji-gfx100rfx-t30-iii-rawjpeg-pairs-found-2026-08) for details.

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
