"""Signed provenance receipts for evidence-producing evaluation runs.

Receipts bind the exact input artifacts and evaluator identity to a run. They
do not prove that the captured data represents reality; they prove which
artifacts a trusted runner claimed to execute and sign.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


_SCHEMA = "hncs.evidence-receipt/v1"
_REQUIRED_ARTIFACTS = ("manifest", "metrics", "controls", "robustness")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX_SHA = re.compile(r"^[0-9a-f]{7,64}$")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sha256_file(path: str | Path) -> str:
    digest = sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def public_key_sha256(path: str | Path) -> str:
    """Return the fingerprint of the raw Ed25519 public-key bytes."""
    try:
        raw = base64.b64decode(Path(path).read_text(encoding="ascii").strip(), validate=True)
    except (OSError, UnicodeError, ValueError, binascii.Error) as error:
        raise ValueError("receipt public key is invalid") from error
    if len(raw) != 32:
        raise ValueError("receipt public key is invalid")
    return sha256(raw).hexdigest()


def build_receipt(
    artifact_paths: Mapping[str, str | Path], *, git_sha: str,
    evaluator_sha256: str, command: list[str], run_id: str,
    timestamp: str, parent_run_id: str | None = None,
    required_artifacts: tuple[str, ...] = _REQUIRED_ARTIFACTS,
) -> dict[str, Any]:
    """Create an unsigned receipt from the artifacts actually on disk."""
    missing = [name for name in required_artifacts if name not in artifact_paths]
    if missing:
        raise ValueError(f"receipt missing artifact paths: {', '.join(missing)}")
    if not isinstance(command, list) or not command or not all(isinstance(v, str) and v for v in command):
        raise ValueError("receipt command must be a non-empty string list")
    if not isinstance(git_sha, str) or not _HEX_SHA.fullmatch(git_sha.lower()):
        raise ValueError("receipt git_sha must be a hexadecimal commit SHA")
    if not isinstance(evaluator_sha256, str) or not _HEX64.fullmatch(evaluator_sha256.lower()):
        raise ValueError("receipt evaluator_sha256 must be a SHA-256 digest")
    if not isinstance(run_id, str) or not run_id.strip() or not isinstance(timestamp, str) or not timestamp.strip():
        raise ValueError("receipt run_id and timestamp must be non-empty")
    artifacts = {}
    for name, path in artifact_paths.items():
        artifacts[name] = {"path": str(path), "sha256": sha256_file(path)}
    return {
        "schema": _SCHEMA,
        "run_id": run_id,
        "parent_run_id": parent_run_id,
        "git_sha": git_sha.lower(),
        "evaluator_sha256": evaluator_sha256.lower(),
        "command": list(command),
        "timestamp": timestamp,
        "artifacts": artifacts,
    }


def sign_receipt(receipt: Mapping[str, Any], private_key: Ed25519PrivateKey,
                 *, key_id: str) -> dict[str, Any]:
    """Sign the canonical unsigned receipt with an Ed25519 private key."""
    if not isinstance(key_id, str) or not key_id.strip():
        raise ValueError("receipt key_id must be non-empty")
    unsigned = dict(receipt)
    unsigned.pop("signature", None)
    signature = private_key.sign(_canonical(unsigned))
    return unsigned | {"signature": {
        "algorithm": "Ed25519",
        "key_id": key_id,
        "value": base64.b64encode(signature).decode("ascii"),
    }}


def _decode_public_key(path: str | Path) -> Ed25519PublicKey:
    try:
        raw = base64.b64decode(Path(path).read_text(encoding="ascii").strip(), validate=True)
        return Ed25519PublicKey.from_public_bytes(raw)
    except (OSError, UnicodeError, ValueError, binascii.Error) as error:
        raise ValueError("receipt public key is invalid") from error


def validate_receipt(
    receipt_path: str | Path, artifact_paths: Mapping[str, str | Path],
    public_key_path: str | Path, expected_git_sha: str | None = None,
    required_artifacts: tuple[str, ...] = _REQUIRED_ARTIFACTS,
    trusted_public_key_sha256: str | None = None,
    trusted_evaluator_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate signature and every artifact hash before trusting a run."""
    try:
        receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("receipt is not valid JSON") from error
    if not isinstance(receipt, dict) or receipt.get("schema") != _SCHEMA:
        raise ValueError("receipt schema is unsupported")
    if (not isinstance(receipt.get("git_sha"), str)
            or not _HEX_SHA.fullmatch(receipt["git_sha"].lower())):
        raise ValueError("receipt git_sha is missing or invalid")
    if expected_git_sha is not None and receipt["git_sha"].lower() != expected_git_sha.lower():
        raise ValueError("receipt git_sha does not match expected git_sha")
    if (not isinstance(receipt.get("evaluator_sha256"), str)
            or not _HEX64.fullmatch(receipt["evaluator_sha256"].lower())):
        raise ValueError("receipt evaluator_sha256 is missing or invalid")
    if trusted_evaluator_sha256 is not None:
        if (not isinstance(trusted_evaluator_sha256, str)
                or not _HEX64.fullmatch(trusted_evaluator_sha256.lower())):
            raise ValueError("trusted evaluator fingerprint is invalid")
        if receipt["evaluator_sha256"].lower() != trusted_evaluator_sha256.lower():
            raise ValueError("receipt evaluator is not trusted")
    if (not isinstance(receipt.get("command"), list)
            or not receipt["command"]
            or not all(isinstance(value, str) and value for value in receipt["command"])
            or not isinstance(receipt.get("timestamp"), str)
            or not receipt["timestamp"].strip()):
        raise ValueError("receipt execution metadata is missing or invalid")
    signature = receipt.get("signature")
    if (not isinstance(signature, dict) or signature.get("algorithm") != "Ed25519"
            or not isinstance(signature.get("key_id"), str)
            or not signature["key_id"].strip()):
        raise ValueError("receipt signature is missing or unsupported")
    try:
        encoded = signature["value"]
        signed_bytes = base64.b64decode(encoded, validate=True)
    except (KeyError, ValueError, binascii.Error) as error:
        raise ValueError("receipt signature is invalid") from error
    unsigned = dict(receipt)
    unsigned.pop("signature", None)
    try:
        _decode_public_key(public_key_path).verify(signed_bytes, _canonical(unsigned))
    except (InvalidSignature, ValueError) as error:
        raise ValueError("receipt signature verification failed") from error
    if trusted_public_key_sha256 is not None:
        if (not isinstance(trusted_public_key_sha256, str)
                or not _HEX64.fullmatch(trusted_public_key_sha256.lower())):
            raise ValueError("trusted receipt public-key fingerprint is invalid")
        if public_key_sha256(public_key_path) != trusted_public_key_sha256.lower():
            raise ValueError("receipt public key is not trusted")
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("receipt artifacts are missing")
    missing = [name for name in required_artifacts if name not in artifacts or name not in artifact_paths]
    if missing:
        raise ValueError(f"receipt artifacts missing: {', '.join(missing)}")
    for name, path in artifact_paths.items():
        entry = artifacts.get(name)
        if not isinstance(entry, dict) or not _HEX64.fullmatch(str(entry.get("sha256", "")).lower()):
            raise ValueError(f"receipt {name} artifact digest is invalid")
        actual = sha256_file(path)
        if actual != entry["sha256"].lower():
            raise ValueError(f"receipt {name} artifact hash does not match")
    if not isinstance(receipt.get("run_id"), str) or not receipt["run_id"].strip():
        raise ValueError("receipt run_id is missing")
    return {"trusted": True, "run_id": receipt["run_id"],
            "key_id": signature.get("key_id"), "git_sha": receipt.get("git_sha")}
