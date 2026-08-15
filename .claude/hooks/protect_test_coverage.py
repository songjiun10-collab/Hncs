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
"simple and unabstracted is fine" for scratch/analysis code."""
import json
import os
import re
import subprocess
import sys

from _hook_common import allow, allow_with_override, bash_override, deny

HOOK_NAME = "protect_test_coverage"
SEVERITY = "HIGH"

_STMT_START = r"(?:^|&&|\|\||;|\n|\||\(|`|\bdo\b|\bthen\b|\belse\b)\s*"
_HEREDOC_RE = re.compile(r"<<-?\s*[\"']?(\w+)[\"']?.*?\n.*?^\1\b", re.DOTALL | re.MULTILINE)
_COMMIT_RE = re.compile(_STMT_START + r"git\s+commit\b")

_COVERAGE_EXPECTED_DIR_RE = re.compile(
    r"^(?:tools|brands|core)/[^/]+\.py$|"
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
    stripped = _HEREDOC_RE.sub("", command)
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

    override_reason = bash_override(HOOK_NAME, command)
    if override_reason:
        allow_with_override(HOOK_NAME, SEVERITY, HOOK_NAME, target, override_reason)
        return

    deny(
        HOOK_NAME,
        f"This commit adds a new file ({target}) with no test file staged "
        "alongside it (tests/CLAUDE.md: full suite green before every "
        "commit implies the new code is actually tested, not just "
        "written). To override: add a trailing `# HNCS-OVERRIDE: "
        f"{HOOK_NAME}: <reason>` comment to the commit command.",
        severity=SEVERITY,
    )


if __name__ == "__main__":
    main()
