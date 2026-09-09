# Promoting internally consistent fabricated evidence to Verified

[한국어](2026-09-08-fabricated-evidence.md)

> **Correction (2026-09-08, trusted-provenance gate)**: The generic EAGER JSON
> CLI now forces `trusted_provenance=False`, so the same fabricated bundle is
> capped at `Supported` even when `--external-replication` is supplied. Only a
> trusted execution caller can pass `trusted_provenance=True` to the classifier.
> This is a fail-closed policy boundary, not cryptographic authentication; a
> caller that is already trusted can still lie, and that trust boundary remains
> explicitly documented.

Baseline commit `0da0c44086d0805e3ea87de536d66e1ed5a9c03f` is the original
attack reproduction. The current regression run invokes the actual EAGER CLI in
subprocesses without mocking classification, statistics or file reads. **The
unreceipted fabricated bundle now reaches Supported at most and cannot reach
Verified.**

## Construction and observations

Generate 24 real, decodable synthetic PPM sources and 24 targets. Pixels and
hashes differ across scenes; each source/target pair has equal pixels. Independently
check that all 48 file hashes match the manifest. This is not a RAW/SOOC capture
corpus: the attack targets EAGER's precomputed-metric interface.

Claim 12 evaluation scenes, 12 lockbox scenes and tier A. Invent baseline errors
of 10.0–10.8 and candidate errors equal to baseline×0.8, without measuring images.
Invent finite positive improving neutral/chromatic errors. Set every control and
robustness field to actual boolean True. The number of controls actually executed
and independent replications actually performed is **zero**.

| Input condition | Observed result |
|---|---|
| Files present, 48/48 matching hashes, invented metrics and attestations | Supported |
| Remove only external-replication flag | Supported |
| Set shuffle control to actual boolean False | Ship gate fails |
| Mutate every source file, producing 24 hash mismatches | Supported |
| Delete all 48 source/target image files | Supported |

Statistics genuinely computed by the CLI from the invented table:

- n_scenes: 24
- mean_improvement_pct: 19.999999999999996
- 20,000-draw bootstrap CI: [2.0549999999999997, 2.098333333333333]
- sign_test_p: 1.1920928955078125e-07

The arithmetic is not the defect. The interface does not establish the origin
of its measurements or whether experiments were performed. These statistics
describe the invented table, not real photographic performance.

## Cause and boundary

`eager_cli.build_report` reads the JSON and validates manifests/metrics.
`evaluate_manifest_metrics` checks hash syntax but does not open source/target
files to verify their hashes or recompute measurements. Controls are boolean
declarations and external replication is a CLI flag. Promotion therefore does
not require authenticated execution evidence.

Checking file hashes would block the mutation/deletion cases, but would not
block the initial fabrication with genuinely matching hashes. A signature or
extra JSON field produced by the same author is not independent verification.
Giving Verified an empirical meaning requires binding measurements, code,
inputs, outputs and control execution, with replication evidence from a separate
trusted party.

This change records and reproduces the attack without modifying production
validators or classification policy. It does not claim to bypass the real RAW
runner. No Supabase sync, deployment or real calibration-registry insertion was
performed. Temporary synthetic inputs and full CLI reports are deleted on exit;
the retained summary explicitly identifies itself as a SYNTHETIC attack.

## Reproduction

[Attack script](2026-09-08-fabricated-evidence-probe.py) ·
[Observed results](2026-09-08-fabricated-evidence-results.json)

From the repository root:

```bash
~/.hncs-hybrid-venv312/bin/python3 docs/superpowers/reports/2026-09-08-fabricated-evidence-probe.py --out /tmp/hncs-fabricated-evidence-results.json
```

The original `Verified` result is retained as historical characterization from
before the trusted-provenance gate. The current script replays the same
synthetic bundle and asserts that an unreceipted result cannot reach `Verified`,
so it now serves as a security regression probe.
