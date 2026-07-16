# Methodology / Verification Log

*[한국어](methodology.md)*

Back to the [main README](../README.md).

## Image trustworthiness policy (2026-07~)

We found that imaging-resource.com's media CDN stores genuinely corrupted originals across several camera review galleries (72% of the Hasselblad X2D 100C gallery, 100% of the Phase One XF 100MP gallery, 40% of the Pentax 645Z/K-1 galleries had decoding stop partway through with the rest saved as blank rows - repeated re-downloads via different methods reproduced the exact same result, confirming this is a defect in the files as stored on the site, not a transfer issue). `cv2.imread()` silently "succeeds" on these files too, only printing a "Premature end of JPEG file" warning and filling the rest with black pixels - load success or shape alone can't filter these out.

**So from this point on, every population analysis only uses images that pass `core/validation.py`'s `is_image_usable()`** (which judges corruption via row-wise standard deviation). This is already applied across every download path in `tools/analyze.py` (Hasselblad's official CDN + the 4 imaging-resource.com brands) and `tools/download.py`'s Fuji Google Drive download path (`download_fuji_pairs()`), so newly scraped images are automatically filtered going forward.

Re-verifying all previously committed/cached population data:
  - Leica (45 photos), Fuji (mirrorlesscomparison.com, 40 JPEGs across 10 bodies): 0 corrupted - no change in numbers
  - Ricoh GR: the existing 40 photos (GR III+IIIx) had 0 corrupted. Later expanded to n=80 by finding additional GR/GR II galleries (GR II's HDR on/off comparison shots were filtered out) - replaced with the re-verified numbers
  - Pentax (16 of 40 corrupted): re-collected to keep n=40, replaced with re-verified numbers
  - Phase One (all 30 of 30 corrupted): re-collected from the whole gallery (110 candidates), but 91 of those were also corrupted, shrinking to n=16 - replaced with re-verified numbers (also tried the Phase One XT gallery to expand the sample, but the surviving images were all shot on a color-less Achromatic back, unusable for a color population, so it was excluded)
See each brand file's docstring for exact numbers.

**Hasselblad X2D 100C gallery follow-up (2026-07) - final verdict: unusable.**
The "72% corrupted" figure above never got a documented follow-up
conclusion, so we actually ran it through `run_imaging_resource_brand()`
in `tools.analyze`. Of the 45 non-"-MOD" (unedited) candidates, both the
original and scaled versions were tried for every one - 44 came back
corrupted ("Premature end of JPEG file"), and the remaining 1 failed the
expected-renderer EXIF check - **zero survivors**. Re-downloading the
same URLs via both curl and Python's urllib produced byte-identical
corrupted files, confirming this is not a bug in our download pipeline
but genuine corruption in the files as stored on imaging-resource.com's
CDN (the same character of failure as the Phase One XF 100MP gallery's
100% corruption). As with Phase One XT, this was left out of
`BRAND_CONFIGS` and only documented as a code comment in
`tools/analyze.py` - Hasselblad's official 124-photo `cdn.hasselblad.com`
set remains the best available source.

## Brand-function QA verification (2026-07)

After adding Canon/Sony/Nikon, ran every `apply_*` function in `brands/*.py` (4 Hasselblad variants + 10 Fuji presets + 7 population-fit brands (Leica/Phase One/Pentax/Ricoh GR/Canon/Sony/Nikon), 21 total) on a random BGR array and confirmed shape/dtype are preserved. Everything works correctly - no bugs found
(note: `apply_acros`/`apply_monochrome` return single-channel grayscale by design and need separate handling in shape comparisons; `apply_highlight_rolloff`/`apply_lut`, re-exported into `fuji.py` from `core.curve`/`core.lut`, are general-purpose helpers rather than brand presets and are out of scope for this test). This started as a manual smoke test and was later formalized into `tests/test_brands.py` - in the process, discovered the README had been incorrectly stating the Fuji preset count as 9 and corrected it to 10 (the code itself was already correct; only the docs were stale).

Canon/Sony/Nikon were also extended with the same pixel-level 5-part signature analysis (tone/color/texture/gamut/joint_distribution) as the other 5 brands (`datasets/canon,sony,nikon/`) - in the process, 3 parallel agents each independently guessed the sharpening/micro_contrast formulas and the scales drifted, so Sony was recomputed and a Canon/Sony-vs-Nikon micro_contrast non-comparability caveat was left in place (see each brand's docstring). Also investigated whether these three brands could be upgraded to raw-baseline calibration (Hasselblad-grade) via a raw+jpeg pair source, but concluded it's not possible on either mirrorlesscomparison.com (no actual pairing) or imaging-resource.com (raw download links are dead) - kept the population-fit approach.

## Population-statistics reproducibility audit (2026-07)

For all 10 population-fit brands out of the 12 total (leica/phaseone/pentax/ricoh_gr/canon/sony/nikon/panasonic/olympus/sigma), fully re-verified whether the population numbers documented in each brand's docstring still reproduce from scratch using the currently locally cached images, via `core.stats.image_stats()` (834 cached files total, integrity re-confirmed with `is_image_array_usable()` - 0 corruption). Result: **10/10 matched**, zero real discrepancies. Sigma's re-implemented burst-deduplication logic reproduced a false positive already documented in `brands/sigma.py` (mistaking two photos with different filename prefixes but coincidentally close frame numbers for the same scene - "YC-78.jpg" vs "YSDIM0080.jpg"), but this was traced to the audit script not re-implementing the original collection script's prefix-matching refinement, not a problem with the actual committed data. The `_TOE_LIFT`/`_WHITE_POINT` constants also matched each docstring's final adopted values exactly across all 10 brands.
