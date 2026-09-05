"""저장소 무결성 일괄 점검 - `/goal`의 "할 일 찾기" 탐색 순서 중
문서/코드 드리프트와 아티팩트 무결성에 해당하는 검사들을 한 번에 돌린다.

2026-09-04에 이 검사들을 임시 스크립트로 하나씩 돌렸는데, 앞으로도 새
브랜드/도구/프로필이 추가될 때마다 같은 걸 다시 확인하게 되므로 파일로
남긴다(`tools/CLAUDE.md`: 일회성 분석도 결과를 냈으면 파일로 저장).

**검사 항목**

1. `tools/`·`brands/`·`core/`의 모든 `*.py`가 `docs/project_structure.md`와
   `.en.md`에 등재돼 있는지 - `docs/CLAUDE.md`의 "새 파일 → 새 행, 양쪽
   언어" 규칙.
2. `docs/*.md` ↔ `docs/*.en.md` 짝이 다 있는지 - 같은 문서의 병행성 규칙.
   `CLAUDE.md`는 문서가 아니라 영역 규칙 파일이라 제외한다.
3. 두 `project_structure`의 표 행 수가 같은지 - 한쪽만 늘어난 커밋을 잡는다.
4. 코드가 문자열로 참조하는 `assets/**` 파일이 실제로 존재하는지.
5. `assets/profiles/*.json`이 파싱되는지.
6. `assets/profiles/**/*.dcp`, `*.icc`의 헤더를 직접 까서 보는 검사 - 아래
   "exiftool이 못 잡는 것" 참고. 외부 도구 없이 항상 돈다.
7. `assets/profiles/**/*.icc`, `*.dcp`가 `exiftool -validate`를 통과하는지.
   exiftool이 없는 환경에서는 이 검사만 건너뛰고 마지막 줄에 그 사실을
   적는다(6번은 그대로 돈다).

**주의(2026-09-04에 실제로 겪은 것)**: `exiftool -validate -s3`는 정상일 때
`OK`만 출력한다. 임시판에서 "출력이 있으면 경고"로 짰다가 정상 13개를
전부 경고로 셌다 - 여기서는 출력이 정확히 `OK`인지로 판정한다.

**exiftool이 못 잡는 것(6번을 따로 두는 이유)**: DCP는 표준 TIFF 매직(42)이
아니라 Adobe 전용 `0x4352`를 요구하는데, 매직이 틀린 파일에도 exiftool은
`Validate: OK`를 낸다(`tests/test_dcp_export.py`의
`test_header_uses_dcp_magic_not_standard_tiff_magic` 주석 - 2026-08-31에
Lightroom이 프로필을 못 읽던 실제 원인이었다). 즉 7번만으로는 그때 그
버그를 다시 배포해도 통과한다. 6번은 그 매직과 ICC의 헤더 크기 필드·태그
테이블을 순수 파이썬으로 직접 확인한다.

이상이 하나라도 있으면 종료코드 1.

  python3 -m tools.audit_repo_integrity
"""
import json
import os
import re
import shutil
import struct
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(BASE, "docs")
PROFILES = os.path.join(BASE, "hybrid_engine", "assets", "profiles")
CODE_DIRS = ["tools", "brands", "core"]
# 영역 규칙 파일이지 번역 대상 문서가 아니다.
NOT_BILINGUAL = {"CLAUDE.md"}
ASSET_REF = re.compile(r"[\"']([^\"']*assets/[^\"']+\.(?:json|dcp|icc|npy|cube))[\"']")


def check_registration():
    ko = open(os.path.join(DOCS, "project_structure.md"), encoding="utf-8").read()
    en = open(os.path.join(DOCS, "project_structure.en.md"), encoding="utf-8").read()
    problems = []
    for d in CODE_DIRS:
        files = sorted(f for f in os.listdir(os.path.join(BASE, d))
                       if f.endswith(".py") and f != "__init__.py")
        for f in files:
            if f"{d}/{f}" not in ko:
                problems.append(f"project_structure.md 미등재: {d}/{f}")
            if f"{d}/{f}" not in en:
                problems.append(f"project_structure.en.md 미등재: {d}/{f}")
        print(f"  {d}/: {len(files)}개 확인")
    ko_rows = len(re.findall(r"^\| `", ko, re.M))
    en_rows = len(re.findall(r"^\| `", en, re.M))
    print(f"  표 행 수: 한글 {ko_rows} / 영문 {en_rows}")
    if ko_rows != en_rows:
        problems.append(f"표 행 수 불일치: 한글 {ko_rows} vs 영문 {en_rows}")
    return problems


def check_doc_pairs():
    problems = []
    names = os.listdir(DOCS)
    for f in sorted(names):
        if f in NOT_BILINGUAL or not f.endswith(".md"):
            continue
        if f.endswith(".en.md"):
            if f[:-6] + ".md" not in names:
                problems.append(f"한글판 없음: {f}")
        elif f[:-3] + ".en.md" not in names:
            problems.append(f"영문판 없음: {f}")
    print(f"  docs/ 문서 {len([f for f in names if f.endswith('.md')])}개 확인")
    return problems


def check_asset_refs():
    problems, n_refs = [], 0
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs
                   if d not in {".git", "raw", "__pycache__", ".superpowers"}]
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(root, f)
            try:
                text = open(path, encoding="utf-8").read()
            except Exception:
                continue
            for ref in ASSET_REF.findall(text):
                if ref.startswith("/") or "{" in ref or "%" in ref:
                    continue
                n_refs += 1
                cand = (os.path.join(BASE, "hybrid_engine", ref)
                        if ref.startswith("assets/") else os.path.join(BASE, ref))
                if not os.path.exists(cand):
                    problems.append(f"참조 대상 없음: {os.path.relpath(path, BASE)} "
                                    f"-> {ref}")
    print(f"  assets 참조 {n_refs}건 확인")
    return problems


def _binary_profiles():
    for root, _, files in os.walk(PROFILES):
        for f in sorted(files):
            if f.endswith((".icc", ".dcp")):
                yield os.path.join(root, f)


def dcp_header_problems(path):
    """DCP 8바이트 헤더를 직접 확인. exiftool은 매직이 틀려도 `OK`를 내므로
    (위 독스트링) 배포 전에 이걸 통과해야 한다."""
    name = os.path.basename(path)
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(8)
    if len(head) < 8:
        return [f"헤더가 8바이트 미만: {name}"]
    byte_order, magic, first_ifd = struct.unpack("<2sHI", head)
    problems = []
    if byte_order != b"II":
        problems.append(f"리틀엔디안이 아님: {name}: {byte_order!r}")
    if magic != 0x4352:
        # 42는 표준 TIFF 매직 - Lightroom이 프로필을 못 읽던 그 버그다.
        problems.append(f"DCP 매직이 0x4352가 아님: {name}: 0x{magic:04X}"
                        f"{' (표준 TIFF 매직 42)' if magic == 42 else ''}")
    if not 8 <= first_ifd < size:
        problems.append(f"첫 IFD 오프셋이 파일 밖: {name}: {first_ifd} (크기 {size})")
    return problems


def icc_header_problems(path):
    """ICC 128바이트 헤더 + 태그 테이블이 파일 크기와 맞는지 확인."""
    name = os.path.basename(path)
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 132:
        return [f"헤더+태그 테이블보다 작음: {name}: {size}바이트"]
    problems = []
    declared = struct.unpack_from(">I", data, 0)[0]
    if declared != size:
        problems.append(f"헤더의 프로필 크기가 실제와 다름: {name}: "
                        f"{declared} vs {size}")
    if data[36:40] != b"acsp":
        problems.append(f"`acsp` 시그니처 없음: {name}: {data[36:40]!r}")
    ntags = struct.unpack_from(">I", data, 128)[0]
    if 132 + ntags * 12 > size:
        return problems + [f"태그 테이블이 파일 밖: {name}: {ntags}개"]
    for i in range(ntags):
        sig, offset, tag_size = struct.unpack_from(">4sII", data, 132 + i * 12)
        if offset + tag_size > size:
            problems.append(f"태그가 파일 밖: {name}: {sig!r} "
                            f"{offset}+{tag_size} > {size}")
    return problems


def check_profile_headers():
    problems, n_dcp, n_icc = [], 0, 0
    for path in _binary_profiles():
        if path.endswith(".dcp"):
            n_dcp += 1
            problems.extend(dcp_header_problems(path))
        else:
            n_icc += 1
            problems.extend(icc_header_problems(path))
    print(f"  DCP {n_dcp}개 / ICC {n_icc}개 헤더 확인")
    return problems


def check_profiles():
    """`None`을 반환하면 exiftool이 없어서 건너뛴 것 - 이상 없음과 다르다."""
    problems, n_json, n_bin = [], 0, 0
    for root, _, files in os.walk(PROFILES):
        for f in sorted(files):
            if f.endswith(".json"):
                n_json += 1
                try:
                    json.load(open(os.path.join(root, f), encoding="utf-8"))
                except Exception as e:
                    problems.append(f"JSON 파싱 실패: {f}: {e}")
    print(f"  프로필 JSON {n_json}개 확인")
    if shutil.which("exiftool") is None:
        print("  ※ exiftool 없음 - ICC·DCP 구조 검증 건너뜀(헤더 검사는 위에서 끝냄)")
        return None
    for path in _binary_profiles():
        n_bin += 1
        out = subprocess.run(["exiftool", "-validate", "-s3", path],
                             capture_output=True, text=True,
                             timeout=120).stdout.strip()
        # 정상은 정확히 "OK" - 출력 유무로 판정하면 안 된다(위 독스트링).
        if out != "OK":
            problems.append(f"구조 검증 실패: {os.path.basename(path)}: "
                            f"{out or '(출력 없음)'}")
    print(f"  ICC·DCP {n_bin}개 exiftool 검증")
    return problems


def main():
    all_problems, skipped = [], []
    for title, fn in [("문서 등재", check_registration),
                      ("한/영 문서 짝", check_doc_pairs),
                      ("assets 참조", check_asset_refs),
                      ("프로필 헤더", check_profile_headers),
                      ("프로필 무결성", check_profiles)]:
        print(f"[{title}]")
        found = fn()
        if found is None:
            skipped.append(title)
            found = []
        all_problems.extend(found)
        for p in found:
            print(f"  ※ {p}")
        print()

    if all_problems:
        print(f"이상 {len(all_problems)}건")
        sys.exit(1)
    # 안 돈 검사가 있으면 "이상 없음"이라고만 쓰면 안 된다 - 검증된 범위를
    # 실제보다 넓게 읽히게 한다.
    print("이상 없음" + (f" - 단 {len(skipped)}개 검사({', '.join(skipped)})는"
                        " exiftool이 없어 못 돌렸다" if skipped else ""))


if __name__ == "__main__":
    main()
