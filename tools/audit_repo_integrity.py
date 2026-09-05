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
6. `assets/profiles/**/*.icc`, `*.dcp`가 `exiftool -validate`를 통과하는지.

**주의(2026-09-04에 실제로 겪은 것)**: `exiftool -validate -s3`는 정상일 때
`OK`만 출력한다. 임시판에서 "출력이 있으면 경고"로 짰다가 정상 13개를
전부 경고로 셌다 - 여기서는 출력이 정확히 `OK`인지로 판정한다.

이상이 하나라도 있으면 종료코드 1.

  python3 -m tools.audit_repo_integrity
"""
import json
import os
import re
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


def check_profiles():
    problems, n_json, n_bin = [], 0, 0
    for root, _, files in os.walk(PROFILES):
        for f in sorted(files):
            path = os.path.join(root, f)
            if f.endswith(".json"):
                n_json += 1
                try:
                    json.load(open(path, encoding="utf-8"))
                except Exception as e:
                    problems.append(f"JSON 파싱 실패: {f}: {e}")
            elif f.endswith((".icc", ".dcp")):
                n_bin += 1
                out = subprocess.run(["exiftool", "-validate", "-s3", path],
                                     capture_output=True, text=True,
                                     timeout=120).stdout.strip()
                # 정상은 정확히 "OK" - 출력 유무로 판정하면 안 된다(위 독스트링).
                if out != "OK":
                    problems.append(f"구조 검증 실패: {f}: {out or '(출력 없음)'}")
    print(f"  프로필 JSON {n_json}개 / ICC·DCP {n_bin}개 확인")
    return problems


def main():
    all_problems = []
    for title, fn in [("문서 등재", check_registration),
                      ("한/영 문서 짝", check_doc_pairs),
                      ("assets 참조", check_asset_refs),
                      ("프로필 무결성", check_profiles)]:
        print(f"[{title}]")
        found = fn()
        all_problems.extend(found)
        for p in found:
            print(f"  ※ {p}")
        print()

    if all_problems:
        print(f"이상 {len(all_problems)}건")
        sys.exit(1)
    print("이상 없음")


if __name__ == "__main__":
    main()
