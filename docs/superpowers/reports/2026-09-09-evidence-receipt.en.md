# HNCS Evidence Receipt — minimal provenance/authentication layer

[한국어](2026-09-09-evidence-receipt.md)

The attack in `0da0c44` and `3e27c7a` showed that the missing protection was not
finite metrics or hash syntax. There was no binding from an external JSON report
to the inputs, code and configuration that supposedly produced it.

`hybrid_engine/evaluation/evidence_receipt.py` now provides canonical JSON and
Ed25519 receipt verification. A receipt signs:

- SHA-256 hashes for manifest, metrics, controls and robustness artifacts
- evaluator SHA-256 and git commit SHA
- execution command, timestamp, run ID and optional parent run ID
- signing key ID and Ed25519 signature

The EAGER CLI accepts `--receipt` and `--receipt-public-key`, then checks the
current hashes of all four artifacts and verifies the signature. Missing either
argument or any hash mismatch is rejected. Without a valid receipt,
`trusted_provenance=False`; `--external-replication` alone cannot produce
`Verified`. Only a trusted runner that validates a receipt can pass
`trusted_provenance=True` to the classifier.

```bash
python -m hybrid_engine.evaluation.eager_cli \
  --manifest manifest.json --metrics metrics.json \
  --controls controls.json --robustness robustness.json \
  --git-sha "$GIT_COMMIT_SHA" \
  --evidence-tier C --validation-passed --lockbox-passed \
  --external-replication \
  --receipt run.receipt.json --receipt-public-key ci-ed25519.pub
```

The existing JSON CLI remains compatible through `Supported`. The fail-closed
boundary is that JSON without a receipt cannot become `Verified`.

## Verification

- valid signed receipt and artifact chain: passed
- metrics mutation after signing: rejected
- unsigned receipt: rejected
- valid receipt-backed EAGER report: `Verified`
- external-replication claim without receipt: `Supported`
- full suite: 1,425 tests passed

## Limitations

This layer authenticates that a trusted runner signed the specified artifacts
and evaluator identity. It does not mathematically prove that the data truthfully
represents reality or that the evaluator internally ran the right algorithm. A
trusted runner holding the Ed25519 private key can still sign a lie. Keep that
private key in a separate runner such as GitHub CI and cap local runs at
`Supported`.

No private signing key is stored in the repository or report. This change does
not modify shipped looks/profiles, existing datasets or the Supabase registry.
