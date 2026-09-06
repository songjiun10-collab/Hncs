#!/usr/bin/env python3
"""PreToolUse hook (matcher: Bash), HIGH severity. Before `git commit`,
checks whether the commit adds a brand-new `.py` file under
tools/brands/core/hybrid_engine (excluding hybrid_engine/research/, which
is explicitly "mirrors for experiments only", and excluding
calibrate_profile_<brand>.py copies, which share coverage via
calibrate_profile.py's own tests per this session's dedup refactor) with
no test file staged in the same commit.

**Deliberately narrow scope**: this does NOT fire on every commit that
touches source without touching tests/ - that would false-positive on
routine, already-covered refactors (e.g. this session's own
calibrate_profile_*.py and brands/*_learned.py dedup commits touched no
test files, because existing tests already covered the behavior and a
standalone verification script proved it byte-identical). It only fires
on a **brand-new file with zero test coverage ever written for it** - the
specific "unconscious slide" this guard exists to catch, not "this diff
happened to not need a new test."

Override: trailing `# HNCS-OVERRIDE: protect_test_coverage: <reason>`
comment - e.g. a one-off script explicitly exempted by tools/CLAUDE.md's
"simple and unabstracted is fine" for scratch/analysis code.

**추가 (2026-08-19, 2-Agent Consensus)**: override 체크 다음, 기존
high_tier_decision() fallback 전에 consensus 확인 단계가 하나 더 생겼다
- 자세한 설계는 `_hook_common.py`의 `write_consensus_verdict()`/
`consensus_verdict()` docstring 참고. 안 쓰면(컨트롤러가 2-agent 디스패치를
아예 안 하면) 기존 동작과 완전히 동일.

**정정(2026-08-20, README "알려진 한계" 2차 라운드 #4 - 실측 결함
수정)**: `eval "git commit ..."`가 `_STMT_START`의 문 시작 위치
요건을 못 맞춰서 완전히 안 걸렸다 - `_hook_common.unwrap_eval()`로
고침."""
import json
import os
import re
import subprocess
import sys

from _hook_common import (allow, allow_with_consensus, allow_with_override,
                           bash_override, consensus_verdict, high_tier_decision,
                           require_decision_or_deny, unwrap_eval)

HOOK_NAME = "protect_test_coverage"
SEVERITY = "HIGH"

_STMT_START = r"(?:^|&&|\|\||;|\n|\||\(|`|\bdo\b|\bthen\b|\belse\b)\s*"
_HEREDOC_RE = re.compile(r"<<-?\s*[\"']?(\w+)[\"']?.*?\n.*?^\1\b", re.DOTALL | re.MULTILINE)
_COMMIT_RE = re.compile(_STMT_START + r"git\s+commit\b")

# 2026-09-06: brands/를 브랜드별 패키지로 옮기면서(brands/hasselblad.py ->
# brands/hasselblad/look.py) brands가 tools|core와 같은 가지에 묶여 있던
# `[^/]+\.py$`에 더는 걸리지 않게 됐다 - 브랜드 파일을 고치고 테스트 없이
# 커밋해도 이 훅이 못 잡는 상태였다. brands만 가지를 분리해 한 단계 하위
# 디렉토리를 허용하고, tools/core는 원래 동작 그대로 둔다.
_COVERAGE_EXPECTED_DIR_RE = re.compile(
    r"^(?:tools|core)/[^/]+\.py$|"
    r"^brands/(?:[^/]+/)?[^/]+\.py$|"
    r"^hybrid_engine/(?!research/)[^/]+\.py$"
)
_CALIBRATE_PROFILE_COPY_RE = re.compile(
    r"^hybrid_engine/calibrate_profile_[^/]+\.py$")


def read_input():
    return json.load(sys.stdin)


def staged_files(status_flag=None):
    """Returns staged file paths (relative to repo root), optionally
    filtered to a specific git status flag (e.g. "A" for added)."""
    try:
        out = subprocess.run(["git", "diff", "--cached", "--name-status"],
                              capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    paths = []
    for line in out.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        flag, path = parts[0], parts[-1]
        if status_flag is None or flag.startswith(status_flag):
            paths.append(path)
    return paths


def uncovered_new_file(added_paths, all_staged_paths):
    """Returns the first newly-added source path that looks like it needs
    test coverage and has none staged in this commit, else None."""
    has_test_change = any(p.startswith("tests/") for p in all_staged_paths)
    if has_test_change:
        return None
    for path in added_paths:
        if _CALIBRATE_PROFILE_COPY_RE.match(path):
            continue
        if _COVERAGE_EXPECTED_DIR_RE.match(path):
            return path
    return None


def main():
    data = read_input()
    if data.get("tool_name") != "Bash":
        allow()
        return
    command = str((data.get("tool_input") or {}).get("command", ""))
    stripped = unwrap_eval(_HEREDOC_RE.sub("", command))
    if not _COMMIT_RE.search(stripped):
        allow()
        return

    added = staged_files(status_flag="A")
    all_staged = staged_files()
    if added is None or all_staged is None:
        allow()  # not a git repo, or git unavailable
        return

    target = uncovered_new_file(added, all_staged)
    if target is None:
        allow()
        return

    decision = require_decision_or_deny(
        HOOK_NAME, SEVERITY, target,
        f"This commit adds a new file ({target}) with no test file staged alongside it.")
    if decision is None:
        return

    override_reason = bash_override(HOOK_NAME, command)
    if override_reason:
        allow_with_override(HOOK_NAME, SEVERITY, HOOK_NAME, target, override_reason,
                             decision=decision)
        return

    verdict = consensus_verdict(HOOK_NAME, target)
    if verdict in ("agree_safe", "agree_risky"):
        allow_with_consensus(HOOK_NAME, SEVERITY, HOOK_NAME, target, verdict, decision=decision)
        return

    high_tier_decision(
        HOOK_NAME, SEVERITY,
        f"This commit adds a new file ({target}) with no test file staged "
        "alongside it (tests/CLAUDE.md: full suite green before every "
        "commit implies the new code is actually tested, not just "
        "written). To override: add a trailing `# HNCS-OVERRIDE: "
        f"{HOOK_NAME}: <reason>` comment to the commit command.",
        data, target=target, decision=decision,
    )


if __name__ == "__main__":
    main()
