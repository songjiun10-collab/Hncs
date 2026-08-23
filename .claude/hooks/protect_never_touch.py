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
greps a protected path (e.g. `cat brands/hasselblad.py`) is left alone.

**정정(2026-08-20, README "알려진 한계" 2차 라운드 #1 - 실측 결함
수정)**: heredoc 본문을 무조건 지우던 게, `python3 - <<'PY'
... open("brands/hasselblad.py","w").write(...) ... PY`처럼 인터프리터에
넘겨져서 실제로 실행되는 코드까지 놓쳤다(파일에 진짜 쓰기가 일어남) -
프로즈 오탐만 막고 인터프리터로 넘어가는 heredoc 본문은 스캔 대상에
남겨두는 `_hook_common.strip_prose_heredocs()`로 교체.

**정정(2026-08-20, README "알려진 한계" 2차 라운드 #2 - 실측 결함
수정)**: `_PY_WRITE_OPEN_RE`는 `open(...)`의 첫 인자가 단일 따옴표 쌍
안에 통째로 들어있다고 가정하는데, (1) 인접 문자열 리터럴
연결(`open('brand''s/hasselblad.py','w')` - Python이 런타임에 이어붙이지만
정규식은 첫 `'...'` 안에서 매칭이 끊김)과 (2) 변수 간접 참조
(`p='brands/hasselblad.py'; open(p,'w')` - `open()` 호출부엔 리터럴
자체가 없음) 둘 다 놓쳤다. `_py_open_literal_target()`(인접 리터럴을
이어붙여서 재검사)과 `_py_open_var_target()`(같은 커맨드 안에서 그
변수에 대한 대입을 찾아서 재검사)로 보강.

**정정(2026-08-20, 사용자 지시 - 단일 홉 → 다단계 체인)**:
`_py_open_var_target()`이 원래 단일 홉만 따라갔음(`p='brands/x.py';
open(p,'w')`는 잡지만 `q=p; p='brands/x.py'; open(q,'w')`는 여전히
놓침). `_resolve_var_literal()`이 바인딩 체인을 `_MAX_VAR_HOPS`(5)까지
재귀적으로 따라가도록 교체 - 여전히 완전한 데이터흐름 분석은 아님
(f-string 표현식, 문자열 메서드 호출로 계산된 값은 못 봄), 경계를
5홉으로 명시적으로 그은 국소 패치."""
import ast
import json
import os
import re
import sys

from _hook_common import (allow, allow_with_override, bash_override, deny,
                           is_subagent_call, require_decision_or_deny,
                           sentinel_override, strip_prose_heredocs)

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

_PROTECTED_PATH_BARE_RE = re.compile(_PROTECTED_PATH)
_QUOTED_SEGMENT_RE = re.compile(r"[\"']([^\"']*)[\"']")
_PY_OPEN_LITERAL_ARG_RE = re.compile(
    r"open\(\s*f?((?:[\"'][^\"']*[\"']\s*){1,20})\s*,\s*[\"'](?:w|a|wb|ab|x)[\"']")
_PY_OPEN_VAR_ARG_RE = re.compile(
    r"open\(\s*(\w+)\s*,\s*[\"'](?:w|a|wb|ab|x)[\"']")
# RHS is either 1+ quoted literal(s) (leaf) or a bare identifier (another
# hop to follow) - covers both `p='brands/x.py'` and `q=p` in one pattern.
_PY_ANY_ASSIGN_RE = re.compile(
    r"\b(\w+)\s*=\s*f?((?:[\"'][^\"']*[\"']\s*)+|\w+)")
_MAX_VAR_HOPS = 5


def _concat_quoted_literal(raw):
    return "".join(_QUOTED_SEGMENT_RE.findall(raw))


def _resolve_var_literal(command, var, upto, hops=0):
    """Walks assignment chains backward from position `upto`, resolving
    `var` to its concatenated literal string - follows bare-identifier
    hops (q=p; p=r; r='brands/x.py') up to `_MAX_VAR_HOPS` before giving
    up. Bounded heuristic, not full data-flow analysis - a computed value
    (f-string with an expression, string method call, etc.) still evades
    this."""
    if hops >= _MAX_VAR_HOPS:
        return None
    latest = None
    for am in _PY_ANY_ASSIGN_RE.finditer(command[:upto]):
        if am.group(1) == var:
            latest = am
    if latest is None:
        return None
    rhs = latest.group(2)
    if rhs and rhs[0] in "\"'":
        return _concat_quoted_literal(rhs)
    if rhs == var:
        return None
    return _resolve_var_literal(command, rhs, latest.start(), hops + 1)


def _py_open_literal_target(command):
    """Adjacent string-literal concatenation - open('brand''s/x.py','w')
    is one path at runtime (Python joins adjacent literals at parse time)
    but _PY_WRITE_OPEN_RE's single-literal match ends at the first closing
    quote. Re-join the quoted segments and re-check against the protected
    path pattern."""
    m = _PY_OPEN_LITERAL_ARG_RE.search(command)
    if not m:
        return None
    path_m = _PROTECTED_PATH_BARE_RE.search(_concat_quoted_literal(m.group(1)))
    return path_m.group(0) if path_m else None


def _py_open_var_target(command):
    """Heuristic for open(var, 'w') where var was assigned a literal
    string earlier in the same command, possibly through a chain of
    bare-identifier reassignments (q=p; p=r; r='brands/x.py'; open(q,'w'))
    - open()'s own call site has no literal for the single-literal regex
    to match. Follows up to `_MAX_VAR_HOPS` hops, not a full data-flow
    analysis - a computed value still evades this."""
    m = _PY_OPEN_VAR_ARG_RE.search(command)
    if not m:
        return None
    literal = _resolve_var_literal(command, m.group(1), m.start())
    if literal is None:
        return None
    path_m = _PROTECTED_PATH_BARE_RE.search(literal)
    return path_m.group(0) if path_m else None


def bash_write_target(command):
    """Returns the matched protected-path string if `command` looks like it
    writes to a protected path, else None. Coarser than the Edit/Write path
    below (file-level, not function-level - see module docstring)."""
    command = strip_prose_heredocs(command)
    for rx in (_REDIRECT_TARGET_RE, _SED_INPLACE_TARGET_RE, _TEE_TARGET_RE,
               _CP_MV_DEST_RE, _PY_WRITE_OPEN_RE):
        m = rx.search(command)
        if m:
            return m.group(1)
    for fn in (_py_open_literal_target, _py_open_var_target):
        target = fn(command)
        if target:
            return target
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
    decision = require_decision_or_deny(HOOK_NAME, SEVERITY, target, reason)
    if decision is None:
        return
    if is_subagent_call(data):
        deny(HOOK_NAME, reason + _SUBAGENT_NO_OVERRIDE_NOTE, severity=SEVERITY,
             target=target, decision=decision)
        return
    override_reason = bash_override(HOOK_NAME, command)
    if override_reason:
        allow_with_override(HOOK_NAME, SEVERITY, HOOK_NAME, target, override_reason,
                             decision=decision)
        return
    deny(HOOK_NAME, reason, severity=SEVERITY, target=target, decision=decision)


def _deny_or_sentinel_override(target, reason, data):
    decision = require_decision_or_deny(HOOK_NAME, SEVERITY, target, reason)
    if decision is None:
        return
    if is_subagent_call(data):
        deny(HOOK_NAME, reason + _SUBAGENT_NO_OVERRIDE_NOTE, severity=SEVERITY,
             target=target, decision=decision)
        return
    override_reason = sentinel_override(HOOK_NAME, target)
    if override_reason:
        allow_with_override(HOOK_NAME, SEVERITY, HOOK_NAME, target, override_reason,
                             decision=decision)
        return
    deny(HOOK_NAME, reason, severity=SEVERITY, target=target, decision=decision)


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
