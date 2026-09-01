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
keyword like do/then/else - or at the very start of the command), allows
up to 6 recognized global git options (`-c k=v`, `-C dir`, `--long-flag
[=val]`, or a short flag) between `git` and `push`, and only inspects
that invocation's own trailing arguments (up to the next statement
separator) for a force flag - matching `--force`, `-f`, or
`--force-with-lease` with or without a `=<refspec>` suffix. This
deliberately does NOT match "git push" appearing inside a quoted
string/heredoc body/prose - e.g. a commit message or a test payload that
merely *mentions* "git push --force" as text, not as a command to run.
Verified against that false-positive, plus a real bypass found in code
review (`git -c http.extraHeader=x push --force` and
`--force-with-lease=<refspec>` both slipped past an earlier version of
this regex - see commit history) - none of this is a substitute for a
real shell parser, so this is still a best-effort net, not a guarantee.

**Severity (2026-08 redesign)**: force-push is CRITICAL, with an override
available via a trailing `# HNCS-OVERRIDE: protect_push_safety: <reason>`
comment (see `_hook_common.py`'s module docstring for the tier design).
The authorship-mismatch check has no override - there's no legitimate
reason to push with the wrong author when the fix is one command; it's
always resolvable rather than something to consciously bypass.

**정정(2026-08-20, README "알려진 한계" 2차 라운드 #4/#5 - 2개 실측
결함 수정)**: (1) `eval "git push --force ..."`는 `git`이 큰따옴표
바로 뒤라 `_STMT_START`가 요구하는 문 시작 위치가 아니어서 완전히
안 걸렸다 - `_hook_common.unwrap_eval()`로 eval/bash -c/sh -c에 감싸인
내용도 스캔 대상에 포함시켜 고침. (2) `git config`에 등록된 별칭
(`git pushf` 같은)이 실제로는 `push --force`를 실행해도, 훅이 보는
텍스트엔 "push"도 "--force"도 리터럴로 안 나타나서 전혀 못 봤다 -
`git config --get-regexp '^alias\\.'`로 force-push를 실행하는 별칭
이름을 미리 조회해서, 그 이름으로의 호출도 force-push로 취급하도록
추가."""
import json
import re
import subprocess
import sys

from _hook_common import (allow, allow_with_override, bash_override, deny,
                           is_subagent_call, require_decision_or_deny,
                           unwrap_eval)

HOOK_NAME = "protect_push_safety"
SEVERITY = "CRITICAL"

_CLAUDE_AUTHOR_EMAIL = "noreply@anthropic.com"

_STMT_START = r"(?:^|&&|\|\||;|\n|\||\(|`|\bdo\b|\bthen\b|\belse\b)\s*"
# Recognized git global options that may appear between `git` and `push`
# (e.g. `git -c http.extraHeader=x push ...`) - bounded to 6 repeats to
# keep backtracking cheap and to avoid matching arbitrary free text as
# "options".
_GIT_GLOBAL_OPT = r"(?:-c\s+\S+|-C\s+\S+|--\S+(?:=\S+)?|-[A-Za-z])"
_PUSH_INVOCATION_RE = re.compile(
    _STMT_START + r"git(?:\s+" + _GIT_GLOBAL_OPT + r"){0,6}\s+push\b(?P<args>[^\n;&|`]*)"
)
_FORCE_RE = re.compile(r"(^|\s)(--force(-with-lease)?(=\S+)?|-f)(\s|$)")
_ALIAS_LINE_RE = re.compile(r"^alias\.([\w-]+)\s+(.*)$")


def read_input():
    return json.load(sys.stdin)


def head_author_email():
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%ae"],
                              capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def force_push_alias_names():
    """Returns the set of `git config` alias names whose expansion itself
    force-pushes (contains "push" and a force flag) - so `git <alias>`
    can be recognized as a force-push even though neither "push" nor
    "--force" appears literally in the invoking command's own text."""
    try:
        out = subprocess.run(["git", "config", "--get-regexp", r"^alias\."],
                              capture_output=True, text=True, timeout=10)
    except Exception:
        return set()
    if out.returncode != 0:
        return set()
    names = set()
    for line in out.stdout.splitlines():
        m = _ALIAS_LINE_RE.match(line)
        if not m:
            continue
        name, expansion = m.group(1), m.group(2)
        if re.search(r"\bpush\b", expansion) and _FORCE_RE.search(expansion + " "):
            names.add(name)
    return names


def alias_invocation_re(names):
    if not names:
        return None
    alternation = "|".join(re.escape(n) for n in sorted(names))
    return re.compile(_STMT_START + r"git\s+(?:" + alternation + r")\b(?P<args>[^\n;&|`]*)")


def main():
    data = read_input()
    if data.get("tool_name") != "Bash":
        allow()
        return
    command = unwrap_eval(str((data.get("tool_input") or {}).get("command", "")))

    # (match, is_already_known_force) pairs - a plain `git push` match still
    # needs its own args checked for a force flag; an alias match is force
    # by construction (force_push_alias_names() already confirmed the
    # alias's own expansion force-pushes), so it skips that re-check.
    candidates = [(m, None) for m in _PUSH_INVOCATION_RE.finditer(command)]
    alias_re = alias_invocation_re(force_push_alias_names())
    if alias_re:
        candidates += [(m, True) for m in alias_re.finditer(command)]
    if not candidates:
        allow()
        return

    for m, known_force in candidates:
        if known_force or _FORCE_RE.search(m.group("args")):
            decision = require_decision_or_deny(
                HOOK_NAME, SEVERITY, command,
                "CLAUDE.md: \"Push rejected -> git fetch + git rebase, never force.\" "
                "This command force-pushes.")
            if decision is None:
                return
            if is_subagent_call(data):
                deny(
                    HOOK_NAME,
                    "CLAUDE.md: \"Push rejected -> git fetch + git rebase, "
                    "never force.\" This command force-pushes, and this call "
                    "is subagent-originated (agent_id present) - CRITICAL-"
                    "tier override is self-servable via a bash comment the "
                    "subagent itself could write, so force-push from a "
                    "subagent gets no override path at all. Have the "
                    "controller run this directly.",
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
                "CLAUDE.md: \"Push rejected -> git fetch + git rebase, "
                "never force.\" This command force-pushes. If the remote "
                "rejected a push, fetch and rebase instead - never force, "
                "even with --force-with-lease, unless the user explicitly "
                "authorized it in this conversation. To override: add a "
                f"trailing `# HNCS-OVERRIDE: {HOOK_NAME}: <reason>` comment "
                "to this command.",
                severity=SEVERITY, target=command, decision=decision,
            )
            return

    email = head_author_email()
    if email is not None and email != _CLAUDE_AUTHOR_EMAIL:
        decision = require_decision_or_deny(
            HOOK_NAME, "HIGH", command,
            "CLAUDE.md: \"Fix authorship or GitHub marks it Unverified.\" "
            f"HEAD commit's author email is {email!r}.")
        if decision is None:
            return
        deny(
            HOOK_NAME,
            "CLAUDE.md: \"Fix authorship or GitHub marks it Unverified.\" "
            f"HEAD commit's author email is {email!r}, not "
            f"{_CLAUDE_AUTHOR_EMAIL!r}. Run `git config user.email "
            f"{_CLAUDE_AUTHOR_EMAIL} && git config user.name Claude` then "
            "re-author HEAD (amend or rebase --exec) before pushing. No "
            "override for this one - just fix it.",
            severity="HIGH", target=command, decision=decision,
        )
        return

    allow()


if __name__ == "__main__":
    main()
