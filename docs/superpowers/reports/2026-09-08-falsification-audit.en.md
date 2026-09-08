# HNCS falsification audit — 2026-09-08

[한국어](2026-09-08-falsification-audit.md)

> **Correction (2026-09-08, Part 1 re-audit)**: The first repairs were incomplete.
> Fresh report-path bypasses still reached Supported/Verified. See the
> [re-audit](2026-09-08-part1-reaudit.en.md) for reproduced defects, repairs,
> regression tests and the remaining evidence-authenticity boundary.

Target: develop 43c5ee8d4acdd1883a64356063dc93b557884b47; local Python 3.12 venv.
Verdict: basic rendering works, but the current NARE Supported/ship decision is not reliable enough
to authorize release. This audit records counterexamples without changing production behavior.

## Verified baseline

- Full unittest discovery: 1396 tests, 23.259 seconds, OK.
- Driver smoke: 6 pass / 0 fail.
- 56 shipped photo looks × black, white and seeded random 32×32 uint8 images:
  168 shape/dtype/finiteness checks passed. These checks do not establish photographic accuracy.
  Hasselblad night emits a divide-by-zero warning on white input but returns valid output.
- The registered GFX100RF manifest's 37 RAWs and 37 JPEGs: 74/74 SHA-256 matches;
  no missing files or mismatches.
- compileall and git diff --check passed.
- Repository integrity audit: exit 1, two missing tool-index entries; 13 DCP and 73 ICC
  structural checks passed.
- Optional darktable-cli, population downloaded_samples and the old raw_calib_cache_fuji
  are absent.

## Reproduced defects

### F1 — P1: invalid registration can become Supported

hybrid_engine/evaluation/nare.py:66–68 checks only the presence of correlation and overlap keys.
With correlation=-1 and overlap=0, registration_passed remains True; otherwise qualifying data
receives ship_gate_passed=True and classification=Supported. Failure status and displacement are
not checked. The RAW runner enforces thresholds, but the recorded-metrics evaluator/CLI does not.
Required repair: validate finite values, ranges, frozen thresholds, displacement and explicit failures
when producing reports.

### F2 — P1: discovery coverage can satisfy evaluation diversity

nare.py:48,81 uses the entire manifest summary. Evaluation data containing only daylight/landscape
passes the three-lighting/three-category gate after adding two discovery-only labels.
The result becomes Supported even though these conditions were never evaluated.
Required repair: derive coverage and picture styles only from scenes actually evaluated.

### F3 — P1: duplicate scene measurements are overwritten, not aggregated

The dictionary at nare.py:52 silently keeps the last metric for each scene_id.
Start with 12 scenes whose candidate errors are 5, then append a repeat for scene 0 with error 100:
mean_candidate becomes 12.916666666666666. Put the repeat first and the mean is 5.0.
Ordering identical observations changes the conclusion. EAGER aggregation cannot recover rows already
discarded. Subgroups still consume all original rows, so their weighting differs from global metrics.
Required repair: separate image and scene IDs and aggregate repeated measurements, or explicitly
reject duplicate scene rows.

### F4 — P1: catastrophic subgroup gate accepts 0→100 and NaN

nare.py:111–126 does not reject nonfinite/negative metrics and assigns zero improvement when the
baseline is zero. All semantic errors can rise from 0 to 100 with passed=True. NaN candidates
also pass. Required repair: finite/nonnegative validation and explicit zero-baseline regression
rules with preregistered tolerances.

### F5 — P1: fitting lacks lockbox, duplicate-scene and hash guards

tools/fuji/fit_nare_provia_session_holdout.py:27–59 loads the full manifest and splits only by session.
A control-flow probe mocks loading/scoring, supplies the same scene ID under three sessions with
split=lockbox, and obtains 3 scenes/3 sessions; two lockbox rows enter training in every fold.
This proves missing input guards, not a real RAW fit. The code also omits frozen hash verification.
The actual 37-row manifest uses evaluation and its hashes matched this audit; this is not evidence
that the current files were corrupted or that a real lockbox was consumed.
Required repair: validate permitted fitting splits, scene/session consistency, hashes and Picture Style
before decoding, and preserve a separate final lockbox.

### F6 — P2: Layer A + appearance is not composed

hybrid_engine/evaluation/nare_runner.py:85–86 calls foundation(neutral) and candidate(neutral)
separately. A nonidentity foundation is never passed into the candidate.
Without an explicit full-pipeline candidate contract, this cannot establish the incremental effect
of Layer A plus appearance. Current identity-B1 results are unaffected.
Required repair: define whether candidate means a complete pipeline or an appearance-only transform,
and test the actual composition.

### F7 — P2: the latest Korean reproduction command fails

hybrid_engine/EVALUATION.md:5050 supplies --candidate provia, which the fit CLI does not accept.
Reproduction exits 2 with unrecognized arguments: --candidate provia.
The English report omits the option and does not share this defect.
Required repair: reconcile the Korean command with --help and smoke-test documented CLI syntax.

### F8 — P2: the preceding documentation-completion claim was unsupported

The new fitting tool is missing from both project_structure indexes, causing two integrity failures.
A recursive docs scan finds 49 documents without a matching .en.md filename; the new English fit
report lacks its Korean filename counterpart. This is a filename-pair count, not proof that every
one of those 49 documents contains Korean text. The integrity tool checks only 16 top-level docs
and misses nested superpowers omissions.
Required repair: recursively inventory pairs and inspect content language before claiming completion.

## Limits of the scientific claims

- There are 37 unique RAW hashes, but that does not prove 37 independent physical scenes.
  The manifest uses sequential gfx100rf IDs, capture-date sessions, and only daylight/natural_scene
  labels. Physical-scene grouping and strata need independent verification.
- Ten of eleven held-out sessions choose the existing parameters and show exactly zero change.
  All 17 frames with nonzero differences belong to capture-2025-03-18. The 7 wins/10 losses and
  scene bootstrap must not be read as replication across independent sessions. The inconclusive/
  negative conclusion remains appropriate; session dependence and overlapping CV training sets
  require further uncertainty analysis.
- The NARE runner produces mean ΔE00, not semantic masks or spatial metrics, and does not combine
  multiple scales into an enforced gate. Boolean controls/provenance are attestations rather than
  independent verification of evidence.
- Population JPEG distributions cannot separate photographer, scene and exposure effects from
  manufacturer rendering. core/engine.py and brands/README.md already acknowledge this;
  successful execution does not resolve it.
- The Hasselblad shipped docstring records both historical edited targets (9/13 pairs) and later
  refitting on 65 pairs. It would be unjustified to dismiss all current coefficients solely because
  of the earlier contamination. This audit did not rerender the entire 65-pair corpus or regroup
  its physical scenes, and does not certify Hasselblad appearance under NARE.
- CLAHE non-equivalence in LUT export and the inability to invert local contrast are documented
  limitations. Adobe application profile import, exhaustive GUI interaction, long video runs,
  Linux CI execution and colorimetric accuracy of every body/profile were not validated.
  Profile structural validity is distinct from color accuracy.

## Reproduction

From the repository root:

~~~bash
PYTHONPATH=. ~/.hncs-hybrid-venv312/bin/python3 docs/superpowers/reports/2026-09-08-falsification-probes.py
~/.hncs-hybrid-venv312/bin/python3 -m unittest discover -s tests
~/.hncs-hybrid-venv312/bin/python3 .claude/skills/run-hncs/driver.py smoke
~/.hncs-hybrid-venv312/bin/python3 -m tools.maintenance.audit_repo_integrity
~~~

The probe prints observations as JSON, including synthetic/mock counterexamples, 168 renderer
contract checks, nonzero sessions from the recorded fit, and documentation filename pairs.
It does not raise merely because a counterexample is found and does not rerun RAW fitting.

Priority: close F1–F5 acceptance/leakage defects, reclassify recorded artifacts, clarify F6 pipeline
composition, repair documentation reproduction/pairs, then gather independent scene, lighting,
semantic and spatial evidence. No shipped look was modified and no new accuracy gain is claimed.

> **Correction (2026-09-08, F1–F7 repairs)**: The counterexamples are now fixed by regression
> tests and guards for registration ranges/finiteness, evaluation-only coverage, duplicate scene
> IDs, semantic zero-baseline/NaN values, foundation-to-candidate composition, and session-holdout
> evaluation split/SHA-256/Provia validation. The Korean fit command's `--candidate provia` option
> is now accepted. The recorded 37-scene fit was replayed through the new input-validation path;
> the JSON was byte-identical and retained improvement **-0.06342050230067402%**, CI
> **[-0.02051282700178119, +0.00462789732822533]**, wins/losses **7/10**, and p
> **0.629058837890625**. The original findings remain in the report.
