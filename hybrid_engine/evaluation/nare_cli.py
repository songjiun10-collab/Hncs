"""Run a NARE natural-scene evaluation from recorded JSON artifacts."""

import argparse
import json
from pathlib import Path
from typing import Any

from .nare import classify_nare_result, evaluate_nare_metrics
from .evidence_receipt import validate_receipt
from .supabase_sync import sync_evaluation_report


def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_report(manifest_path: str, metrics_path: str, controls_path: str,
                 n_bootstrap: int = 20_000, seed: int = 0, *,
                 receipt_path: str | None = None,
                 receipt_public_key_path: str | None = None,
                 expected_git_sha: str | None = None) -> dict[str, Any]:
    paired = evaluate_nare_metrics(_load(manifest_path), _load(metrics_path),
                                   n_bootstrap=n_bootstrap, seed=seed)
    paired["bootstrap_draws"] = n_bootstrap
    paired["bootstrap_seed"] = seed
    controls = _load(controls_path)
    if not isinstance(controls, dict):
        raise ValueError("NARE controls JSON must be an object")
    if bool(receipt_path) != bool(receipt_public_key_path):
        raise ValueError("NARE --receipt and --receipt-public-key must be supplied together")
    paired.update({key: controls.get(key, False) for key in
                   ("subgroups_passed", "controls_passed", "provenance_passed")})
    receipt = None
    receipt_valid = False
    if receipt_path is not None:
        if receipt_public_key_path is None:
            raise ValueError("NARE receipt validation requires --receipt-public-key")
        if expected_git_sha is None:
            raise ValueError("NARE receipt validation requires --git-sha")
        receipt = validate_receipt(
            receipt_path,
            {"manifest": manifest_path, "metrics": metrics_path, "controls": controls_path},
            receipt_public_key_path,
            expected_git_sha=expected_git_sha,
            required_artifacts=("manifest", "metrics", "controls"),
            expected_run_config={"bootstrap": n_bootstrap, "seed": seed},
        )
        receipt_valid = receipt["signature_valid"] is True
    paired["receipt_valid"] = receipt_valid
    paired["trusted_provenance"] = False
    report = {"paired": paired, "classification": classify_nare_result(paired)}
    if receipt is not None:
        report["evidence_receipt"] = receipt
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NARE natural-scene appearance gates")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--controls", required=True)
    parser.add_argument("--bootstrap", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out")
    parser.add_argument("--sync-supabase", action="store_true",
                        help="sync the frozen report to the HNCS Supabase registry")
    parser.add_argument("--dataset-slug",
                        help="Supabase dataset slug; defaults to the manifest directory name")
    parser.add_argument("--candidate-name",
                        help="candidate identifier required with --sync-supabase")
    parser.add_argument("--brand")
    parser.add_argument("--camera-model")
    parser.add_argument("--evidence-tier", choices=list("ABCDE"), default="C")
    parser.add_argument("--git-sha")
    parser.add_argument("--receipt",
                        help="signed evaluator receipt for the exact NARE artifacts")
    parser.add_argument("--receipt-public-key",
                        help="base64 Ed25519 public key for --receipt")
    args = parser.parse_args()
    if args.sync_supabase and not args.out:
        parser.error("--sync-supabase requires --out so the frozen report can be hashed")
    if args.sync_supabase and not args.candidate_name:
        parser.error("--sync-supabase requires --candidate-name")
    if bool(args.receipt) != bool(args.receipt_public_key):
        parser.error("--receipt and --receipt-public-key must be supplied together")

    report = build_report(args.manifest, args.metrics, args.controls,
                          n_bootstrap=args.bootstrap, seed=args.seed,
                          receipt_path=args.receipt,
                          receipt_public_key_path=args.receipt_public_key,
                          expected_git_sha=args.git_sha)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

    if args.sync_supabase:
        result = sync_evaluation_report(
            report,
            protocol="NARE",
            dataset_slug=args.dataset_slug or Path(args.manifest).parent.name,
            candidate_name=args.candidate_name,
            manifest_path=args.manifest,
            metrics_path=args.metrics,
            controls_path=args.controls,
            report_path=args.out,
            evidence_tier=args.evidence_tier,
            brand=args.brand,
            camera_model=args.camera_model,
            git_sha=args.git_sha,
            bootstrap_draws=args.bootstrap,
            bootstrap_seed=args.seed,
        )
        print(
            "Supabase sync: "
            f"{result['classification']}, scenes={result['n_scenes']}, "
            f"run_key={result['run_key']}"
        )


if __name__ == "__main__":
    main()
