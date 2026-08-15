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
override-tier design."""
import json
import re
import sys

from _hook_common import allow, allow_with_override, bash_override, deny

HOOK_NAME = "protect_destructive"
SEVERITY = "CRITICAL"

_STMT_START = r"(?:^|&&|\|\||;|\n|\||\(|`|\bdo\b|\bthen\b|\belse\b)\s*"
_HEREDOC_RE = re.compile(r"<<-?\s*[\"']?(\w+)[\"']?.*?\n.*?^\1\b", re.DOTALL | re.MULTILINE)

# rm -r/-f in any combination (long or short form), with the target -
# only flagged if none of the targets look like a scratch/temp path.
_RM_RE = re.compile(
    _STMT_START + r"rm\s+(?P<args>[^\n;&|`]*)"
)
_RM_RECURSIVE_RE = re.compile(r"(^|\s)(-\w*[rR]\w*|--recursive)(\s|$)")
_RM_FORCE_RE = re.compile(r"(^|\s)(-\w*f\w*|--force)(\s|$)")
_SCRATCH_PATH_RE = re.compile(r"(^|\s)(/tmp/|\.\/?scratchpad/|/scratchpad/)")

_GIT_RESET_HARD_RE = re.compile(_STMT_START + r"git\s+reset\s+.*--hard\b")
_GIT_CLEAN_FORCE_RE = re.compile(
    _STMT_START + r"git\s+clean\s+(?:(?!\bgit\b)[^\n;&|`])*?"
    r"(-\w*f\w*|--force)\b")
_GIT_BRANCH_DELETE_FORCE_RE = re.compile(
    _STMT_START + r"git\s+branch\s+(?:(?!\bgit\b)[^\n;&|`])*?"
    r"(-D\b|--delete\s+--force\b|-\w*D\w*)")


def read_input():
    return json.load(sys.stdin)


def destructive_reason(command):
    """Returns a human-readable reason string if `command` looks
    destructive, else None."""
    command = _HEREDOC_RE.sub("", command)

    for m in _RM_RE.finditer(command):
        args = m.group("args")
        if _RM_RECURSIVE_RE.search(args) and _RM_FORCE_RE.search(args):
            if _SCRATCH_PATH_RE.search(args):
                continue
            return ("`rm` with both a recursive and a force flag, on a path "
                    "that isn't under /tmp/ or a scratchpad/ dir - this "
                    "permanently deletes files with no undo.")

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

    override_reason = bash_override(HOOK_NAME, command)
    if override_reason:
        allow_with_override(HOOK_NAME, SEVERITY, HOOK_NAME, command, override_reason)
        return

    deny(
        HOOK_NAME,
        f"{reason} This hook denies by default - to override, add a "
        f"trailing `# HNCS-OVERRIDE: {HOOK_NAME}: <reason>` comment to the "
        "command, stating why this specific destructive action is intended "
        "and safe.",
        severity=SEVERITY,
    )


if __name__ == "__main__":
    main()
