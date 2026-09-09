# HNCS Evidence Receipt — minimal provenance/authentication layer

[한국어](2026-09-09-evidence-receipt.md)

> **Correction (2026-09-09, forged registry trust re-audit):** The completion
> claims below do not establish independently authenticated execution. Adding
> `trusted_provenance: true` and a fake receipt object bypassed both registry
> checks. All five regression cases passed without rejection before the fix:
> Verified/Supported with ship true/false, and Inconclusive with ship true.
> The uploader now rejects Supported/Verified or ship=true before any write.
> This is temporary fail-closed containment, not trusted ingestion. Research
> uploads labelled Exploratory/Inconclusive/Rejected remain available.
> Validating a signature against a submitter-selected public key does not
> establish trust in that key. CLI classifications, actual RAW/JPEG file
> verification, evaluator/config verification and independent replay still
> need work. This change neither audits existing remote records nor prevents
> direct database writes by a service-role credential holder.
> The EAGER CLI now requires `HNCS_TRUSTED_RECEIPT_PUBLIC_KEY_SHA256` to match
> the supplied key before a receipt-backed run can become `Verified`; without
> that protected fingerprint the same receipt remains `Supported`.
> The evaluator hash must also match `HNCS_TRUSTED_EVALUATOR_SHA256`.

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
export HNCS_TRUSTED_RECEIPT_PUBLIC_KEY_SHA256="$(openssl dgst -sha256 -binary ci-ed25519.pub | xxd -p -c 256)"
export HNCS_TRUSTED_EVALUATOR_SHA256="$(shasum -a 256 hybrid_engine/evaluation/eager_cli.py | awk '{print $1}')"
python -m hybrid_engine.evaluation.eager_cli \
  --manifest manifest.json --metrics metrics.json \
  --controls controls.json --robustness robustness.json \
  --git-sha "$GIT_COMMIT_SHA" \
  --evidence-tier C --validation-passed --lockbox-passed \
  --external-replication \
  --receipt run.receipt.json --receipt-public-key ci-ed25519.pub
```

The NARE CLI uses the same receipt boundary and checks a three-artifact chain for
manifest, metrics and controls. External metrics without a receipt remain
`Inconclusive`; only a signed receipt-backed run can become `Supported`. The
existing EAGER JSON path remains compatible through `Supported`, while
`Verified` requires a receipt.

## Verification

- valid signed receipt and artifact chain: passed
- metrics mutation after signing: rejected
- unsigned receipt: rejected
- valid receipt-backed EAGER report: `Verified`
- external-replication claim without receipt: `Supported`
- plausible NARE metrics without a receipt: `Inconclusive`
- valid receipt-backed NARE report: `Supported`
- full suite: 1,455 tests passed (rerun on the current checkout)

## NARE trusted-runner re-audit (2026-09-09)

The NARE CLI now matches EAGER: a receipt contributes to the provenance gate
only when both the trusted receipt public-key fingerprint and evaluator
fingerprint are pinned in the environment. A formally valid receipt signed by
an arbitrary Ed25519 key still passes the hash-chain check but remains
`trusted_provenance=False` and `Inconclusive`. Only matching both fingerprints
can reach the `Supported` path. The regression coverage is two
`tests.test_nare_cli` tests; the full suite now passes 1,455 tests.

The NARE CLI also requires `--receipt` and `--receipt-public-key` to be supplied
together. A one-sided invocation fails immediately instead of silently ignoring
the provenance input.

The receipt `git_sha` is also restricted to a full 40-character commit SHA.
Abbreviated revisions remain suitable for registry metadata but cannot identify
the code in an execution provenance receipt.

Registry sync also requires literal JSON boolean `true` for
`ship_gate_passed`, `provenance_passed`, and `external_replication`; Python
truthiness is no longer accepted. Fabricated values such as `"false"` cannot
pollute the stored complete or ship state.

NARE reports now also record `bootstrap_draws` and `bootstrap_seed` in the
`paired` result, binding the metrics to the statistical configuration used.

The registered-report audit also requires an allowed classification label and a
literal JSON boolean for `ship_gate_passed`.

## Limitations

This layer authenticates that a trusted runner signed the specified artifacts
and evaluator identity. It does not mathematically prove that the data truthfully
represents reality or that the evaluator internally ran the right algorithm. A
trusted runner holding the Ed25519 private key can still sign a lie. Keep that
private key in a separate runner such as GitHub CI and cap local runs at
`Supported`.

No private signing key is stored in the repository or report. This change does
not modify shipped looks/profiles, existing datasets or the Supabase registry.
