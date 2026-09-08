"""Generate frozen NARE metrics for the supported Fuji Provia candidate."""

import argparse
import json
from pathlib import Path

from brands.fuji import apply_provia

from .nare_runner import run_nare_metrics


_CANDIDATES = {"provia": ("F0/Standard (Provia)", apply_provia)}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Measure NARE RAW/JPEG scene metrics")
    parser.add_argument("--manifest", required=True, help="frozen NARE JSON manifest")
    parser.add_argument("--candidate", choices=sorted(_CANDIDATES), required=True)
    parser.add_argument("--max-dim", type=int, default=512)
    parser.add_argument("--out", required=True, help="metrics JSON output")
    args = parser.parse_args(argv)
    picture_style, transform = _CANDIDATES[args.candidate]
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    metrics = run_nare_metrics(manifest, picture_style, candidate=transform,
                               max_dim=args.max_dim)
    Path(args.out).write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    print(f"NARE metrics: {len(metrics)} scenes, candidate={args.candidate}, max_dim={args.max_dim}")


if __name__ == "__main__":
    main()
