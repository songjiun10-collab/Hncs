# External Source Analysis: HNCS/Phocus (blog.tonalphoto.com + Luminous Landscape forum)

*[한국어](hncs_external_sources_analysis.md)*

Back to the [main README](../README.md).

This session gathered 17 external documents (16 blog posts + 1 forum
thread) about Hasselblad's Phocus and HNCS. This note has two goals:
(1) collect the most credible external information about "real HNCS"
in one place, and (2) cross-check it honestly against the three
measured experiments run this session (hard-cluster structural
experiment, chromatic-aberration correction experiment, illuminant
blend experiment) — what got confirmed, and what didn't.

## Sources and credibility

**The author is an actual contributor to this project.** blog.tonalphoto.com's
author, Konrad Michels, is the same contributor behind
`datasets/hasselblad/contributed/kmichels-x2dii-2026-07/` (X2D II
ColorChecker data submitted via GitHub issue #4, already folded into
`hasselblad.json` v1.3). This isn't a coincidental find — it's a
follow-up public writeup from someone actually connected to this
project.

As the author states in every post, these are **personal exploration
and testing, not official Hasselblad technical support or guidance**.
Methodology is transparent (tools, software versions, raw data
disclosed) and there's a documented self-correction history (a
`.phos` preset-persistence claim corrected 2026-05-04), so credibility
isn't low — but it's still reverse-engineering, not
Hasselblad-confirmed fact.

**The Luminous Landscape forum thread** ("Hasselblad Natural Color
Solution (HNCS) - how it works (probably)", author unknown, community
technical analysis) is one notch less reliable — the title itself
says "probably," and it's inferred from circumstantial observation on
an H4D-50 ("same profile, but both tungsten and daylight look good").
Still, the blog author cites this thread and confirms it matches their
own Phocus 4.x measurements, and this project independently judged
the thread's core claim (multiple illuminants, auto-selected and
blended) physically plausible enough to run an actual experiment
against it.

## 1. HNCS mechanism — the most important finding

**Source**: `hasselblad-hncs-color-science-explained` (blog,
2026-07-18) + the Luminous Landscape forum thread.

### 1-1. Render-time, not capture-time

HNCS is not baked into the RAW file. The 3FR is pure sensor data;
HNCS is a render pipeline Phocus re-runs **every time it opens the
file**. Changing white balance makes Phocus re-select the color
matrix and chroma LUT and re-render from scratch — this is why the
same numeric Kelvin value applied later in Lightroom/Capture One
produces different color (those tools just multiply an already-decoded
image; Phocus picks an entirely different matrix).

**Relation to this project**: this matches, exactly, the structure
`hybrid_engine/research/hncs_structural.py` already assumed from the
start (illuminant-specific matrix → illuminant-specific chroma LUT →
shared film curve). The "real 4-stage HNCS structure" hypothesis this
project set up early in the session is independently re-confirmed by
an external source.

### 1-2. Illuminant count: at least 4, we approximate with 2

The forum thread's specific numbers: **Tungsten (~2950K), Low
Tungsten (~2100K), Flash (~5650K), Flash-Daylight** — at least 4
illuminants, each with its own 3x3 matrix. Chroma-correction LUTs
exist only for Tungsten and Flash ("too similar" for Low-Tungsten /
Flash-Daylight to need separate tables), and each of those two LUT
sets has two variants: "Standard" (more subjective punch) and
"Reproduction" (accuracy-tuned).

Matrix and LUT are auto-selected by the white-balance setting, and
**intermediate values are blended** — the same way Lightroom's
dual-illuminant DCP works, just with more illuminants.

**Relation to this project**: `hncs_structural.py`'s hard-cluster
model doubly simplifies this — 2 clusters instead of 4 illuminants,
hard classification (`CLUSTER_THRESHOLD_R_OVER_B = 0.9`) instead of
blending. This session directly tested the second simplification
(blend vs. hard-classify, see section 3 below); blending did not beat
hard classification on our 13 pairs. The first simplification (2 vs.
4) was never even attempted, due to sample size.

### 1-3. Presets (Standard/Nature/Portrait/Product/Square Crop) are color-independent

**Source**: `what-phocus-writes-to-phos-hncs-presets` (blog,
2026-05-05, measured by diffing `.phos` sidecar files directly).

The only differences between presets are **sharpening parameters
(USMAmount/USMRadius/USMNoiseLimit) and the tone curve
(Gradations)**. Brightness/Contrast/Saturation are identical (0/0/0)
across all 5 presets, and the author states no separate color matrix
was found anywhere in the file format. Nature's "punchier" look comes
from an S-curve (shadows crushed, highlights lifted) plus 1.8x the
sharpening of Standard — not a saturation change.

**Relation to this project**: this re-confirms a scoping decision this
project already made correctly — neither `apply_hncs()` nor the
structural experiments model "presets" at all, treating HNCS as a
single render pipeline. That was the right scope: presets are a
post-processing layer on top of HNCS, not part of the color-science
layer itself.

## 2. Measured Phocus vs. Capture One vs. Lightroom comparison

**Source**: `phocus-capture-one-lightroom-raw-color-test` (blog, data
page) + `phocus-capture-one-lightroom-hasselblad-measured` (narrative
version of the same data). Printed color chart + ISO ladder, X2D II
100C, all three apps at defaults, measured in CIELAB (D65, Bradford),
with an adversarial verification pass (round-trip error 0.007 L*).

| Comparison | Tone | Color |
|---|---|---|
| Capture One vs. Phocus | consistently 5.4-6.8 L* darker across all ISOs (~0.4-0.5 stops) | blue chroma +18.9 to +27.7 C* (largest measured difference), cyan rotated 11-17° toward blue |
| Lightroom vs. Phocus | matches through ISO 800, then brightens (+6.7 L* at ISO 12800) | yellow-cyan pastels -4 to -9 C*, highlights cooler (b* -6 to -7) |

Overall CIEDE2000 median: Capture One 4.0, Lightroom 2.4 (perceptibility
threshold is roughly 1.0-2.3).

**Important caveat (stated by the author)**: this data cannot answer
"which app is most accurate" — it's a printed chart, not a real scene,
and ink reflectance spectra interact with each app's camera profile
differently than natural spectra. Direction is trustworthy; exact
magnitudes shouldn't be carried over to real scenes (sky, water) as-is.

**Lens correction difference** (same author, measured corner falloff
compensation): Lightroom +23.1 L*, Capture One (default Light
Falloff=100) +20.9 L*, **Phocus only +8.1 L*** — both third-party apps
flatten vignetting almost completely; Phocus compensates about a third
as much and leaves visible natural corner darkening.

**Relation to this project**: the corner-falloff finding independently
confirms the HNCS design philosophy already documented in `brands/hasselblad.py`'s
docstring ("the eye perceives contrast, not accuracy" / "respect the
lens's natural character").

## 3. Cross-checking against our three internal experiments

This session ran three experiments, each using the same honest
statistical methodology (LOO cross-validation + sign test + bootstrap
CI + drop-one sensitivity, all recorded in `hybrid_engine/EVALUATION.md`).
**All three landed on "inconclusive" or "flat null"** — this is
probably not a coincidence but a fundamental limit of the 13-pair
sample size.

### 3-1. Hard-cluster structural experiment (run before this external research)

Mirrored `apply_hncs()`'s 3-stage simplification against the real
HNCS's 4 stages (matrix → chroma LUT → film curve, with the first two
split by a 2-cluster hard classification on AsShotNeutral R/B ratio).
Result: a 4.1% mean-ΔE improvement that looked real but had a 95%
bootstrap CI of [-15.8%, +22.9%] (straddling zero) and sign-test
p=1.000 (6 wins, 7 losses) — **inconclusive**.

### 3-2. Chromatic aberration correction experiment

First experiment to touch the decode stage itself (rawpy's
`chromatic_aberration` parameter). All 13 LOO folds independently
picked "no correction" as optimal — a completely flat null (sign-test
p=1.000, CI exactly [0.000, 0.000]). The final review ran a positive
control confirming the parameter genuinely does something (94% of
pixels change) — so this is "it works, but doesn't help," not "it's
silently broken."

**Connection to external sources**: `capture-one-hasselblad-raw-support`
states that Capture One's XCD lens-correction profiles always apply
only a "default" correction because 3FR files carry no focus-distance
information. This lines up with our finding — genuine lens CA
correction needs to vary by focus distance, and neither our single
global scalar nor Capture One's distance-generic default profile can
capture a meaningful signal without that missing data. This
observation hasn't yet been folded into the CA experiment's
`EVALUATION.md` write-up — proposed as a follow-up below.

### 3-3. Illuminant blend experiment (run right after this external research)

Took the forum thread's "4 illuminants + blending" hint and, given
sample constraints, kept 2 anchors but replaced hard classification
with **continuous blending**. Tested two weight formulas (R/B linear,
CCT/mired) via LOO. Result: both slightly worse than the hard-cluster
baseline on average (RB -1.6%, CCT -1.4%), both CIs straddle zero —
**inconclusive**, and the two formulas are indistinguishable from each
other too.

The final review re-ran the entire experiment from scratch and
reproduced every number bit-exactly, and directly instrumented the
weighted least-squares fitting to confirm it genuinely uses all 13
pairs correctly — so this is a genuine null, not an implementation bug.

## 4. Overall conclusion

**The structure external sources strongly suggest (continuous blending
across illuminant-specific matrix/LUT pairs, at least 4 illuminants)
was not reproduced or confirmed on our 13-pair dataset.** All three
experiments converge here not because of methodology flaws (the final
review independently re-verified each one) but because of sample
limits:

- **The sample itself is small**: 13 pairs, unevenly split across the
  2 illuminant clusters we do model (10 vs. 3) — splitting into 4
  illuminants was never even attempted, since that would leave
  2-4 images per illuminant.
- **The target isn't real HNCS output**: every experiment in this
  project measures "how close to the camera's built-in JPEG," not
  "how close to Phocus's actual HNCS render" (the camera JPEG goes
  through some render pipeline too, but there's no guarantee it's
  identical to Phocus's HNCS — already documented as a limitation in
  `hncs_structural.py`'s docstring).
- **The CA experiment's "a global scalar carries no signal" result
  points the same direction as an external, independent admission (Capture
  One's missing focus-distance data)** — this might not be a
  coincidence so much as a more general pattern: render-time
  corrections that depend on information absent from camera RAW
  (focus distance, the exact count/identity of illuminants) are hard
  to reproduce precisely from RAW alone.

## 5. Proposed follow-ups (outside this document, needs separate discussion)

1. Add one line to the chromatic-aberration experiment's limitations
   in `hybrid_engine/EVALUATION.md` noting Capture One's admitted lack
   of focus-distance data (small doc addition, doable immediately).
2. Re-request real-photo (not chart) X2D II raw+jpeg pairs on GitHub
   issue #4 — the kmichels blog post mentions an existing real-world
   frame (XCD 90V, ISO 12800). If more real pairs land, both a
   4-illuminant model and the cross-generation pooling re-check
   (issue #4 point 3) become feasible.
3. With all three experiments (hard-cluster / chromatic aberration /
   illuminant blend) converging on "inconclusive," further parametric
   tuning on this same 13-pair set is likely past the point of
   diminishing returns. A different angle — either more data, or an
   entirely different kind of target (e.g. measuring ΔE against an
   actual Phocus HDR TIFF export instead of the camera JPEG, to get
   closer to "real HNCS" as the reference) — may be more productive
   than continuing to tune parameters on the same 13 images.

## 6. Direct inspection of the Phocus 4.1.1 app bundle (2026-08-03)

An attempt at the "entirely different kind of data" direction proposed
in 5-3 above, but aimed at **the Phocus app itself** rather than a
render output. This section's source isn't a blog or forum post but the
actually-installed Phocus 4.1.1 binary (`brew install --cask phocus`) —
a different tier of evidence than the rest of this document (a primary
source), but the method was deliberately limited to reading static
resource files plus `strings`/`otool -L` (no disassembly or
decompilation, out of respect for the license boundary). So this
confirms *that a structure exists*, not the actual matrix/LUT numbers —
see the limitation in 6-2 below.

### 6-1. ICC profiles are unrelated to the HNCS look (negative result)

Directly parsed the raw binary tags (`wtpt`/`rTRC`/`rXYZ`, etc.) of the
8 `.icc` files bundled under
`Contents/Frameworks/HBImageProcessing.framework/Versions/A/Resources/Profiles/`
(`Hasselblad RGB`, `HasselbladLStarRGB`/`v1`, `Hasselblad Rec709`,
`Hasselblad Rec2100PQ`, `Hasselblad Lab`, `Hasselblad Gray`, and the
film-scanning `330Skel 30K75`/`350Skel 30K90`). Results:

- `Hasselblad RGB.icc`: pure gamma 2.1992, wtpt ≈ D50 (0.964, 1.0, 0.825)
- `Hasselblad Rec709.icc`: pure gamma 1.9609, wtpt ≈ D65
- `HasselbladLStarRGB(v1).icc`: TRC is a 700-point LUT (shaped like the
  CIE L* curve) — the same idea as ProPhoto's L* variant

All of these are **generic color-management working spaces** (the same
concept as ProPhoto RGB), not the HNCS look itself — not "render this
photo with this tone/color." `Settings/Standard/Standard.xml` (the
default preset) confirms the same thing from another angle: its
`ColorCorr` array is all zeros — the preset only carries neutral
adjustment deltas, the base look isn't stored there at all (consistent
with section 1-3's finding that presets differ only in sharpening +
tone curve, never color — it's now clearer *why*: the preset XML was
never the place color logic could live).

### 6-2. Binary strings confirm the "per-illuminant matrix + LUT" structure from section 1-2

Running `strings -a` against `HBRawCorrections.framework` (1.2MB) and
grepping for related format strings surfaced the following
symbol/format-string names (they look like debug/code-dump templates
using `%s`/`%.1ff` placeholders — the actual per-camera numeric values
live in the compiled data section and don't show up as text):

```
kMatrixFlash, kMatrixTungsten, kMatrixLowTungsten          # per-illuminant 3x3 matrices
kLUTTableFlashCb/Cr, kLUTTableTungstenCb/Cr                # per-illuminant Cb/Cr chroma LUTs
kColorTempFlash, kColorTempTungsten, kColorTempLowTungsten # per-illuminant color-temp constants
kNeutralVector                                             # neutral-point vector (appears to be per-illuminant)
```

**Cross-check against section 1-2**: the forum thread claimed "4
illuminants — Tungsten / Low-Tungsten / Flash / Flash-Daylight — each
with its own matrix, and a chroma LUT existing only for Tungsten and
Flash (Low-Tungsten/Flash-Daylight have none)." What this inspection
found matches structurally down to the specific detail of *which*
illuminants have a LUT: **3 matrices (Flash/Tungsten/LowTungsten), but
only 2 LUTs (Flash/Tungsten — no `kLUTTableLowTungsten*`)**. No distinct
name for a 4th illuminant (Daylight/Flash-Daylight) turned up — it may
exist as an unsuffixed "default," under a different naming convention,
or this may just be a limit of string extraction (unconfirmed).

**Limitation**: all the names above are source-level symbols/debug
format strings, not data. The actual 9 floats per 3x3 matrix and the LUT
table values live at specific addresses in the binary's data section,
and reading them requires knowing which address each symbol points to
(i.e. disassembly) — out of scope for this pass (strings/otool only).
Stopped here after checking with the user — going further would cross
into what Phocus's EULA's anti-reverse-engineering clause most likely
prohibits.

### 6-3. Relationship to our project

`apply_hncs()` (v11) is still a **single parametric tone+saturation
curve** with no per-illuminant matrices — this inspection corroborates
section 1-2's external claim that real HNCS has a per-illuminant
matrix + chroma-LUT structure, this time from the actual shipped
binary's internal naming rather than a blogger's inference. That
doesn't mean `apply_hncs()` needs to change, though — there are no
numbers to base such a change on, and even if there were,
`raw_calib_cache`'s 13 pairs have no recorded shooting-illuminant
(color-temperature) label, so a per-illuminant validation isn't
possible either (a follow-up candidate in its own right, outside this
document's scope).

(Same-session follow-up: not a per-illuminant breakdown, but all 13
`raw_calib_cache` pairs were run through real Phocus to compare
`apply_hncs()` directly against a **genuine Phocus render**, not just the
camera JPEG - see `docs/measurements.en.md`'s "First check against a real
Phocus render (2026-08)" section.)

## 7. Reference list

**Directly cited / analyzed in depth**:
- Konrad Michels, "How HNCS Actually Works: Hasselblad's Color Science
  Explained", blog.tonalphoto.com, 2026-07-18
- Konrad Michels, "Phocus, Capture One, or Lightroom for Hasselblad?
  Measured" + data page ("How Phocus, Capture One, and Lightroom
  Render Hasselblad RAW Files"), blog.tonalphoto.com, 2026-07-18
- Konrad Michels, "What Phocus Writes to the .phos When You Switch
  HNCS Presets", blog.tonalphoto.com, 2026-05-05
- Luminous Landscape Forums, "Hasselblad Natural Color Solution
  (HNCS) - how it works (probably)" (forum.luminous-landscape.com,
  topic 96679)
- Hasselblad Phocus 4.1.1 app bundle (Homebrew cask `phocus`, installed
  2026-08-03) — static resource files (`.icc`, `.xml`, `Targets/*.txt`)
  plus `strings -a`/`otool -L` only on `HBRawCorrections.framework`/
  `HBImageProcessing.framework` (no disassembly/decompilation). Primary
  source, see section 6.

**Skimmed, not directly relevant to color science (UI/workflow/separate HDR pipeline)**:
- "Phocus Histogram vs Capture One Levels" (2026-01-10)
- "A Complete Hasselblad RAW Workflow" (2026-07-18)
- "Capture One's Hasselblad Support: What You Get and What Stays in
  Phocus" (2026-07-02)
- "What You Keep and Lose When You Skip Phocus" (2026-07-18)
- "Cull Hasselblad Shoot Fast Before Phocus", "Phocus Thumbnail
  Options Menu", "Phocus Crop Tool Grid Options" (workflow/UI)
- The HDR five-part series ("HNCS HDR", "Output Formats Trilemma",
  "Phocus 4.x HDR Workflow", "HDR Display Requirements", "HDR Print &
  Archival Recommendations") — a separate pipeline layered on top of
  HNCS (gain-map encoding), out of scope for this document.
