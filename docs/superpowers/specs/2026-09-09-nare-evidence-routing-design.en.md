# NARE amendment: measurements and claims by data type

[한국어](2026-09-09-nare-evidence-routing-design.md)

Status: methodology design for review; these contracts are not yet implemented
in validators. This preserves the [NARE](2026-09-08-nare-natural-scene-protocol.en.md)
appearance criteria and defines what incomplete local data can establish.

## Decision and measurement paths

Of relaxing NARE, replacing it, or preserving it with separate auxiliary paths,
choose the third. Relaxation turns missing targets into evidence; replacement
duplicates existing regression coverage. Inspecting twelve brands and measuring
appearance for twelve brands are separate completion criteria. Missing ΔE00 is null.

| Path | Inputs | Permitted result | NARE appearance status |
|---|---|---|---|
| NARE | Same-capture RAW and confirmed SOOC JPEG with confirmed style | Fixed candidate reconstruction error | Promotion requires existing gates and receipts |
| Preview comparison | RAW and its extracted embedded preview | Error against that preview | Exploratory ceiling; cannot substitute for SOOC |
| Colorimetric | Chart RAW and valid chart reference/ROI | Chart colorimetric error | Separate claim; no NARE promotion |
| Diagnostic | Pair with uncertain target provenance/style, or standalone image | Descriptive pair error or execution status | Exploratory ceiling; no target means no ΔE00 |

Preview comparison requires successful extraction and verified color space and
resolution. Record missing, low-resolution or unknown-color-space previews as
exclusions. A decoder-generated JPEG is not an independent manufacturer target.
Never pool averages across paths.

## Identity and provenance

Scan all declared local roots and record access failures. A repository dataset
scan cannot establish that the entire computer lacks files. SHA-256 detects
identical bytes; different encodings/crops need duplicate-candidate review.
Renaming cannot create another capture.

capture_id denotes a verified pair identity; scene_id denotes a reviewed physical
scene group. Sequential identifiers are record_id only. EXIF time/model/ISO matches
support pairing candidates, not SOOC authentication. Store evidence and review
state for scene, session, contributor, lighting and style. Do not treat LOCAL_SOOC,
folder names or generic natural_scene labels as verified metadata.

Preserve target_kind, original hashes, preview extraction command/version, decoder
version/options, color handling, candidate function/commit/config, split and
artifact hashes. Receipts bind execution to inputs; they do not authenticate scene
independence or whether data represents reality.

## Comparisons and measurement

Freeze evaluation cells `(brand, body/model, target_kind, style, candidate, scale)`
and exclusions before execution. Select candidates from an explicit registry;
reject NARE style mismatches. Body-specific and generic brand looks are distinct
candidates. B0 is a fixed RAW decoder; B1 is a separate foundation only when one
exists; C is the actual appearance transform. An identity candidate is a baseline
execution check. Identity B1 cannot establish sensor-correction contribution.
Separate fitting and evaluation by scene/session; do not tune thresholds on results.

Freeze color-space/ICC/transfer-function/white-point handling before registration
and overlap/exclusion masks. Use identical geometry and masks for B0/B1/C. Do not
realign or select pixels to favor a candidate. Record clipping, shadow, highlight
denominators and exclusions. Registration failures retain null metrics and reasons.

512px is an exploratory execution scale. Performance conclusions require at least
two prespecified scales; 1024px/2048px do not imply native resolution. Report both
the common valid capture set across scales and each scale's complete pass set to
expose selection effects.

## Statistics and claims

Before reviewing scene groups, report n_captures and descriptive capture-level
mean/median/p90 only. Do not claim independent scenes, bootstrap confidence,
sign-test significance or generalization from registration success counts.

After group review, average images within scenes and weight scenes equally.
Compute B0-C paired scene differences with 20,000 bootstrap draws (seed=0), exact
sign tests and drop-one sensitivity. If sessions induce dependence, also report
session-cluster analysis; scene-only intervals are insufficient. Prespecify holdout
and multiple-comparison policies when selecting among candidates.

Raw ΔE00 rankings across brands photographing different scenes are not quality
rankings. Report within-brand paired improvements and observed coverage. Direct
cross-camera comparison requires Protocol 2R same-physical-scene conditions.

Preserve existing NARE sample-size, improvement, CI/sign-test, subgroup, coverage,
control and provenance gates. Supported requires a reproducible full hash chain
and actual evaluator execution. Verified additionally requires a separate trusted
runner signature and replay; do not issue it where that path is unimplemented.

## Accounting and reproduction

Keep stage denominators separate: discovered files → capture candidates → eligible
pairing/provenance → decoded → registered → evaluation eligible → reviewed scenes.
At each stage classify a capture as passing or one primary failure, with secondary
reasons in a separate array. Never add file, pair and scene counts together.

Persist a run bundle containing inventory, pair/scene manifests, per-capture and
per-scene metrics, failures, configuration/environment, executable command/code,
receipt and summary. A summary relying solely on /tmp is not durable evidence.
Every brand gets a result or precise nonmeasurement reason; missing is never pass.

## Correction and implementation acceptance

The 2026-09-09 local audit's Fuji 207, Hasselblad 17 and Leica 15 passing records
are capture records, not established independent scenes. Their identity-candidate
means describe decoder-to-selected-JPEG differences, not HNCS appearance
performance. LOCAL_SOOC and invented metadata do not establish NARE eligibility.
Sony failures describe this environment and input set, not universal impossibility.

Future regression coverage must reject unknown-style promotion, preview-to-SOOC
promotion, renamed duplicates, inference from unreviewed scenes, appearance gains
claimed for identity candidates, numeric ΔE00 without targets, broken failure
accounting, candidate/style mismatches and receipt artifact tampering. Also verify
that baseline and candidate share geometry and masks.
