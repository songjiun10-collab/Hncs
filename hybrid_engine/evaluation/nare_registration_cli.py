"""Create a NARE geometry-registration preflight report from a frozen manifest."""

import argparse
import json
from collections import Counter
from pathlib import Path

import cv2

from tools.fit.calibrate import load_neutral_render

from .nare import validate_nare_manifest
from .nare_registration import inspect_registration


def build_report(manifest_rows: list[dict], *, max_dim: int = 512) -> dict:
    validate_nare_manifest(manifest_rows)
    records = []
    for row in manifest_rows:
        if row["split"] not in {"evaluation", "lockbox"}:
            continue
        source = load_neutral_render(row["source_path"], max_dim=max_dim)
        target = cv2.imread(row["target_path"], cv2.IMREAD_COLOR)
        if target is None:
            diagnostic = {"passed": False, "failure_reason": "unreadable_target"}
        else:
            target = cv2.resize(target, (source.shape[1], source.shape[0]), interpolation=cv2.INTER_AREA)
            diagnostic = inspect_registration(source, target)
        records.append({"scene_id": row["scene_id"], **diagnostic})
    failures = Counter(record["failure_reason"] for record in records if not record["passed"])
    return {"max_dim": max_dim, "n_input": len(records),
            "n_passed": sum(record["passed"] for record in records),
            "failure_counts": dict(sorted(failures.items())), "records": records}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Preflight NARE RAW/JPEG registration")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--max-dim", type=int, default=512)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    report = build_report(manifest, max_dim=args.max_dim)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"NARE registration: {report['n_passed']}/{report['n_input']} passed")


if __name__ == "__main__":
    main()
