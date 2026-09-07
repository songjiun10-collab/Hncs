"""Run a NARE natural-scene evaluation from recorded JSON artifacts."""

import argparse
import json
from pathlib import Path
from typing import Any

from .nare import classify_nare_result, evaluate_nare_metrics


def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_report(manifest_path: str, metrics_path: str, controls_path: str,
                 n_bootstrap: int = 20_000, seed: int = 0) -> dict[str, Any]:
    paired = evaluate_nare_metrics(_load(manifest_path), _load(metrics_path),
                                   n_bootstrap=n_bootstrap, seed=seed)
    controls = _load(controls_path)
    if not isinstance(controls, dict):
        raise ValueError("NARE controls JSON must be an object")
    paired.update({key: controls.get(key, False) for key in
                   ("subgroups_passed", "controls_passed", "provenance_passed")})
    return {"paired": paired, "classification": classify_nare_result(paired)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NARE natural-scene appearance gates")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--controls", required=True)
    parser.add_argument("--bootstrap", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out")
    args = parser.parse_args()
    report = build_report(args.manifest, args.metrics, args.controls,
                          n_bootstrap=args.bootstrap, seed=args.seed)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
