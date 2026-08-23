#!/usr/bin/env python3
"""PreToolUse hook (matcher: Bash), CRITICAL severity. Blocks locally-
destructive commands that discard data with no recovery path other than
git reflog/backups the user may not have: `rm -r`/`-f` combos outside
scratch dirs, `git reset --hard`, `git clean` with a force flag, and
`git branch -D`. Force-push is handled by `protect_push_safety.py`
instead (push-specific authorship/force logic already lived there before
this severity redesign - not duplicated here).

Override: trailing `# HNCS-OVERRIDE: protect_destructive: <reason>`
comment on the command, same mechanism as `protect_never_touch.py`'s
Bash path - see `_hook_common.py` module docstring for the full
override-tier design.

**정정(2026-08-20, README "알려진 한계" 2차 라운드 #2/#3/#6 - 3개 실측
결함 수정, 그리고 #2에 대한 원래 서술 정정)**: (1) heredoc 본문을
무조건 지우던 게 `bash - <<'EOF'\nrm -rf ...\nEOF`처럼 셸에 직접
넘겨진(진짜 셸 문법으로 파싱되는) heredoc 안의 실제 `rm -rf`까지
놓쳤다 - `_hook_common.strip_prose_heredocs()`(인터프리터에 넘겨진
heredoc은 안 지움)로 교체해서 고쳤다. **원래 README 2차 라운드 #2가
든 예시(`python3 - <<'PY' ... shutil.rmtree(...) ... PY`)는 재검토
결과 부정확했다** - `_RM_RE`는 `_STMT_START`(진짜 셸 문법 경계 가정)
기반이라, heredoc을 안 지워도 Python 문자열 리터럴 안에 박힌 셸
텍스트(`os.system("rm -rf ...")` 포함)는 여전히 못 잡는다 - 그
문자열은 shell 파서가 아니라 Python 런타임이 나중에 해석하는 데이터라
`_STMT_START`가 요구하는 위치에 있지 않기 때문. heredoc 스트리핑
버그는 실재하지만, 닫히는 범위는 "셸에 직접 넘겨진 heredoc" 한정이고
"인터프리터 문자열 안에 셸 명령이 박힌 경우"는 이 훅의 정규식
어휘(`rm`/`git reset --hard`/`git clean -f`/`git branch -D`, 전부
셸 명령 자체를 찾는 패턴)로는 원천적으로 대응 범위 밖 - 별도 과제.
(2) `_SCRATCH_PATH_RE`가 부분문자열
매칭이라 `rm -rf ./scratchpad/../not_scratch_dir`처럼 `../`로 실제로는
scratchpad 밖을 지우는 명령도 "scratch 경로다"로 오판하고 통과시켰다 -
`os.path.normpath` 후 접두사 비교로 교체. (3) `find ... -delete`가
`rm -rf`와 동등하게 파괴적인데 전혀 커버 안 됐다 - 추가."""
import json
import os
import re
import sys

from _hook_common import (allow, allow_with_override, bash_override, deny,
                           is_subagent_call, require_decision_or_deny,
                           strip_prose_heredocs)

HOOK_NAME = "protect_destructive"
SEVERITY = "CRITICAL"

_STMT_START = r"(?:^|&&|\|\||;|\n|\||\(|`|\bdo\b|\bthen\b|\belse\b)\s*"

# rm -r/-f in any combination (long or short form), with the target -
# only flagged if none of the targets look like a scratch/temp path.
_RM_RE = re.compile(
    _STMT_START + r"rm\s+(?P<args>[^\n;&|`]*)"
)
_RM_RECURSIVE_RE = re.compile(r"(^|\s)(-\w*[rR]\w*|--recursive)(\s|$)")
_RM_FORCE_RE = re.compile(r"(^|\s)(-\w*f\w*|--force)(\s|$)")
_FIND_DELETE_RE = re.compile(_STMT_START + r"find\s+(?P<args>[^\n;&|`]*?)-delete\b")
_SCRATCH_PREFIXES = ("/tmp/", "/scratchpad/", "scratchpad/")

_GIT_RESET_HARD_RE = re.compile(_STMT_START + r"git\s+reset\s+.*--hard\b")
_GIT_CLEAN_FORCE_RE = re.compile(
    _STMT_START + r"git\s+clean\s+(?:(?!\bgit\b)[^\n;&|`])*?"
    r"(-\w*f\w*|--force)\b")
_GIT_BRANCH_DELETE_FORCE_RE = re.compile(
    _STMT_START + r"git\s+branch\s+(?:(?!\bgit\b)[^\n;&|`])*?"
    r"(-D\b|--delete\s+--force\b|-\w*D\w*)")


def read_input():
    return json.load(sys.stdin)


def _all_targets_under_scratch(args):
    """True if every non-flag token in `args` normalizes to a path under
    /tmp/ or a scratchpad/ dir - normpath-based so `./scratchpad/../x`
    (which contains the substring "./scratchpad/" but actually resolves
    outside it) isn't mistaken for a safe scratch path."""
    tokens = [t for t in args.split() if t and not t.startswith("-")]
    if not tokens:
        return False
    for token in tokens:
        normalized = os.path.normpath(token).replace(os.sep, "/") + "/"
        if not normalized.startswith(_SCRATCH_PREFIXES) and "/scratchpad/" not in normalized:
            return False
    return True


def destructive_reason(command):
    """Returns a human-readable reason string if `command` looks
    destructive, else None."""
    command = strip_prose_heredocs(command)

    for m in _RM_RE.finditer(command):
        args = m.group("args")
        if _RM_RECURSIVE_RE.search(args) and _RM_FORCE_RE.search(args):
            if _all_targets_under_scratch(args):
                continue
            return ("`rm` with both a recursive and a force flag, on a path "
                    "that isn't under /tmp/ or a scratchpad/ dir - this "
                    "permanently deletes files with no undo.")

    for m in _FIND_DELETE_RE.finditer(command):
        if _all_targets_under_scratch(m.group("args")):
            continue
        return ("`find ... -delete` is as destructive as `rm -rf` on "
                "whatever it matches, on a path that isn't under /tmp/ or "
                "a scratchpad/ dir - this permanently deletes files with "
                "no undo.")

    if _GIT_RESET_HARD_RE.search(command):
        return ("`git reset --hard` discards uncommitted changes with no "
                "recovery path other than reflog (which doesn't cover "
                "untracked files).")

    if _GIT_CLEAN_FORCE_RE.search(command):
        return ("`git clean` with a force flag permanently deletes "
                "untracked files/dirs - no undo.")

    if _GIT_BRANCH_DELETE_FORCE_RE.search(command):
        return ("`git branch -D` force-deletes a branch even if it has "
                "unmerged commits - those commits become unreachable.")

    return None


def main():
    data = read_input()
    if data.get("tool_name") != "Bash":
        allow()
        return
    command = str((data.get("tool_input") or {}).get("command", ""))

    reason = destructive_reason(command)
    if reason is None:
        allow()
        return

    decision = require_decision_or_deny(HOOK_NAME, SEVERITY, command, reason)
    if decision is None:
        return

    if is_subagent_call(data):
        deny(
            HOOK_NAME,
            f"{reason} 이 호출은 서브에이전트발이라(agent_id 있음) override를 "
            "받지 않음 - CRITICAL 등급에서 override는 self-servable(bash "
            "주석은 서브에이전트 스스로도 쓸 수 있음)이라는 게 가장 치명적인 "
            "지점이라, 파괴적 명령의 서브에이전트발 시도는 override 불가로 "
            "막는다. 컨트롤러가 직접 실행할 것.",
            severity=SEVERITY, target=command, decision=decision,
        )
        return

    override_reason = bash_override(HOOK_NAME, command)
    if override_reason:
        allow_with_override(HOOK_NAME, SEVERITY, HOOK_NAME, command, override_reason,
                             decision=decision)
        return

    deny(
        HOOK_NAME,
        f"{reason} This hook denies by default - to override, add a "
        f"trailing `# HNCS-OVERRIDE: {HOOK_NAME}: <reason>` comment to the "
        "command, stating why this specific destructive action is intended "
        "and safe.",
        severity=SEVERITY, target=command, decision=decision,
    )


if __name__ == "__main__":
    main()
