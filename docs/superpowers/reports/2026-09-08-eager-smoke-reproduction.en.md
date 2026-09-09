# EAGER smoke reproduction (2026-09-08)

[한국어](2026-09-08-eager-smoke-reproduction.md)

This record checks reproducibility of the EAGER statistical kernel and
classification gates using **synthetic input**. The run does not contain
same-physical-scene data from real cameras, so it cannot support cross-camera
generalization or deployment performance claims.

## Input contract

- 12 independent `scene_id` values (`scene-00`–`scene-11`)
- Lighting strata: 6 `daylight`, 6 `tungsten`
- Source body: `source-a`; target body: `target-b`
- Every row: `split=lockbox`, `evidence_tier=C`
- Paired metric: baseline ΔE00 repeated at `10.0/10.2/10.4`, candidate ΔE00 repeated at `8.0/8.1`
- Neutral: `4.0 → 3.0`; chromatic: `12.0 → 9.5`
- Bootstrap: 20,000 draws, seed `0`
- Controls: identity, target-reference shuffle, source-label shuffle, holdout rerun,
  and chart positive control all `true`
- Robustness: source body and both lighting strata `true`

## Reproduction command

Create four input JSON files with the contract above, then run:

```bash
.venv/bin/python -m hybrid_engine.evaluation.eager_cli \
  --manifest /tmp/eager-repro/manifest.json \
  --metrics /tmp/eager-repro/metrics.json \
  --controls /tmp/eager-repro/controls.json \
  --robustness /tmp/eager-repro/robustness.json \
  --evidence-tier C --validation-passed --lockbox-passed \
  --bootstrap 20000 --seed 0
```

## Result

| Item | Value |
|---|---:|
| Independent scenes | 12 |
| Mean baseline ΔE00 | 10.200000000000001 |
| Mean candidate ΔE00 | 8.049999999999999 |
| Mean improvement | 2.15 |
| Mean improvement percentage | 21.078431372549016% |
| Paired bootstrap 95% CI | [2.0500000000000003, 2.241666666666667] |
| Exact sign-test p | 0.00048828125 |
| Ship gate | `true` |
| Classification | `Supported` |

All gates pass, but this is Tier C and has no external replication, so it is
not `Verified`. The values record only that scene-level aggregation, paired
uncertainty, subgroup, control, and robustness gates are applied
deterministically to the same input. They are not an effect-size claim for a
real appearance transform.

## Falsification check

Changing `target_reference_shuffle` to `false` with the same input produces:

```text
controls_passed=false
ship_gate_passed=false
classification=Rejected
failure=target_reference_shuffle
```

When real Protocol 2R results are added, they must use a separate manifest,
metric set, and provenance hashes; the synthetic smoke result must not be
overwritten.
