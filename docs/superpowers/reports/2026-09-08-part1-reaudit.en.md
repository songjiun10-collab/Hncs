# Part 1 adversarial re-audit — 2026-09-08

[한국어](2026-09-08-part1-reaudit.md) · [Original audit](2026-09-08-falsification-audit.en.md)

Audited baseline: `b9a14043cf49b9b4f113938027cad582d3844c45`, develop.
Verdict: Part 1 was incomplete. Invalid recorded evidence could still become
**Supported** in NARE and **Verified** in EAGER. The reproduced paths below now
reject the input or fail the gate. This is bounded adversarial testing, not a
proof that every possible invalid or fabricated dataset is detectable.

## Every Part 1 fix revisited

| Original finding | Re-audit and resulting repair |
|---|---|
| F1: registration | Finite displacement of 10,000 px still passed; absent displacement/scale and numeric/string failure flags were accepted. Require finite correlation, overlap, both displacements and `long_edge_px`; enforce the existing 5% shift limit and reject explicit failures. Injected NaN/Inf ECC results also escaped the renderer's comparisons; registration now rejects nonfinite ECC results. |
| F2: evaluation coverage | Discovery-only coverage remains blocked. Repeated manifest rows for one scene could instead supply conflicting evaluated labels. Reject conflicting scene metadata, normalize label case/whitespace and exclude unknown placeholders from gate counts. Null metadata is no longer converted to the string `None`. |
| F3: repeated scenes | Duplicate metric rows remain rejected. Identical RAW or JPEG hashes under different scene IDs could manufacture sample size and cross fitting sessions. Reject each such cross-scene hash reuse before evaluation or fitting. |
| F4: subgroup regression | Original NaN and 0→100 cases remain blocked. Finite 1e308→1.7e308 errors overflowed averages and hid catastrophic regression. A divide-first repair then failed a 5e-324→1e-323 underflow test. Use `statistics.mean` for subgroup means; reject empty subgroup contracts and nonfinite thresholds. Zero raw baseline is inconclusive instead of dividing by zero; nonfinite derived foundation improvement raises. |
| F5: fitting boundary | Complete lockbox inputs, duplicate scenes, changed later RAW/JPEG hashes and wrong style all fail before `_load_frame`. Reused content across renamed scenes is now blocked by F3. A synthetic score matrix after real file-hash checks confirms each held-out session is excluded from parameter selection. No new fitting-algorithm change was needed. |
| F6: pipeline composition | An in-place Layer A adds 40 to a neutral value of 40; in-place appearance adds another 40. Actual JPEG decode and ΔE00 measurement give candidate error zero against target 120, with positive ordered B0/B1 errors and unchanged neutral input. Composition survives; no production patch needed. RAW decoding and registration alone are mocked in this test. |
| F7: documented CLI | The `--candidate provia` CLI regression still passes. Fitting is mocked only in the parser/output test; it is not evidence of a RAW fit. |
| F8: documentation | Both new-tool index entries exist and repository integrity passes. The recursive probe still lists **49** missing English filename counterparts. The earlier broad documentation-completion claim remains unsupported; translation completion is not claimed here. |

## Interactions that reached Supported / Verified

- NARE accepted false-valued strings and other truthy non-booleans as controls,
  subgroup approval and provenance. Each gate now requires literal `True`.
- Direct classifiers accepted reversed or nonfinite CI endpoints, negative
  sign-test probabilities and infinite effect sizes. Both now validate the whole
  two-endpoint interval and finite statistical values; NARE also requires an
  integer scene count. EAGER replication/validation/lockbox flags are strict booleans.
- **Four separate EAGER JSON report cases returned Verified** even after the
  direct-classifier repair: robustness `0`, negative neutral candidate error,
  negative chromatic candidate error, and a tier-E manifest with requested tier A.
  Numeric robustness is now invalid; optional errors are validated before
  aggregation; the requested tier cannot exceed the weakest evaluated manifest
  tier. Discovery rows do not determine the evaluated tier.
- Direct paired aggregation also accepted negative optional errors. It now
  validates metric values before repeated observations can average them away.

Positive controls deliberately remain admissible: valid synthetic NARE input
becomes Supported, and valid synthetic EAGER input with all required attestations
becomes Verified. The tests do not obtain safety by making every input fail.

## Evidence and reproduction

The initial 11-test adversarial module produced **46 failing subtests and one
zero-baseline error** before production edits. Follow-up red tests reproduced
four EAGER report promotions, two injected nonfinite ECC cases, the direct paired
negative-error path, and two averaging failures. These are overlapping test
cases, not a count of independent root causes.

From the repository root, using the local Python 3.12 environment:

```bash
~/.hncs-hybrid-venv312/bin/python3 -m unittest tests.test_nare_part1_reaudit tests.test_nare_session_holdout tests.test_nare_runner tests.test_nare_registration tests.test_nare tests.test_nare_cli tests.test_eager
~/.hncs-hybrid-venv312/bin/python3 -m unittest discover -s tests
PYTHONPATH=. ~/.hncs-hybrid-venv312/bin/python3 docs/superpowers/reports/2026-09-08-falsification-probes.py
~/.hncs-hybrid-venv312/bin/python3 .claude/skills/run-hncs/driver.py smoke
~/.hncs-hybrid-venv312/bin/python3 -m tools.maintenance.audit_repo_integrity
git diff --check
```

The adversarial module has 15 tests; additional tests cover fitting, composition
and ECC. The probe now has a passing control, independent discovery fixture
hashes, and a complete lockbox manifest, so an unrelated missing field cannot
masquerade as successful lockbox protection.

Final full discovery: **1,424 tests in 23.041 seconds, OK** (20 new tests above
the 1,404-test Part 1 baseline). `compileall` and `git diff --check` also pass.

## Recorded-data check and compatibility

- The current 37-row Fuji fitting manifest passes all **74/74** frozen RAW/JPEG
  hash checks. This re-audit did not decode/refit the RAW corpus or change fit numbers.
- Recorded 512px and 1024px registered metrics both reclassify as **Inconclusive**
  with 100 bootstrap draws for this gate probe. Diversity, semantic and control
  gates fail; registration also fails because the old diagnostics omit
  `long_edge_px`. Historical artifacts are preserved. Regenerate registration
  diagnostics at the actual evaluated resolution; do not invent a scale to pass.
- The recorded fit's nonzero differences still occur only in
  `capture-2025-03-18`; hash uniqueness does not establish independent physical scenes.
- Driver smoke: **6 pass / 0 fail**. Shipped-look contract probe: **168 pass**.
  These are execution checks, not appearance validation. The existing Hasselblad
  night white-input divide-by-zero warning remains visible.
- Repository integrity passes, including 13 DCP and 73 ICC checks. Its document
  parity scan still covers only 16 top-level documents; the recursive gap above remains.

## What the classification still cannot prove

The JSON interfaces accept precomputed errors, labels, hashes and explicit
attestations. They do not authenticate whether a caller actually ran controls,
used correct semantic masks, assigned physical scenes honestly, preserved SOOC
JPEGs, or independently replicated an experiment. Fabricated but internally
consistent finite values and literal `True` attestations can still receive a
positive classification. Closing that trust boundary requires an evidence-bound
execution/provenance design, beyond these reproduced validator repairs.

No shipped look/profile or recorded fitting artifact was edited.
Supported/Verified here is conditional on the supplied evidence being truthful;
this re-audit does not authorize a photographic-accuracy or release claim.
