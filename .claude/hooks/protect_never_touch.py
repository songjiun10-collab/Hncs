#!/usr/bin/env python3
"""PreToolUse hook enforcing CLAUDE.md's "Never" list: no Edit/Write/MultiEdit
may modify a shipped apply_* function in brands/*.py, or touch
hybrid_engine/assets/profiles/*.json|*.dcp, without the user's explicit,
in-the-moment sign-off given directly in the conversation.

**CRITICAL severity, override available (2026-08 redesign).** Denies by
default. An override is honored if a matching, fresh (<=10min)
`.claude/hooks/.pending_override.json` sentinel exists (see
`_hook_common.sentinel_override()` for the exact contract) for the
Edit/Write/MultiEdit path, or a trailing `# HNCS-OVERRIDE:
protect_never_touch: <reason>` comment for the Bash path. Every override
is logged to `override_audit.jsonl` with the git sha it was granted at -
this hook doesn't judge whether the override is *wise*, only that it was
explicit, not silent. Write the sentinel yourself right before the
guarded call; don't ask the user to do it manually.

Also covers Bash: a code review found this hook's Edit|Write|MultiEdit-only
matcher meant `sed -i`, `python3 -c "...open(...).write(...)"`, `tee`, or
shell redirection against a protected path went through unchecked. Bash text
doesn't carry a reliable notion of byte/line ranges the way Edit/Write do,
so Bash coverage is file-level (any write-shaped command referencing a
protected path is blocked), not function-level like the Edit/Write path
above - coarser, but still a real, text-matching-based net rather than a
guarantee. A command with no write-shaped pattern that merely reads or
greps a protected path (e.g. `cat brands/hasselblad.py`) is left alone."""
import ast
import json
import os
import re
import sys

from _hook_common import (allow, allow_with_override, bash_override, deny,
                           is_subagent_call, sentinel_override)

HOOK_NAME = "protect_never_touch"
SEVERITY = "CRITICAL"

BRAND_FILE_RE = re.compile(r"(^|/)brands/[^/]+\.py$")
PROFILE_ASSET_RE = re.compile(r"(^|/)hybrid_engine/assets/profiles/[^/]+\.(json|dcp)$")

# Bash coverage: only flags a write-shaped command whose *destination*
# looks like a protected path - e.g. `cp x brands/hasselblad.py` (protected
# path last = destination) is flagged, `cp brands/hasselblad.py /tmp/ref.py`
# (protected path first = source, just reading it out for reference) is not.
_PROTECTED_PATH = (
    r"(?:(?:[\w./-]*/)?brands/[^/\s\"'>]+\.py|"
    r"(?:[\w./-]*/)?hybrid_engine/assets/profiles/[^/\s\"'>]+\.(?:json|dcp))"
)
_REDIRECT_TARGET_RE = re.compile(r">{1,2}\s*[\"']?(" + _PROTECTED_PATH + r")")
_SED_INPLACE_TARGET_RE = re.compile(r"\bsed\s+-i\b[^|;&\n`]*?(" + _PROTECTED_PATH + r")")
_TEE_TARGET_RE = re.compile(r"\btee\b[^|;&\n`]*?(" + _PROTECTED_PATH + r")")
_CP_MV_DEST_RE = re.compile(
    r"\b(?:cp|mv)\b[^|;&\n`]*\s(" + _PROTECTED_PATH + r")\s*(?:[;&|\n`]|$)")
_PY_WRITE_OPEN_RE = re.compile(
    r"open\(\s*f?[\"']([^\"']*" + _PROTECTED_PATH + r")[\"']\s*,\s*"
    r"[\"'](?:w|a|wb|ab|x)[\"']")


# Strips heredoc bodies (`<<EOF ... EOF` / `<<'EOF' ... EOF` / `<<-EOF ...
# EOF`) before scanning - otherwise a heredoc body that merely *mentions* a
# redirect/protected-path pattern as prose (e.g. a commit message explaining
# this very hook) gets misread as a real write. Same false-positive class
# `protect_push_safety.py` hit and fixed earlier this session.
_HEREDOC_RE = re.compile(r"<<-?\s*[\"']?(\w+)[\"']?.*?\n.*?^\1\b", re.DOTALL | re.MULTILINE)


def bash_write_target(command):
    """Returns the matched protected-path string if `command` looks like it
    writes to a protected path, else None. Coarser than the Edit/Write path
    below (file-level, not function-level - see module docstring)."""
    command = _HEREDOC_RE.sub("", command)
    for rx in (_REDIRECT_TARGET_RE, _SED_INPLACE_TARGET_RE, _TEE_TARGET_RE,
               _CP_MV_DEST_RE, _PY_WRITE_OPEN_RE):
        m = rx.search(command)
        if m:
            return m.group(1)
    return None


def read_input():
    return json.load(sys.stdin)


def normalize(path):
    return (path or "").replace(os.sep, "/")


def is_profile_asset(path):
    return bool(PROFILE_ASSET_RE.search(normalize(path)))


def is_brand_file(path):
    return bool(BRAND_FILE_RE.search(normalize(path)))


def _assign_targets(node):
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def protected_ranges(file_path):
    """Returns [(name, start_line, end_line), ...] for every shipped apply_*
    in file_path, or None if the file can't be parsed (fail-safe signal).
    Covers both `def apply_X(...)` (hasselblad.py, fuji.py, ...) and the
    `apply_X_look = make_population_fit_look(...)` factory-assignment
    pattern most brands/*.py files use (core/engine.py's
    make_population_fit_look()/make_hasselblad_body_look()) - a plain
    ast.FunctionDef scan misses the latter entirely."""
    if not os.path.exists(file_path):
        return []
    try:
        src = open(file_path, "r", encoding="utf-8").read()
        tree = ast.parse(src)
    except Exception:
        return None
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("apply_"):
            end = getattr(node, "end_lineno", node.lineno)
            ranges.append((node.name, node.lineno, end))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for name in _assign_targets(node):
                if name.startswith("apply_"):
                    end = getattr(node, "end_lineno", node.lineno)
                    ranges.append((name, node.lineno, end))
    return ranges


def line_of_offset(text, offset):
    return text.count("\n", 0, offset) + 1


def touched_function(file_path, old_string):
    """Returns (name, (start, end)) if ANY occurrence of old_string in
    file_path overlaps a protected apply_* (checking every occurrence, not
    just the first, since Edit's replace_all applies to all of them),
    ("__unknown__", None) if the file couldn't be safety-checked, or
    (None, None) if it's clear."""
    if not old_string or not os.path.exists(file_path):
        return None, None
    text = open(file_path, "r", encoding="utf-8").read()
    ranges = protected_ranges(file_path)
    if ranges is None:
        return "__unknown__", None
    start = 0
    while True:
        idx = text.find(old_string, start)
        if idx == -1:
            break
        start_line = line_of_offset(text, idx)
        end_line = line_of_offset(text, idx + len(old_string))
        for name, s, e in ranges:
            if start_line <= e and end_line >= s:
                return name, (s, e)
        start = idx + 1
    return None, None


_SUBAGENT_NO_OVERRIDE_NOTE = (
    " 이 호출은 서브에이전트발이라(agent_id 있음) override를 받지 않음 - "
    "CRITICAL 등급에서 override는 self-servable(자기 자신이 사유를 지어내면 "
    "훅은 검증 불가)이라는 게 가장 치명적인 지점이라, Never-touch는 "
    "서브에이전트발 시도를 아예 override 불가로 막는다. 컨트롤러가 직접 "
    "실행할 것(오케스트레이터 직접 호출은 기존 sentinel/bash-marker "
    "override 그대로 사용 가능)."
)


def _deny_or_bash_override(command, target, reason, data):
    if is_subagent_call(data):
        deny(HOOK_NAME, reason + _SUBAGENT_NO_OVERRIDE_NOTE, severity=SEVERITY, target=target)
        return
    override_reason = bash_override(HOOK_NAME, command)
    if override_reason:
        allow_with_override(HOOK_NAME, SEVERITY, HOOK_NAME, target, override_reason)
        return
    deny(HOOK_NAME, reason, severity=SEVERITY, target=target)


def _deny_or_sentinel_override(target, reason, data):
    if is_subagent_call(data):
        deny(HOOK_NAME, reason + _SUBAGENT_NO_OVERRIDE_NOTE, severity=SEVERITY, target=target)
        return
    override_reason = sentinel_override(HOOK_NAME, target)
    if override_reason:
        allow_with_override(HOOK_NAME, SEVERITY, HOOK_NAME, target, override_reason)
        return
    deny(HOOK_NAME, reason, severity=SEVERITY, target=target)


def main():
    data = read_input()
    tool = data.get("tool_name")

    if tool == "Bash":
        command = str((data.get("tool_input") or {}).get("command", ""))
        target = bash_write_target(command)
        if target is None:
            allow()
            return
        if is_profile_asset(target):
            _deny_or_bash_override(
                command, target,
                f"CLAUDE.md Never list: this Bash command appears to write to "
                f"{target}, a shipped calibration profile under "
                "hybrid_engine/assets/profiles/. It cannot be modified without "
                "the user's explicit, in-the-moment sign-off given directly in "
                "this conversation. To override: add a trailing `# HNCS-OVERRIDE: "
                f"{HOOK_NAME}: <reason>` comment to this command.",
                data,
            )
            return
        if is_brand_file(target):
            _deny_or_bash_override(
                command, target,
                f"CLAUDE.md Never list: this Bash command appears to write to "
                f"{target} (brands/*.py). This check is file-level, not "
                "function-level like the Edit/Write path - it can't tell "
                "whether the write targets a shipped apply_* specifically, so "
                "it blocks any write-shaped Bash command touching this file to "
                "be safe. To override: add a trailing `# HNCS-OVERRIDE: "
                f"{HOOK_NAME}: <reason>` comment to this command.",
                data,
            )
            return
        allow()
        return

    if tool not in ("Edit", "Write", "MultiEdit"):
        allow()
        return
    ti = data.get("tool_input") or {}
    file_path = ti.get("file_path", "")
    if not file_path:
        allow()
        return

    if is_profile_asset(file_path):
        _deny_or_sentinel_override(
            file_path,
            f"CLAUDE.md Never list: {file_path} is a shipped calibration "
            "profile under hybrid_engine/assets/profiles/. It cannot be "
            "modified without the user's explicit, in-the-moment sign-off "
            "given directly in this conversation. To override: write "
            f'.claude/hooks/.pending_override.json with {{"rule": "{HOOK_NAME}", '
            f'"target": "{file_path}", "reason": "<reason>", "timestamp": '
            "<time.time()>}, then retry immediately.",
            data,
        )
        return

    if not is_brand_file(file_path):
        allow()
        return

    if tool == "Write":
        ranges = protected_ranges(file_path)
        if ranges is None:
            _deny_or_sentinel_override(
                file_path,
                f"CLAUDE.md Never list: couldn't parse the current contents of "
                f"{file_path} to check for shipped apply_* functions before this "
                "Write would overwrite it. Blocking to be safe - ask the user "
                "for explicit sign-off, or fix whatever broke the parse.",
                data,
            )
            return
        if ranges:
            names = ", ".join(n for n, _, _ in ranges)
            _deny_or_sentinel_override(
                file_path,
                f"CLAUDE.md Never list: this Write would overwrite {file_path}, "
                f"which currently defines shipped apply_* function(s) ({names}). "
                "Modifying a shipped apply_* requires the user's explicit, "
                "in-the-moment sign-off given directly in this conversation. To "
                f'override: write .claude/hooks/.pending_override.json with '
                f'{{"rule": "{HOOK_NAME}", "target": "{file_path}", "reason": '
                '"<reason>", "timestamp": <time.time()>}, then retry immediately.',
                data,
            )
            return
        allow()
        return

    # Edit / MultiEdit
    if tool == "MultiEdit":
        edits = ti.get("edits") or []
    else:
        edits = [{"old_string": ti.get("old_string", "")}]

    for e in edits:
        name, rng = touched_function(file_path, e.get("old_string", ""))
        if name == "__unknown__":
            _deny_or_sentinel_override(
                file_path,
                f"CLAUDE.md Never list: couldn't parse {file_path} to check "
                "whether this edit touches a shipped apply_* function. "
                "Blocking to be safe - ask the user for explicit sign-off, "
                "or fix whatever broke the parse.",
                data,
            )
            return
        if name:
            _deny_or_sentinel_override(
                file_path,
                f"CLAUDE.md Never list: this edit touches `{name}()` in "
                f"{file_path} (lines {rng[0]}-{rng[1]}), a shipped apply_* "
                "function. CLAUDE.md forbids modifying it without the user's "
                "explicit, in-the-moment sign-off given directly in this "
                f'conversation. To override: write '
                f'.claude/hooks/.pending_override.json with {{"rule": '
                f'"{HOOK_NAME}", "target": "{file_path}", "reason": "<reason>", '
                '"timestamp": <time.time()>}, then retry immediately.',
                data,
            )
            return

    allow()


if __name__ == "__main__":
    main()
