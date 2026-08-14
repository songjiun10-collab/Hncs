#!/usr/bin/env python3
"""PreToolUse hook (matcher: Bash) enforcing two CLAUDE.md git rules:

1. "Push rejected -> git fetch + git rebase, never force." Blocks
   `git push` with a force flag (--force/-f/--force-with-lease) outright.
2. "Every commit: fix authorship or GitHub marks it Unverified." Before
   a `git push`, checks the current HEAD commit's author email is the
   configured Claude identity - catches the case where a commit was made
   with a stale/human git config and never re-authored.

Text-matching a raw shell command string is inherently approximate, so
this only flags a `git push` that appears as an actual statement start
(after &&, ||, ;, a newline, a pipe, a subshell/backtick, or a shell
keyword like do/then/else - or at the very start of the command) and
only inspects that invocation's own trailing arguments (up to the next
statement separator) for a force flag. This deliberately does NOT match
"git push" appearing inside a quoted string/heredoc body/prose - e.g. a
commit message or a test payload that merely *mentions* "git push
--force" as text, not as a command to run. Verified against exactly that
false-positive during development (see commit history)."""
import json
import re
import subprocess
import sys

from _hook_common import allow, deny

HOOK_NAME = "protect_push_safety"

_CLAUDE_AUTHOR_EMAIL = "noreply@anthropic.com"

_STMT_START = r"(?:^|&&|\|\||;|\n|\||\(|`|\bdo\b|\bthen\b|\belse\b)\s*"
_PUSH_INVOCATION_RE = re.compile(
    _STMT_START + r"git\s+push\b(?P<args>[^\n;&|`]*)"
)
_FORCE_RE = re.compile(r"(^|\s)(--force(-with-lease)?|-f)(\s|$)")


def read_input():
    return json.load(sys.stdin)


def head_author_email():
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%ae"],
                              capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def main():
    data = read_input()
    if data.get("tool_name") != "Bash":
        allow()
        return
    command = str((data.get("tool_input") or {}).get("command", ""))

    matches = list(_PUSH_INVOCATION_RE.finditer(command))
    if not matches:
        allow()
        return

    for m in matches:
        if _FORCE_RE.search(m.group("args")):
            deny(
                HOOK_NAME,
                "CLAUDE.md: \"Push rejected -> git fetch + git rebase, "
                "never force.\" This command force-pushes. If the remote "
                "rejected a push, fetch and rebase instead - never force, "
                "even with --force-with-lease, unless the user explicitly "
                "authorized it in this conversation. This hook has no "
                "bypass."
            )
            return

    email = head_author_email()
    if email is not None and email != _CLAUDE_AUTHOR_EMAIL:
        deny(
            HOOK_NAME,
            "CLAUDE.md: \"Fix authorship or GitHub marks it Unverified.\" "
            f"HEAD commit's author email is {email!r}, not "
            f"{_CLAUDE_AUTHOR_EMAIL!r}. Run `git config user.email "
            f"{_CLAUDE_AUTHOR_EMAIL} && git config user.name Claude` then "
            "re-author HEAD (amend or rebase --exec) before pushing. This "
            "hook has no bypass."
        )
        return

    allow()


if __name__ == "__main__":
    main()
