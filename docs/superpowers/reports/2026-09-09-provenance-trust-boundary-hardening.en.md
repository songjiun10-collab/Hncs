# HNCS provenance trust-boundary hardening

[한국어](2026-09-09-provenance-trust-boundary-hardening.md)

A 2026-09-09 re-audit reproduced that a local caller could generate an arbitrary
Ed25519 key, place its fingerprint in `HNCS_TRUSTED_RECEIPT_PUBLIC_KEY_SHA256` /
`HNCS_TRUSTED_EVALUATOR_SHA256`, and reach EAGER `Verified`. Environment variables
chosen by the local caller are not an independent trust anchor.

The same re-audit hardened promotion configuration that was previously separable
from the receipt. EAGER now signs `evidence_tier`, `validation_passed`,
`lockbox_passed`, and `external_replication` inside `run_config` together with the
bootstrap draw count and seed. Reusing the same receipt while changing only a CLI
value fails closed at `run_config` validation.

The normal EAGER CLI now separates signature/artifact integrity from signer
authority. `validate_receipt()` returns `signature_valid=True` for a valid
signature but `trusted=False`. The local CLI never creates
`trusted_provenance=True`, so local execution is capped at `Supported` and
`Verified` is intentionally unreachable until there is a separate trusted runner
whose authority the local caller cannot choose.

NARE has no `Verified` class. It uses a valid signed receipt only as an artifact
integrity gate for `Supported`, without claiming `trusted_provenance`; bootstrap
and seed must also match the signed `run_config`.

Issuing genuine `Verified` results requires an external trust anchor such as a
private signing key plus approval policy and a protected ref/environment. The
GitHub connection available in this session cannot create Actions secrets or
protected-environment policy, so this change does not pretend that path exists.
The existing Supabase uploader fail-closed block on Supported/Verified/ship
promotion remains unchanged.
