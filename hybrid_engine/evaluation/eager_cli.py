"""Run an EAGER paired evaluation from manifest and metric JSON files.

Rendering and ROI extraction remain explicit inputs.  This command only joins
their recorded results and applies the evidence gates, which keeps model
selection and image processing outside the statistical checker.
"""

import argparse
import json
from pathlib import Path
from typing import Any

from .eager import (
    EvidenceTier,
    classify_result,
    evaluate_manifest_metrics,
    validate_controls,
    validate_robustness,
)


def _load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _records(value: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(value, list) and all(isinstance(row, dict) for row in value):
        return value
    if isinstance(value, dict) and isinstance(value.get("rows"), list):
        rows = value["rows"]
        if all(isinstance(row, dict) for row in rows):
            return rows
    raise ValueError(f"{label} JSON must be a list of objects or an object with a rows list")


def build_report(
    manifest_path: str, metrics_path: str, controls_path: str,
    robustness_path: str, evidence_tier: str, validation_passed: bool,
    lockbox_passed: bool, external_replication: bool,
    n_bootstrap: int = 20_000, seed: int = 0,
) -> dict[str, Any]:
    """Load JSON inputs, evaluate paired errors, and classify the evidence."""

    paired_report = evaluate_manifest_metrics(
        _records(_load_json(manifest_path), "manifest"),
        _records(_load_json(metrics_path), "metrics"),
        n_bootstrap=n_bootstrap,
        seed=seed,
    )
    controls = validate_controls(_load_json(controls_path))
    robustness = validate_robustness(_load_json(robustness_path))
    paired = paired_report["paired"]
    paired["controls_passed"] = controls["passed"]
    paired["robustness_passed"] = robustness["passed"]
    paired_report["controls"] = controls
    paired_report["robustness"] = robustness
    paired_report["classification"] = classify_result(
        paired, EvidenceTier(evidence_tier.upper()),
        lockbox_passed=lockbox_passed,
        external_replication=external_replication,
        validation_passed=validation_passed,
    )
    return paired_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply EAGER evidence gates to recorded metric tables")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--controls", required=True)
    parser.add_argument("--robustness", required=True)
    parser.add_argument("--evidence-tier", required=True, choices=[tier.value for tier in EvidenceTier])
    parser.add_argument("--validation-passed", action="store_true")
    parser.add_argument("--lockbox-passed", action="store_true")
    parser.add_argument("--external-replication", action="store_true")
    parser.add_argument("--bootstrap", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out")
    args = parser.parse_args()
    report = build_report(
        args.manifest, args.metrics, args.controls, args.robustness,
        args.evidence_tier, args.validation_passed, args.lockbox_passed,
        args.external_replication, n_bootstrap=args.bootstrap, seed=args.seed,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
