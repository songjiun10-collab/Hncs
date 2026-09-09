"""Create a strict NARE RAW/SOOC-JPEG pairing preflight report."""

import argparse
import json
from pathlib import Path

from .nare_pairs import build_nare_manifest, scan_pair_directories


def main(argv=None):
    parser = argparse.ArgumentParser(description="Find exact metadata-matched NARE RAW/JPEG pairs")
    parser.add_argument("raw_dir", help="directory containing RAW files")
    parser.add_argument("jpeg_dir", help="directory containing SOOC JPEG files")
    parser.add_argument("--output", required=True, help="path for the JSON preflight report")
    parser.add_argument("--manifest-out", help="write candidate NARE manifest JSON")
    parser.add_argument("--contributor", default="unknown")
    parser.add_argument("--lighting", default="unknown")
    parser.add_argument("--scene-type", default="unknown")
    parser.add_argument("--split", default="evaluation")
    parser.add_argument("--scene-prefix", default="scene")
    args = parser.parse_args(argv)
    report = scan_pair_directories(args.raw_dir, args.jpeg_dir)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.manifest_out:
        manifest = build_nare_manifest(
            report["pairs"], contributor=args.contributor, lighting=args.lighting,
            scene_type=args.scene_type, split=args.split, scene_prefix=args.scene_prefix,
        )
        Path(args.manifest_out).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    print(f"strict NARE pairs: {len(report['pairs'])} / RAW {report['raw_input_count']} / JPEG {report['jpeg_input_count']}")
    raise SystemExit(0 if report["pairs"] else 2)


if __name__ == "__main__":
    main()
