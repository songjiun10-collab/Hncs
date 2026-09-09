"""Sync frozen EAGER/NARE reports to the HNCS Supabase research registry."""

from __future__ import annotations

import json
import os
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

import requests


URL_ENV = "HNCS_SUPABASE_URL"
KEY_ENV = "HNCS_SUPABASE_SERVICE_ROLE_KEY"
_CLASSIFICATIONS = {"Verified", "Supported", "Inconclusive", "Rejected", "Exploratory"}
_PROTOCOLS = {"EAGER", "NARE", "Protocol 2R", "other"}


class SupabaseRestClient:
    """Minimal PostgREST client; credentials never enter reports or files."""

    def __init__(
        self,
        url: str | None = None,
        service_role_key: str | None = None,
        session: requests.Session | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.url = (url or os.environ.get(URL_ENV, "")).strip().rstrip("/")
        self.key = (service_role_key or os.environ.get(KEY_ENV, "")).strip()
        self.timeout = timeout
        self.session = session or requests.Session()
        missing = [name for name, value in ((URL_ENV, self.url), (KEY_ENV, self.key)) if not value]
        if missing:
            raise RuntimeError(f"missing Supabase environment variable(s): {', '.join(missing)}")
        if not self.url.startswith("https://"):
            raise ValueError(f"{URL_ENV} must use https://")

    def upsert(
        self, table: str, rows: Sequence[Mapping[str, Any]], on_conflict: str,
    ) -> list[dict[str, Any]]:
        if not rows:
            return []
        response = self.session.post(
            f"{self.url}/rest/v1/{table}",
            params={"on_conflict": on_conflict},
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
            json=list(rows),
            timeout=self.timeout,
        )
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            detail = getattr(response, "text", "")
            raise RuntimeError(f"Supabase {table} upsert failed: {detail}") from exc
        value = response.json()
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            raise RuntimeError(f"Supabase {table} upsert returned an invalid payload")
        return value


def sha256_file(path: str | Path) -> str:
    digest = sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_git_sha() -> str | None:
    env_sha = os.environ.get("GITHUB_SHA", "").strip()
    if env_sha:
        return env_sha
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True,
            text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def _records(path: str | Path) -> list[dict[str, Any]]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = value.get("rows")
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError(f"{path} must contain a JSON row list")
    return value


def _classification(report: Mapping[str, Any]) -> tuple[str, bool]:
    value = report.get("classification")
    if isinstance(value, Mapping):
        label = value.get("classification")
        ship = bool(value.get("ship_gate_passed", value.get("ship_gate", False)))
    else:
        label = value
        ship = bool(report.get("ship_gate_passed", report.get("ship_gate", False)))
    if label not in _CLASSIFICATIONS:
        raise ValueError(f"unsupported classification: {label!r}")
    return str(label), ship


def _single_split(rows: Sequence[Mapping[str, Any]]) -> str | None:
    values = {str(row.get("split", "")).strip() for row in rows}
    values.discard("")
    return next(iter(values)) if len(values) == 1 else None


def _run_key(
    protocol: str, dataset_slug: str, candidate_name: str,
    manifest_sha: str, metrics_sha: str, *artifact_shas: str,
) -> str:
    raw = "\0".join((protocol, dataset_slug, candidate_name, manifest_sha,
                       metrics_sha, *artifact_shas))
    suffix = sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"{protocol.lower().replace(' ', '-')}:{dataset_slug}:{candidate_name}:{suffix}"


def sync_evaluation_report(
    report: Mapping[str, Any],
    *,
    protocol: str,
    dataset_slug: str,
    candidate_name: str,
    manifest_path: str | Path,
    metrics_path: str | Path,
    controls_path: str | Path | None = None,
    robustness_path: str | Path | None = None,
    report_path: str | Path | None = None,
    evidence_tier: str = "C",
    brand: str | None = None,
    camera_model: str | None = None,
    source_type: str = "raw_jpeg_pairs",
    git_sha: str | None = None,
    external_replication: bool = False,
    bootstrap_draws: int | None = None,
    bootstrap_seed: int | None = None,
    client: SupabaseRestClient | None = None,
) -> dict[str, Any]:
    """Upsert a report using hashes as the immutable run identity."""

    tier = evidence_tier.upper()
    if tier not in {"A", "B", "C", "D", "E"}:
        raise ValueError(f"unsupported evidence tier: {evidence_tier!r}")
    if protocol not in _PROTOCOLS:
        raise ValueError(f"unsupported protocol: {protocol!r}")
    if not dataset_slug.strip() or not candidate_name.strip():
        raise ValueError("dataset_slug and candidate_name must be non-empty")

    manifest_rows = _records(manifest_path)
    paired = report.get("paired")
    if not isinstance(paired, Mapping):
        raise ValueError("report must contain a paired object")
    per_scene = paired.get("per_scene")
    if not isinstance(per_scene, list) or not all(isinstance(row, Mapping) for row in per_scene):
        raise ValueError("report paired.per_scene must be a row list")

    classification, ship_gate = _classification(report)
    # This uploader has no independent verifier or protected trust root.
    # JSON booleans (including receipt.trusted) cannot grant publication rights.
    # Keep research uploads available, but fail closed on evidence promotion
    # until an independently verified ingestion path exists.
    if ship_gate or classification in {"Supported", "Verified"}:
        raise ValueError(
            "promotion requires independent verification of trusted provenance; "
            "this uploader cannot publish Supported, Verified, or ship gates")
    manifest_sha = sha256_file(manifest_path)
    metrics_sha = sha256_file(metrics_path)
    controls_sha = sha256_file(controls_path) if controls_path else None
    robustness_sha = sha256_file(robustness_path) if robustness_path else None
    report_sha = sha256_file(report_path) if report_path else None
    run_key = _run_key(
        protocol, dataset_slug, candidate_name, manifest_sha, metrics_sha,
        controls_sha or "", robustness_sha or "", report_sha or "",
    )
    client = client or SupabaseRestClient()

    coverage = paired.get("coverage")
    if not isinstance(coverage, Mapping):
        coverage = {}
    dataset_result = client.upsert(
        "hncs_datasets",
        [{
            "slug": dataset_slug,
            "brand": brand,
            "camera_model": camera_model,
            "source_type": source_type,
            "evidence_tier": tier,
            "provenance_status": (
                "complete" if bool(paired.get("provenance_passed", False)) else "incomplete"
            ),
            "manifest_sha256": manifest_sha,
            "metadata": {
                "lighting": coverage.get("lighting"),
                "scene_type": coverage.get("scene_type"),
            },
        }],
        "slug",
    )
    dataset_id = dataset_result[0].get("id")
    if not dataset_id:
        raise RuntimeError("Supabase dataset upsert returned no id")

    ci95 = paired.get("ci95")
    ci_low = ci_high = None
    if isinstance(ci95, (list, tuple)) and len(ci95) == 2:
        ci_low, ci_high = float(ci95[0]), float(ci95[1])

    run_result = client.upsert(
        "hncs_runs",
        [{
            "run_key": run_key,
            "dataset_id": dataset_id,
            "protocol": protocol,
            "candidate_name": candidate_name,
            "git_sha": git_sha or current_git_sha(),
            "split": _single_split(manifest_rows),
            "evidence_tier": tier,
            "classification": classification,
            "ship_gate": ship_gate,
            "provenance_complete": bool(paired.get("provenance_passed", False)),
            "external_replication": bool(external_replication),
            "bootstrap_draws": bootstrap_draws,
            "bootstrap_seed": bootstrap_seed,
            "n_scenes": paired.get("n_scenes"),
            "mean_baseline": paired.get("mean_baseline"),
            "mean_candidate": paired.get("mean_candidate"),
            "mean_improvement": paired.get("mean_improvement"),
            "mean_improvement_pct": paired.get(
                "mean_improvement_pct", paired.get("improvement_pct")
            ),
            "ci95_low": ci_low,
            "ci95_high": ci_high,
            "sign_test_p": paired.get("sign_test_p"),
            "manifest_sha256": manifest_sha,
            "metrics_sha256": metrics_sha,
            "controls_sha256": controls_sha,
            "robustness_sha256": robustness_sha,
            "controls": report.get("controls", {
                key: paired.get(key) for key in
                ("controls_passed", "subgroups_passed", "provenance_passed")
                if key in paired
            }),
            "robustness": report.get("robustness", {}),
            "sample_accounting": report.get("sample_accounting", {}),
            "raw_result": dict(report),
        }],
        "run_key",
    )
    run_id = run_result[0].get("id")
    if not run_id:
        raise RuntimeError("Supabase run upsert returned no id")

    manifest_by_scene = {
        str(row.get("scene_id")): row for row in manifest_rows if row.get("scene_id") is not None
    }
    scene_rows = []
    for row in per_scene:
        scene_id = str(row.get("scene_id", "")).strip()
        if not scene_id:
            raise ValueError("per_scene row missing scene_id")
        metadata = manifest_by_scene.get(scene_id, {})
        baseline = float(row["baseline_delta_e00"])
        candidate = float(row["candidate_delta_e00"])
        scene_rows.append({
            "run_id": run_id,
            "scene_id": scene_id,
            "source_body": row.get("source_body") or metadata.get("source_body"),
            "target_body": metadata.get("target_body"),
            "illumination_id": (
                row.get("illumination_id") or metadata.get("illumination_id")
                or metadata.get("lighting")
            ),
            "scene_category": metadata.get("scene_type") or metadata.get("scene_category"),
            "baseline_delta_e00": baseline,
            "candidate_delta_e00": candidate,
            "improvement": float(row.get("improvement", baseline - candidate)),
            "neutral_baseline": row.get("neutral_baseline"),
            "neutral_candidate": row.get("neutral_candidate"),
            "chromatic_baseline": row.get("chromatic_baseline"),
            "chromatic_candidate": row.get("chromatic_candidate"),
            "metadata": {
                key: metadata.get(key) for key in
                ("session_id", "contributor", "picture_style")
                if metadata.get(key) is not None
            },
        })
    client.upsert("hncs_scene_metrics", scene_rows, "run_id,scene_id")

    artifacts: list[tuple[str, str | Path, str | None]] = [
        ("manifest", manifest_path, manifest_sha),
        ("metrics", metrics_path, metrics_sha),
    ]
    if controls_path:
        artifacts.append(("controls", controls_path, controls_sha))
    if robustness_path:
        artifacts.append(("robustness", robustness_path, robustness_sha))
    if report_path and Path(report_path).exists():
        artifacts.append(("report", report_path, sha256_file(report_path)))
    client.upsert(
        "hncs_artifacts",
        [{
            "run_id": run_id,
            "kind": kind,
            "repo_path": str(path),
            "sha256": digest,
        } for kind, path, digest in artifacts],
        "run_id,kind,repo_path",
    )

    return {
        "dataset_id": dataset_id,
        "run_id": run_id,
        "run_key": run_key,
        "classification": classification,
        "ship_gate": ship_gate,
        "n_scenes": len(scene_rows),
    }
