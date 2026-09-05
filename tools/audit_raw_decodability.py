"""`datasets/*/contributed/*/raw/`의 RAW가 설치된 LibRaw로 실제 열리는지
점검하고, 열리지 않는 파일을 사유와 함께 보고한다.

**왜 만들었나**: `tools/diagnose_neutral_render_offset_by_brand.py`를 돌리다
소니 `dpreview-a7v-preprod-2026-08` 62쌍 중 **40개가 디코드 실패**하는 걸
발견했다. 손상이 아니었다 - 파일은 전부 정상 TIFF 헤더(`II*\\0`)에
`exiftool -FileType`도 `ARW`다. 갈린 건 압축 방식이었다:

- `Sony Compressed RAW 2`(손실) 40개 -> 전부
  `LibRawFileUnsupportedError: Unsupported file format or not RAW file`
- `Sony Lossless Compressed RAW 2` 22개 -> 전부 정상 디코드

설치된 LibRaw는 0.22.1(rawpy 0.27.0)이고 a7 V의 손실 압축 ARW를 지원하지
않는다. 문제는 이게 **조용하다**는 점이다 - 대부분의 `evaluate_*.py`는
디코드 실패를 건너뛰기만 해서, 소니 작업이 62쌍이 아니라 22쌍에서
돌아가고 있었는데 아무 데도 그 숫자가 안 남았다.

새 바디를 받을 때마다 같은 일이 재발할 수 있으므로 파일로 남긴다. 전체
디코드가 아니라 **`rawpy.imread()` 열기만** 하므로 빠르다(지원하지 않는
포맷은 열기 단계에서 바로 예외가 난다).

이상이 있으면 종료코드 1. `--json <경로>`로 리포트를 저장한다.

  ~/.hncs-hybrid-venv312/bin/python3 -m tools.audit_raw_decodability
  ~/.hncs-hybrid-venv312/bin/python3 -m tools.audit_raw_decodability --json /tmp/raw_audit.json
"""
import argparse
import collections
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rawpy

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _raw_subtype(path):
    """압축 방식 등 실패 원인을 가르는 메타데이터. exiftool이 없으면 빈 문자열."""
    try:
        out = subprocess.run(
            ["exiftool", "-s3", "-SonyRawFileType", "-Compression", "-FileType", path],
            capture_output=True, text=True, timeout=30).stdout.strip().split("\n")
        return " / ".join(x.strip() for x in out if x.strip())
    except (OSError, subprocess.SubprocessError):
        return ""


def audit_set(raw_dir):
    files = sorted(f for f in glob.glob(os.path.join(raw_dir, "*"))
                   if os.path.isfile(f) and not os.path.basename(f).startswith("."))
    ok, failures = [], []
    for p in files:
        try:
            with rawpy.imread(p):
                pass
            ok.append(os.path.basename(p))
        except Exception as e:
            failures.append(dict(filename=os.path.basename(p),
                                 size_bytes=os.path.getsize(p),
                                 error=f"{type(e).__name__}: {str(e)[:120]}",
                                 raw_subtype=_raw_subtype(p)))
    return ok, failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    raw_dirs = sorted(d for d in glob.glob(
        os.path.join(BASE, "datasets", "*", "contributed", "*", "raw"))
        if os.path.isdir(d) and os.listdir(d))
    if not raw_dirs:
        print("raw/가 있는 세트 없음 - raw/는 git-ignore 대상이라 클론마다 다르다")
        return 0

    print(f"rawpy {rawpy.__version__} / LibRaw "
          f"{'.'.join(str(x) for x in rawpy.libraw_version)}\n")
    report, total_fail = [], 0
    for d in raw_dirs:
        rel = os.path.relpath(d, BASE)
        ok, failures = audit_set(d)
        total_fail += len(failures)
        mark = "※" if failures else " "
        print(f"{mark} {rel}: {len(ok)}개 정상, {len(failures)}개 실패")
        if failures:
            by_subtype = collections.Counter(f["raw_subtype"] for f in failures)
            for st, cnt in by_subtype.most_common():
                print(f"    {cnt}개  {st or '(메타데이터 없음)'}")
            errs = collections.Counter(f["error"].split(":")[0] for f in failures)
            for e, cnt in errs.most_common():
                print(f"    {cnt}개  {e}")
        report.append(dict(set=rel, n_ok=len(ok), n_failed=len(failures),
                           failures=failures))

    print(f"\n총 디코드 실패 {total_fail}건")
    if total_fail:
        print("주의: 대부분의 evaluate_*.py는 디코드 실패를 조용히 건너뛴다 - "
              "해당 세트의 실효 표본 수는 매니페스트 행 수가 아니라 위 '정상' 수다")
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({
                "rawpy_version": rawpy.__version__,
                "libraw_version": list(rawpy.libraw_version),
                "sets": report,
                "total_failed": total_fail,
            }, f, indent=2, ensure_ascii=False)
        print(f"리포트: {args.json_out}")
    return 1 if total_fail else 0


if __name__ == "__main__":
    sys.exit(main())
