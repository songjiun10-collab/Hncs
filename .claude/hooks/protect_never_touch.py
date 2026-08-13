#!/usr/bin/env python3
"""PreToolUse hook enforcing CLAUDE.md's "Never" list: no Edit/Write/MultiEdit
may modify a shipped apply_* function in brands/*.py, or touch
hybrid_engine/assets/profiles/*.json|*.dcp, without the user's explicit,
in-the-moment sign-off given directly in the conversation. This hook cannot
detect that sign-off, so it always denies matching calls; the model must
surface the block to the user and get explicit permission before retrying
(there is no bypass through this hook - only a human can unblock)."""
import ast
import json
import os
import re
import sys

BRAND_FILE_RE = re.compile(r"(^|/)brands/[^/]+\.py$")
PROFILE_ASSET_RE = re.compile(r"(^|/)hybrid_engine/assets/profiles/[^/]+\.(json|dcp)$")


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


def allow():
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }))


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def main():
    data = read_input()
    tool = data.get("tool_name")
    if tool not in ("Edit", "Write", "MultiEdit"):
        allow()
        return
    ti = data.get("tool_input") or {}
    file_path = ti.get("file_path", "")
    if not file_path:
        allow()
        return

    if is_profile_asset(file_path):
        deny(
            f"CLAUDE.md Never list: {file_path} is a shipped calibration "
            "profile under hybrid_engine/assets/profiles/. It cannot be "
            "modified without the user's explicit, in-the-moment sign-off "
            "given directly in this conversation. Stop and ask the user "
            "before retrying - this hook has no bypass."
        )
        return

    if not is_brand_file(file_path):
        allow()
        return

    if tool == "Write":
        ranges = protected_ranges(file_path)
        if ranges is None:
            deny(
                f"CLAUDE.md Never list: couldn't parse the current contents of "
                f"{file_path} to check for shipped apply_* functions before this "
                "Write would overwrite it. Blocking to be safe - ask the user "
                "for explicit sign-off, or fix whatever broke the parse."
            )
            return
        if ranges:
            names = ", ".join(n for n, _, _ in ranges)
            deny(
                f"CLAUDE.md Never list: this Write would overwrite {file_path}, "
                f"which currently defines shipped apply_* function(s) ({names}). "
                "Modifying a shipped apply_* requires the user's explicit, "
                "in-the-moment sign-off given directly in this conversation - "
                "use Edit for unrelated additions, or ask the user first."
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
            deny(
                f"CLAUDE.md Never list: couldn't parse {file_path} to check "
                "whether this edit touches a shipped apply_* function. "
                "Blocking to be safe - ask the user for explicit sign-off, "
                "or fix whatever broke the parse."
            )
            return
        if name:
            deny(
                f"CLAUDE.md Never list: this edit touches `{name}()` in "
                f"{file_path} (lines {rng[0]}-{rng[1]}), a shipped apply_* "
                "function. CLAUDE.md forbids modifying it without the user's "
                "explicit, in-the-moment sign-off given directly in this "
                "conversation. Stop and ask the user before retrying - this "
                "hook has no bypass."
            )
            return

    allow()


if __name__ == "__main__":
    main()
