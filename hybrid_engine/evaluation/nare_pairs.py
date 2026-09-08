"""Strict RAW/SOOC-JPEG capture pairing for NARE intake.

Pairing uses capture metadata rather than a filename stem: public sample sets
often rename, omit, or reorder files.  A key must occur exactly once in each
folder before it may become a NARE candidate.
"""

import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Iterable


_REQUIRED = ("DateTimeOriginal", "Make", "Model", "ISO")
_RAW_EXTENSIONS = {".3fr", ".arw", ".cr2", ".cr3", ".dng", ".nef", ".orf", ".raf", ".rw2"}
_JPEG_EXTENSIONS = {".jpg", ".jpeg"}


def _read_exif_many(paths: Iterable[str]) -> dict[str, dict]:
    """Read strict-key EXIF fields for a folder in one exiftool process."""
    paths = sorted(map(str, paths))
    if not paths:
        return {}
    completed = subprocess.run(
        ["exiftool", "-json", "-DateTimeOriginal", "-Make", "-Model", "-ISO", *paths],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if completed.returncode or not completed.stdout.strip():
        return {}
    records = json.loads(completed.stdout)
    return {str(record.get("SourceFile")): record for record in records}


def _capture_key(metadata: dict) -> tuple[str, str, str, str] | None:
    values = [str(metadata.get(field, "")).strip() for field in _REQUIRED]
    if not all(values):
        return None
    timestamp, make, model, iso = values
    return timestamp, make.lower(), model.lower(), iso


def find_strict_pairs(raw_paths: Iterable[str], jpeg_paths: Iterable[str]) -> dict:
    """Return only unambiguous RAW/JPEG pairs with an exact metadata key.

    A collision is deliberately reported rather than resolved by filename or
    ordering: burst frames and edited exports must never create a false NARE
    sample pair.
    """
    raw_paths, jpeg_paths = list(raw_paths), list(jpeg_paths)
    raw_by_key, jpeg_by_key = defaultdict(list), defaultdict(list)
    invalid_raw, invalid_jpeg = [], []
    all_paths = list(map(str, raw_paths)) + list(map(str, jpeg_paths))
    metadata = _read_exif_many(all_paths)
    for paths, destination, invalid in ((raw_paths, raw_by_key, invalid_raw),
                                        (jpeg_paths, jpeg_by_key, invalid_jpeg)):
        for path in sorted(map(str, paths)):
            key = _capture_key(metadata.get(path, {}))
            if key is None:
                invalid.append(path)
            else:
                destination[key].append(path)

    pairs, ambiguous = [], []
    for key in sorted(set(raw_by_key) | set(jpeg_by_key)):
        raws, jpegs = raw_by_key[key], jpeg_by_key[key]
        if len(raws) == len(jpegs) == 1:
            pairs.append({"raw_path": raws[0], "jpeg_path": jpegs[0]})
        elif raws or jpegs:
            ambiguous.append({"key": list(key), "raw_count": len(raws),
                              "jpeg_count": len(jpegs)})
    paired_raw = {pair["raw_path"] for pair in pairs}
    paired_jpeg = {pair["jpeg_path"] for pair in pairs}
    return {"pairs": pairs,
            "unmatched_raw": sorted(path for paths in raw_by_key.values() for path in paths
                                    if path not in paired_raw),
            "unmatched_jpeg": sorted(path for paths in jpeg_by_key.values() for path in paths
                                     if path not in paired_jpeg),
            "invalid_raw": invalid_raw, "invalid_jpeg": invalid_jpeg,
            "ambiguous_keys": ambiguous}


def scan_pair_directories(raw_dir: str | Path, jpeg_dir: str | Path) -> dict:
    """Scan conventional RAW and JPEG folders and attach their input counts."""
    raw_paths = [str(path) for path in Path(raw_dir).iterdir()
                 if path.is_file() and path.suffix.lower() in _RAW_EXTENSIONS]
    jpeg_paths = [str(path) for path in Path(jpeg_dir).iterdir()
                  if path.is_file() and path.suffix.lower() in _JPEG_EXTENSIONS]
    report = find_strict_pairs(raw_paths, jpeg_paths)
    return {"raw_input_count": len(raw_paths), "jpeg_input_count": len(jpeg_paths), **report}
