#!/usr/bin/env python3
"""PreToolUse hook (matcher: Bash), HIGH severity. Before a `git commit` or
`git push`, checks the current branch isn't a default-branch name
(main/master) or a detached HEAD - catches "accidentally committing to
main" (or a detached HEAD nobody will find again) before it happens,
rather than after.

Same statement-boundary + heredoc-stripping approach as
`protect_push_safety.py`/`protect_never_touch.py` to avoid the same class
of false positive (a commit message that merely *mentions* "git commit"
as prose).

Override: trailing `# HNCS-OVERRIDE: protect_branch: <reason>` comment -
sometimes committing to main directly really is intended (e.g. a genuine
hotfix workflow, or a repo where main IS the working branch)."""
import json
import re
import subprocess
import sys

from _hook_common import (allow, allow_with_override, bash_override,
                           high_tier_decision, require_decision_or_deny)

HOOK_NAME = "protect_branch"
SEVERITY = "HIGH"

_STMT_START = r"(?:^|&&|\|\||;|\n|\||\(|`|\bdo\b|\bthen\b|\belse\b)\s*"
_HEREDOC_RE = re.compile(r"<<-?\s*[\"']?(\w+)[\"']?.*?\n.*?^\1\b", re.DOTALL | re.MULTILINE)
_COMMIT_OR_PUSH_RE = re.compile(_STMT_START + r"git\s+(commit|push)\b")

_DEFAULT_BRANCH_NAMES = {"main", "master"}


def read_input():
    return json.load(sys.stdin)


def current_branch():
    try:
        out = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                              capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def branch_risk_reason(branch):
    """Returns a reason string if `branch` looks like an unintended commit
    target, else None. `git rev-parse --abbrev-ref HEAD` prints literal
    \"HEAD\" when detached."""
    if branch == "HEAD":
        return ("HEAD is detached - not on any branch. A commit here is "
                "easy to lose (unreachable once you switch branches, until "
                "it's garbage-collected).")
    if branch in _DEFAULT_BRANCH_NAMES:
        return (f"Current branch is '{branch}' (a default-branch name). "
                "If a feature/working branch was intended, this is "
                "probably a wrong-branch mistake, not a deliberate choice.")
    return None


def main():
    data = read_input()
    if data.get("tool_name") != "Bash":
        allow()
        return
    command = str((data.get("tool_input") or {}).get("command", ""))
    stripped = _HEREDOC_RE.sub("", command)
    if not _COMMIT_OR_PUSH_RE.search(stripped):
        allow()
        return

    branch = current_branch()
    if branch is None:
        allow()  # not a git repo, or git unavailable - nothing to check
        return

    reason = branch_risk_reason(branch)
    if reason is None:
        allow()
        return

    decision = require_decision_or_deny(HOOK_NAME, SEVERITY, branch, reason)
    if decision is None:
        return

    override_reason = bash_override(HOOK_NAME, command)
    if override_reason:
        allow_with_override(HOOK_NAME, SEVERITY, HOOK_NAME, branch, override_reason,
                             decision=decision)
        return

    high_tier_decision(
        HOOK_NAME, SEVERITY,
        f"{reason} To override: add a trailing `# HNCS-OVERRIDE: "
        f"{HOOK_NAME}: <reason>` comment to the command.",
        data, target=branch, decision=decision,
    )


if __name__ == "__main__":
    main()
