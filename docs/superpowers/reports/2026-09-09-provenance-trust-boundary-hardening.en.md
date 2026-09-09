# HNCS provenance trust-boundary hardening

[한국어](2026-09-09-provenance-trust-boundary-hardening.md)

A 2026-09-09 re-audit reproduced two concrete counterexamples against the
existing Evidence Receipt boundary.

1. A local caller could generate an arbitrary Ed25519 key, place its fingerprint
   in `HNCS_TRUSTED_RECEIPT_PUBLIC_KEY_SHA256` / `HNCS_TRUSTED_EVALUATOR_SHA256`,
   and make EAGER promote the run to `Verified`.
2. Keeping the receipt unchanged while changing only `validation_passed`,
   `lockbox_passed`, or `external_replication` could change classification
   without invalidating the signature. `evidence_tier` was not receipt-bound
   either.

This change separates local verification from independent trust.

- `validate_receipt()` now means **signature/artifact integrity validation**.
  It returns `signature_valid=True`, while the compatibility `trusted` field is
  always `False`. Optional expected key/evaluator fingerprints may still be
  checked for equality, but equality with caller-supplied expectations is not
  interpreted as promotion authority.
- An EAGER receipt must sign `evidence_tier` and all three promotion attestations:
  `validation_passed`, `lockbox_passed`, and `external_replication`. Missing or
  mismatched values fail closed.
- The normal EAGER CLI never sets `trusted_provenance=True`, regardless of local
  environment variables or self-signed keys. Local execution is therefore capped
  at `Supported`; `Verified` is intentionally unreachable until a separate
  trusted-runner path exists.
- NARE has no `Verified` class, so the meanings are separated there as well. A
  valid signed receipt may satisfy the local `receipt_integrity` gate for
  `Supported`, but it does not claim `trusted_provenance`.

## Remaining boundary

Issuing a genuine independent `Verified` result needs a trust anchor that a local
caller cannot choose: a private signing key, approval policy, and protected
ref/environment or equivalent external authority. The GitHub connection available
in this session cannot create or inspect Actions secrets or protected-environment
settings, so this commit does not pretend that path exists. It instead fails
closed for local promotion.

The existing Supabase uploader block on Supported/Verified/ship promotion remains
unchanged. Production looks/profiles and dataset binaries are untouched.

## Verification

Regression coverage includes:

- self-generated key + self-selected `HNCS_TRUSTED_*` environment → EAGER remains `Supported`
- flip one promotion attestation at the CLI while keeping the signed receipt → rejected
- receipt evidence tier differs from CLI tier → rejected
- NARE without receipt → `Inconclusive`
- NARE with a valid signed receipt → `Supported`, while `trusted_provenance=False`

The full-suite result is verified by the GitHub Actions run for this commit.
