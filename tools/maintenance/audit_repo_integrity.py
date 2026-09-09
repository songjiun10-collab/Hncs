"""저장소 무결성 일괄 점검 - `/goal`의 "할 일 찾기" 탐색 순서 중
문서/코드 드리프트와 아티팩트 무결성에 해당하는 검사들을 한 번에 돌린다.

2026-09-04에 이 검사들을 임시 스크립트로 하나씩 돌렸는데, 앞으로도 새
브랜드/도구/프로필이 추가될 때마다 같은 걸 다시 확인하게 되므로 파일로
남긴다(`tools/CLAUDE.md`: 일회성 분석도 결과를 냈으면 파일로 저장).

**검사 항목**

1. `tools/`·`brands/`·`core/`의 모든 `*.py`가 `docs/project_structure.md`와
   `.en.md`에 등재돼 있는지 - `docs/CLAUDE.md`의 "새 파일 → 새 행, 양쪽
   언어" 규칙. 세 디렉토리 중 하나가 discovery에서 0개로 나오면 그 자체가
   이상(등재 누락이 아니라 discovery가 깨진 것) - `_code_files()`가 실제로
   두 번(brands/, tools/ 패키지화 때) 이 클래스로 조용히 무력화된 적 있다.
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

  python3 -m tools.maintenance.audit_repo_integrity
"""
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS = os.path.join(BASE, "docs")
PROFILES = os.path.join(BASE, "hybrid_engine", "assets", "profiles")
DATASETS = os.path.join(BASE, "datasets")
CODE_DIRS = ["tools", "brands", "core"]
# 영역 규칙 파일이지 번역 대상 문서가 아니다.
NOT_BILINGUAL = {"CLAUDE.md", "AGENTS.md"}
# 접두부에 공백을 허용하면 따옴표 안의 *명령 문자열*까지 경로로 잡힌다 -
# tests/test_hooks_never_touch_bash.py의 "printf x > hybrid_engine/assets/
# profiles/hasselblad_x2dii_chart.dcp"가 통째로 캡처돼 실재하는 파일을
# "참조 대상 없음"으로 오탐했다(2026-09-06). 경로로 쓸 수 있는 문자만 받는다.
ASSET_REF = re.compile(r"[\"']([^\"'\s]*assets/[^\"'\s]+\.(?:json|dcp|icc|npy|cube))[\"']")


def _code_files(root):
    """root 아래 모든 깊이의 *.py를 root 기준 상대경로로 돌려준다(재귀).

    이전엔 "root 바로 아래 + 한 단계 하위 디렉토리"까지만 봤다 - brands/를
    브랜드별 패키지로 묶은 뒤(brands/hasselblad/look.py 등) os.listdir만으론
    브랜드 파일이 하나도 안 잡혀 이 등재 검사가 통째로 무력화된 적이 있어서
    한 단계를 추가했었다. 그런데 2026-09-06에 tools/도
    tools/data/verify_contributed_pairs.py처럼 서브패키지로 나뉘면서, 그
    "한 단계"짜리 수정도 tools/data/x/y.py처럼 두 단계 이상 깊어지면 똑같이
    조용히 무력화될 수 있는 구조였다(지금은 실제로 2단계 이상인 파일이
    없어서 안 터졌을 뿐 - `check_asset_refs()`가 이미 쓰는 `os.walk`
    재귀 방식으로 통일해 이 클래스의 버그 자체를 없앤다)."""
    out = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith((".", "__"))]
        rel_dir = os.path.relpath(dirpath, root)
        for name in files:
            if name.endswith(".py") and name != "__init__.py":
                out.append(name if rel_dir == "." else f"{rel_dir}/{name}")
    return out


def check_registration():
    with open(os.path.join(DOCS, "project_structure.md"), encoding="utf-8") as f:
        ko = f.read()
    with open(os.path.join(DOCS, "project_structure.en.md"), encoding="utf-8") as f:
        en = f.read()
    problems = []
    for d in CODE_DIRS:
        files = sorted(_code_files(os.path.join(BASE, d)))
        # discovery가 조용히 0개를 찾고 "이상 없음"으로 통과하는 걸 막는
        # 구조적 불변식 - brands/ 패키지 이동 때 실제로 벌어졌던 실패 클래스
        # (위 _code_files() docstring 참고). 이 3개 디렉토리는 항상 코드가
        # 있으므로 0개는 등재 누락이 아니라 discovery 자체가 깨졌다는 뜻.
        if not files:
            problems.append(f"{d}/에서 *.py를 하나도 못 찾음 - discovery 로직이"
                            f" 깨졌을 가능성(등재 누락이 아님)")
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
                with open(path, encoding="utf-8") as source:
                    text = source.read()
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
                    with open(os.path.join(root, f), encoding="utf-8") as profile:
                        json.load(profile)
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


def check_nare_registered_metrics():
    """Ensure frozen registered NARE metrics retain registration scale metadata."""

    problems, n_files, n_rows = [], 0, 0
    for root, _, files in os.walk(DATASETS):
        for name in sorted(files):
            if not name.endswith(".json") or "registered_metrics_" not in name:
                continue
            path = os.path.join(root, name)
            n_files += 1
            try:
                with open(path, encoding="utf-8") as handle:
                    rows = json.load(handle)
            except (OSError, json.JSONDecodeError) as exc:
                problems.append(f"NARE metrics JSON 파싱 실패: {os.path.relpath(path, BASE)}: {exc}")
                continue
            if not isinstance(rows, list):
                problems.append(f"NARE metrics 행 목록 아님: {os.path.relpath(path, BASE)}")
                continue
            n_rows += len(rows)
            match = re.search(r"registered_metrics_(\d+)px", name)
            expected_scale = int(match.group(1)) if match else None
            scene_ids = []
            for row in rows:
                scene_id = row.get("scene_id") if isinstance(row, dict) else None
                scene_ids.append(scene_id)
                registration = row.get("registration") if isinstance(row, dict) else None
                scale = registration.get("long_edge_px") if isinstance(registration, dict) else None
                deltas = tuple(row.get(key) for key in
                               ("raw_delta_e00", "foundation_delta_e00", "candidate_delta_e00"))
                overlap = registration.get("overlap_fraction") if isinstance(registration, dict) else None
                correlation = registration.get("ecc_correlation") if isinstance(registration, dict) else None
                finite_metrics = all(isinstance(value, (int, float)) and not isinstance(value, bool)
                                     and math.isfinite(float(value)) and value >= 0 for value in deltas)
                valid_registration = (
                    isinstance(overlap, (int, float)) and not isinstance(overlap, bool)
                    and math.isfinite(float(overlap)) and 0 <= overlap <= 1
                    and isinstance(correlation, (int, float)) and not isinstance(correlation, bool)
                    and math.isfinite(float(correlation)) and -1 <= correlation <= 1
                )
                if (not isinstance(scene_id, str) or not scene_id.strip()
                        or type(scale) is not int or scale <= 0
                        or (expected_scale is not None and scale != expected_scale)):
                    problems.append(
                        f"NARE registration scale 누락: {os.path.relpath(path, BASE)}"
                    )
                    break
                if not finite_metrics or not valid_registration:
                    problems.append(
                        f"NARE metrics 값 무효: {os.path.relpath(path, BASE)}"
                    )
                    break
            if len(scene_ids) != len(set(scene_ids)):
                problems.append(
                    f"NARE metrics scene_id 중복: {os.path.relpath(path, BASE)}"
                )
    print(f"  등록 NARE metrics {n_files}개 / {n_rows}행 schema 확인")
    return problems


def check_nare_registered_reports():
    """Ensure frozen registered NARE reports record bootstrap configuration."""

    problems, n_files = [], 0
    for root, _, files in os.walk(DATASETS):
        for name in sorted(files):
            if not name.endswith(".json") or "registered_report_" not in name:
                continue
            path = os.path.join(root, name)
            n_files += 1
            try:
                with open(path, encoding="utf-8") as handle:
                    report = json.load(handle)
            except (OSError, json.JSONDecodeError) as exc:
                problems.append(f"NARE report JSON 파싱 실패: {os.path.relpath(path, BASE)}: {exc}")
                continue
            paired = report.get("paired") if isinstance(report, dict) else None
            draws = paired.get("bootstrap_draws") if isinstance(paired, dict) else None
            seed = paired.get("bootstrap_seed") if isinstance(paired, dict) else None
            n_scenes = paired.get("n_scenes") if isinstance(paired, dict) else None
            per_scene = paired.get("per_scene") if isinstance(paired, dict) else None
            scene_ids = [row.get("scene_id") for row in per_scene] if isinstance(per_scene, list) else None
            aggregate_values = (
                paired.get("mean_baseline"), paired.get("mean_candidate"),
                paired.get("mean_improvement"), paired.get("mean_improvement_pct"),
            ) if isinstance(paired, dict) else ()
            aggregate_finite = all(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(float(value)) for value in aggregate_values
            )
            per_scene_values = []
            if isinstance(per_scene, list):
                for row in per_scene:
                    if not isinstance(row, dict):
                        continue
                    values = tuple(row.get(key) for key in
                                   ("baseline_delta_e00", "candidate_delta_e00", "improvement"))
                    if all(isinstance(value, (int, float)) and not isinstance(value, bool)
                           and math.isfinite(float(value)) for value in values):
                        per_scene_values.append(values)
            arithmetic_ok = True
            if n_scenes and len(per_scene_values) == n_scenes and aggregate_finite:
                baseline_mean = sum(row[0] for row in per_scene_values) / n_scenes
                candidate_mean = sum(row[1] for row in per_scene_values) / n_scenes
                improvement_mean = sum(row[2] for row in per_scene_values) / n_scenes
                expected_pct = 100.0 * improvement_mean / baseline_mean if baseline_mean else None
                arithmetic_ok = (
                    baseline_mean >= 0 and candidate_mean >= 0
                    and all(abs(actual - expected) <= 1e-9 * max(1.0, abs(expected))
                            for actual, expected in (
                                (paired["mean_baseline"], baseline_mean),
                                (paired["mean_candidate"], candidate_mean),
                                (paired["mean_improvement"], improvement_mean),
                            ))
                    and (expected_pct is None or
                         abs(paired["mean_improvement_pct"] - expected_pct)
                         <= 1e-9 * max(1.0, abs(expected_pct)))
                    and all(row[0] >= 0 and row[1] >= 0
                            and abs(row[2] - (row[0] - row[1]))
                            <= 1e-9 * max(1.0, abs(row[0]), abs(row[1]))
                            for row in per_scene_values)
                )
            classification = report.get("classification") if isinstance(report, dict) else None
            label = classification.get("classification") if isinstance(classification, dict) else None
            ship_gate = classification.get("ship_gate_passed") if isinstance(classification, dict) else None
            if (type(draws) is not int or draws <= 0 or type(seed) is not int
                    or type(n_scenes) is not int or n_scenes < 0
                    or not isinstance(per_scene, list) or len(per_scene) != n_scenes
                    or any(not isinstance(row, dict) or not isinstance(row.get("scene_id"), str)
                           or not row["scene_id"].strip() for row in per_scene or [])
                    or len(scene_ids or []) != len(set(scene_ids or []))
                    or (n_scenes > 0 and (not aggregate_finite or len(per_scene_values) != n_scenes
                                          or not arithmetic_ok))
                    or label not in {"Verified", "Supported", "Inconclusive", "Rejected", "Exploratory"}
                    or type(ship_gate) is not bool):
                problems.append(
                    f"NARE report schema 누락: {os.path.relpath(path, BASE)}"
                )
            metrics_name = name.replace("registered_report_", "registered_metrics_", 1)
            metrics_path = os.path.join(root, metrics_name)
            if os.path.isfile(metrics_path) and isinstance(per_scene, list):
                try:
                    with open(metrics_path, encoding="utf-8") as handle:
                        metric_rows = json.load(handle)
                except (OSError, json.JSONDecodeError) as exc:
                    problems.append(f"NARE metrics JSON 파싱 실패: {os.path.relpath(metrics_path, BASE)}: {exc}")
                else:
                    metric_ids = [row.get("scene_id") for row in metric_rows] if isinstance(metric_rows, list) else None
                    if metric_ids is None or metric_ids != scene_ids:
                        problems.append(
                            f"NARE report/metrics scene 불일치: {os.path.relpath(path, BASE)}"
                        )
    print(f"  등록 NARE reports {n_files}개 bootstrap schema 확인")
    return problems


def check_nare_selection_sensitivity():
    """Validate frozen NARE registration-selection sensitivity artifacts."""

    problems, n_files = [], 0
    schema = "hncs.nare-registration-selection-sensitivity/v1"
    sha_pattern = re.compile(r"^[0-9a-fA-F]{40}$")

    def finite(value):
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(float(value)))

    def nonnegative(value):
        return finite(value) and float(value) >= 0

    def ci(value):
        return (isinstance(value, list) and len(value) == 2
                and all(finite(item) for item in value) and value[0] <= value[1])

    def file_sha256(path):
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def close(actual, expected):
        return finite(actual) and finite(expected) \
            and abs(float(actual) - float(expected)) <= 1e-9 * max(1.0, abs(float(expected)))

    for root, _, files in os.walk(DATASETS):
        for name in sorted(files):
            if not name.startswith("nare_") or "registration_selection_sensitivity_" not in name \
                    or not name.endswith(".json"):
                continue
            path = os.path.join(root, name)
            n_files += 1
            try:
                with open(path, encoding="utf-8") as handle:
                    artifact = json.load(handle)
            except (OSError, json.JSONDecodeError) as exc:
                problems.append(f"NARE sensitivity JSON 파싱 실패: {os.path.relpath(path, BASE)}: {exc}")
                continue
            gate = artifact.get("registration_gate") if isinstance(artifact, dict) else None
            sensitivity = artifact.get("selection_sensitivity") if isinstance(artifact, dict) else None
            reports = artifact.get("post_registration_current_reports") if isinstance(artifact, dict) else None
            valid = isinstance(artifact, dict) and artifact.get("schema") == schema \
                and isinstance(artifact.get("source_develop_sha"), str) \
                and sha_pattern.fullmatch(artifact["source_develop_sha"]) is not None
            if valid and os.path.exists(os.path.join(BASE, ".git")):
                commit_check = subprocess.run(
                    ["git", "cat-file", "-e", artifact["source_develop_sha"] + "^{commit}"],
                    cwd=BASE, capture_output=True, check=False,
                )
                valid = commit_check.returncode == 0
            inputs = artifact.get("inputs") if isinstance(artifact, dict) else None
            required_inputs = ("exploratory_metrics_512px", "registration_512px",
                               "registered_report_512px", "registered_report_1024px")
            if isinstance(inputs, dict):
                artifact_dir = os.path.realpath(root)
                input_hashes = artifact.get("input_sha256") if isinstance(artifact, dict) else None
                valid = valid and isinstance(input_hashes, dict)
                for key in required_inputs:
                    value = inputs.get(key)
                    expected_hash = input_hashes.get(key) if isinstance(input_hashes, dict) else None
                    if (not isinstance(value, str) or not value.strip() or os.path.isabs(value)
                            or not isinstance(expected_hash, str)
                            or re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash) is None):
                        valid = False
                        continue
                    candidate = os.path.realpath(os.path.join(root, value))
                    try:
                        hash_matches = file_sha256(candidate) == expected_hash.lower()
                    except OSError:
                        hash_matches = False
                    valid = valid and os.path.commonpath((artifact_dir, candidate)) == artifact_dir \
                        and os.path.isfile(candidate) and hash_matches
            else:
                valid = False
            if isinstance(gate, dict):
                counts = tuple(gate.get(key) for key in
                               ("n_input", "n_passed", "n_failed", "n_aspect_ratio_failed", "n_geometry_failed"))
                valid = valid and all(type(value) is int and value >= 0 for value in counts) \
                    and counts[1] + counts[2] == counts[0] \
                    and counts[3] + counts[4] == counts[2]
            else:
                valid = False
            if isinstance(sensitivity, dict):
                p_value = sensitivity.get("two_sided_permutation_p")
                valid = valid and finite(sensitivity.get("pass_minus_fail_mean_absolute_improvement_delta_e00")) \
                    and ci(sensitivity.get("bootstrap_95ci")) \
                    and finite(p_value) and 0 <= p_value <= 1 \
                    and type(sensitivity.get("bootstrap_draws")) is int \
                    and sensitivity["bootstrap_draws"] > 0 \
                    and type(sensitivity.get("permutation_draws")) is int \
                    and sensitivity["permutation_draws"] > 0 \
                    and type(sensitivity.get("seed_absolute")) is int \
                    and type(sensitivity.get("seed_relative")) is int
            else:
                valid = False
            pre = artifact.get("pre_registration_exploratory_metrics") if isinstance(artifact, dict) else None
            if isinstance(pre, dict):
                pre_values = {}
                for group in ("all_51", "registration_pass_32", "registration_fail_19"):
                    row = pre.get(group)
                    if not isinstance(row, dict):
                        valid = False
                        continue
                    valid = valid and all(nonnegative(row.get(key)) for key in
                                         ("mean_baseline_delta_e00", "mean_candidate_delta_e00",
                                          "mean_absolute_improvement_delta_e00")) \
                        and finite(row.get("aggregate_relative_improvement_pct")) \
                        and type(row.get("wins")) is int and row["wins"] >= 0 \
                        and type(row.get("losses")) is int and row["losses"] >= 0 \
                        and close(row["mean_absolute_improvement_delta_e00"],
                                  row["mean_baseline_delta_e00"] - row["mean_candidate_delta_e00"]) \
                        and (row["mean_baseline_delta_e00"] == 0
                             or close(row["aggregate_relative_improvement_pct"],
                                      100.0 * row["mean_absolute_improvement_delta_e00"] /
                                      row["mean_baseline_delta_e00"]))
                    pre_values[group] = row
                if (isinstance(sensitivity, dict)
                        and all(group in pre_values for group in ("registration_pass_32", "registration_fail_19"))):
                    valid = valid and close(
                        sensitivity.get("pass_minus_fail_mean_absolute_improvement_delta_e00"),
                        pre_values["registration_pass_32"]["mean_absolute_improvement_delta_e00"]
                        - pre_values["registration_fail_19"]["mean_absolute_improvement_delta_e00"])
            else:
                valid = False
            if isinstance(reports, dict):
                for scale in ("512px", "1024px"):
                    report = reports.get(scale)
                    valid = valid and isinstance(report, dict) \
                        and type(report.get("n_scenes")) is int and report["n_scenes"] > 0 \
                        and all(nonnegative(report.get(key)) for key in
                                ("mean_baseline_delta_e00", "mean_candidate_delta_e00",
                                 "mean_absolute_improvement_delta_e00")) \
                        and finite(report.get("aggregate_relative_improvement_pct")) \
                        and ci(report.get("bootstrap_95ci_absolute_improvement")) \
                        and close(report["mean_absolute_improvement_delta_e00"],
                                  report["mean_baseline_delta_e00"] - report["mean_candidate_delta_e00"]) \
                        and (report["mean_baseline_delta_e00"] == 0
                             or close(report["aggregate_relative_improvement_pct"],
                                      100.0 * report["mean_absolute_improvement_delta_e00"] /
                                      report["mean_baseline_delta_e00"]))
            else:
                valid = False
            if not valid:
                problems.append(f"NARE sensitivity schema 누락: {os.path.relpath(path, BASE)}")
    print(f"  NARE sensitivity {n_files}개 schema 확인")
    return problems


def main():
    all_problems, skipped = [], []
    for title, fn in [("문서 등재", check_registration),
                      ("한/영 문서 짝", check_doc_pairs),
                      ("assets 참조", check_asset_refs),
                      ("NARE metrics", check_nare_registered_metrics),
                      ("NARE reports", check_nare_registered_reports),
                      ("NARE sensitivity", check_nare_selection_sensitivity),
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
