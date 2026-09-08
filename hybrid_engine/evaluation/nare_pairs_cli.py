"""Create a strict NARE RAW/SOOC-JPEG pairing preflight report."""

import argparse
import json
from pathlib import Path

from .nare_pairs import scan_pair_directories


def main(argv=None):
    parser = argparse.ArgumentParser(description="Find exact metadata-matched NARE RAW/JPEG pairs")
    parser.add_argument("raw_dir", help="directory containing RAW files")
    parser.add_argument("jpeg_dir", help="directory containing SOOC JPEG files")
    parser.add_argument("--output", required=True, help="path for the JSON preflight report")
    args = parser.parse_args(argv)
    report = scan_pair_directories(args.raw_dir, args.jpeg_dir)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"strict NARE pairs: {len(report['pairs'])} / RAW {report['raw_input_count']} / JPEG {report['jpeg_input_count']}")
    raise SystemExit(0 if report["pairs"] else 2)


if __name__ == "__main__":
    main()
