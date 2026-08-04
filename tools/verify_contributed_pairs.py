"""
기여 데이터셋(datasets/<브랜드>/contributed/<세트>/) 자동 검증 CLI.
규격은 datasets/hasselblad/contributed/README.md 참고(브랜드 무관 공통
스키마 - datasets/leica/contributed/README.md는 그 스키마를 그대로
가리킨다).

  python3 -m tools.verify_contributed_pairs datasets/hasselblad/contributed/kmichels-x2dii-2026-07
  python3 -m tools.verify_contributed_pairs datasets/leica/contributed/<세트> --make Leica

--make 기본값은 Hasselblad(기존 호출 하위호환) - EXIF Make가 이 문자열을
포함해야 통과한다."""
import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.analyze import _check_genuine_bytes

REQUIRED_COLUMNS = {"filename_raw", "filename_jpeg", "camera", "lens", "iso",
                     "wb_setting", "scene_type", "download_url"}
PAIR_SYNC_TOLERANCE_SEC = 2
DEFAULT_EXPECTED_MAKE = "Hasselblad"


def _exif(path, tags):
    out = subprocess.run(["exiftool", "-json"] + [f"-{t}" for t in tags] + [path],
                          capture_output=True, text=True, timeout=60)
    if out.returncode != 0 or not out.stdout.strip():
        return {}
    return json.loads(out.stdout)[0]


def _parse_exif_datetime(value):
    """exiftool DateTimeOriginal - 'YYYY:mm:dd HH:MM:SS' 또는 ISO 형태 둘 다 수용."""
    if not value:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(value)[:19], fmt)
        except ValueError:
            continue
    return None


def _model_matches(exif_model, manifest_camera):
    """EXIF Model과 manifest camera 표기가 같은 카메라를 가리키는지 - 공백/
    하이픈 차이('X2D II 100C' vs 'X2DII-100c')를 무시하고 비교."""
    def norm(s):
        return "".join((s or "").lower().split()).replace("-", "")
    a, b = norm(exif_model), norm(manifest_camera)
    return bool(a) and (a in b or b in a)


def verify_row(set_dir, row, expected_make=DEFAULT_EXPECTED_MAKE):
    """manifest 한 행 검증 - 문제 목록(비면 통과)을 반환. expected_make는
    EXIF Make에 포함돼야 할 제조사명(기본 Hasselblad, 대소문자 무관)."""
    problems = []

    raw_path = os.path.join(set_dir, "raw", row["filename_raw"])
    jpeg_path = os.path.join(set_dir, "jpeg", row["filename_jpeg"])
    for label, path in (("raw", raw_path), ("jpeg", jpeg_path)):
        if not os.path.exists(path):
            problems.append(f"{label} 파일 없음: {path}")
    if problems:
        return problems  # 파일이 없으면 나머지 검증 불가

    # EXIF Make/Model 대조
    for label, path in (("raw", raw_path), ("jpeg", jpeg_path)):
        d = _exif(path, ["Make", "Model"])
        if expected_make.lower() not in (d.get("Make") or "").lower():
            problems.append(f"{label} EXIF Make가 {expected_make}가 아님: {d.get('Make')!r}")
        if not _model_matches(d.get("Model"), row["camera"]):
            problems.append(
                f"{label} EXIF Model({d.get('Model')!r})이 manifest camera({row['camera']!r})와 불일치")

    # 페어 동기(동시 촬영) 검증
    dt_raw = _parse_exif_datetime(_exif(raw_path, ["DateTimeOriginal"]).get("DateTimeOriginal"))
    dt_jpeg = _parse_exif_datetime(_exif(jpeg_path, ["DateTimeOriginal"]).get("DateTimeOriginal"))
    if dt_raw is None or dt_jpeg is None:
        problems.append("DateTimeOriginal을 못 읽음 - 페어 동기 검증 불가")
    elif abs((dt_raw - dt_jpeg).total_seconds()) > PAIR_SYNC_TOLERANCE_SEC:
        problems.append(
            f"raw/jpeg 촬영시각 차이 {abs((dt_raw - dt_jpeg).total_seconds()):.0f}초 "
            f"(허용 {PAIR_SYNC_TOLERANCE_SEC}초) - 같은 셔터가 아닐 수 있음")

    # 편집 오염 검사 (jpeg만 - raw는 정의상 무가공)
    with open(jpeg_path, "rb") as f:
        if not _check_genuine_bytes(f.read()):
            problems.append("jpeg EXIF Software에 편집 도구(Photoshop/Lightroom류) 흔적")

    return problems


def main():
    parser = argparse.ArgumentParser(description="기여 데이터셋 manifest 검증")
    parser.add_argument("set_dir", help="datasets/<브랜드>/contributed/<세트> 경로")
    parser.add_argument("--make", default=DEFAULT_EXPECTED_MAKE,
                         help=f"기대하는 EXIF Make (기본 {DEFAULT_EXPECTED_MAKE})")
    args = parser.parse_args()
    set_dir = args.set_dir

    manifest_path = os.path.join(set_dir, "manifest.csv")
    if not os.path.exists(manifest_path):
        print(f"manifest.csv 없음: {manifest_path}")
        sys.exit(1)

    with open(manifest_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    missing_cols = REQUIRED_COLUMNS - set(rows[0].keys() if rows else [])
    if missing_cols:
        print(f"manifest에 필수 컬럼 누락: {sorted(missing_cols)}")
        sys.exit(1)

    passed, failed = 0, 0
    for i, row in enumerate(rows):
        problems = verify_row(set_dir, row, expected_make=args.make)
        status = "PASS" if not problems else "FAIL"
        print(f"[{i + 1}/{len(rows)}] {row['filename_raw']} + {row['filename_jpeg']}: {status}")
        for p in problems:
            print(f"    - {p}")
        if problems:
            failed += 1
        else:
            passed += 1

    print(f"\n검증 통과 {passed} / 실패 {failed} (총 {len(rows)})")
    sys.exit(0 if failed == 0 else 2)


if __name__ == "__main__":
    main()
