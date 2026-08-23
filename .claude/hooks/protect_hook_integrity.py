#!/usr/bin/env python3
"""PreToolUse hook enforcing hook-tree integrity: no Edit/Write/MultiEdit/
Bash may modify `.claude/hooks/*.py`, `.claude/hooks/session-start.sh`, or
`.claude/settings.json` without the user's explicit, in-the-moment
sign-off.

**Why (2026-08-20, 사용자 지시 - README "알려진 한계", "훅 스크립트/설정
자체의 무결성·공급망 신뢰" 항목)**: 이전까지 이 시스템의 모든 가드는
"훅이 (변조 없이) 실행된다"는 전제 위에서 그 안의 판단 로직만 검증했다 -
훅 파일/설정 자체가 위조·약화될 수 있는가는 다뤄지지 않았다
(`affaan-m/ECC`의 보안 가이드가 실제 CVE 두 개, `CVE-2025-59536`/
`CVE-2026-21852`를 근거로 훅을 방어 메커니즘이 아니라 공격 표면으로
프레이밍한 것 참고). 이 훅은 그 전제 자체를 지킨다 - 다른 CRITICAL
가드와 동일한 override 메커니즘(사용자의 명시적, 그 자리에서의 승인)
이지만 override 자체도 감사 로그에 남는다.

**의도된 부작용**: 이 훅 자신을 포함해 이 세션이 만든 다른 모든 훅
수정도 지금부터 이 가드를 통과해야 함 - 자기 자신을 예외로 두지 않음
(예외를 두면 "훅 코드는 특별 취급"이라는 바로 그 취약점을 재도입하는
것이 됨).

**Scope**: `.claude/hooks/` 아래 `*.py`(직계 자식만 - 현재 이 디렉토리
구조와 일치, 서브디렉토리 없음)와 `session-start.sh`, 그리고
`.claude/settings.json`. `.claude/hooks/README.md`/`CLAUDE.md`는
**의도적으로 제외** - 이 프로토콜 자체가 발견을 README에 기록하도록
요구하는데(문서, 실행 코드 아님), 문서 편집까지 게이트에 걸리면 보고
워크플로우 자체가 매번 override를 요구하게 된다.

**Coverage**: 함수 단위가 아니라 파일 단위(`protect_never_touch.py`와
같은 이유 - Bash 텍스트는 신뢰할 만한 byte/line 범위 개념이 없다)이고,
Edit/Write는 임의의 한 글자 변경도 막는다(부분 신뢰라는 개념이 없음 -
훅 코드는 전부 아니면 전무). Bash 경로는 `protect_never_touch.py`의
같은 클래스 우회(heredoc, 인접 문자열 리터럴 연결, 다단계 변수 간접
참조)에 동일하게 대응 - 그 발견들이 이 새 가드에도 그대로 적용되므로
처음부터 같은 방어를 넣었다.

Override: same mechanism as `protect_never_touch.py` - a fresh (<=10min)
matching `.claude/hooks/.pending_override.json` sentinel for Edit/Write,
or a trailing `# HNCS-OVERRIDE: protect_hook_integrity: <reason>` comment
for Bash. Subagent-originated calls get no override at all (CRITICAL
convention - override is self-servable, which is exactly what CRITICAL
exists to close off for subagent-originated attempts)."""
import json
import os
import re
import sys

from _hook_common import (allow, allow_with_override, bash_override, deny,
                           is_subagent_call, require_decision_or_deny,
                           sentinel_override, strip_prose_heredocs,
                           unwrap_eval)

HOOK_NAME = "protect_hook_integrity"
SEVERITY = "CRITICAL"

_HOOK_SCRIPT_RE = re.compile(r"(^|/)\.claude/hooks/[^/]+\.py$")
_SESSION_START_RE = re.compile(r"(^|/)\.claude/hooks/session-start\.sh$")
_SETTINGS_RE = re.compile(r"(^|/)\.claude/settings\.json$")

_PROTECTED_PATH = (
    r"(?:(?:[\w./-]*/)?\.claude/hooks/[^/\s\"'>]+\.py|"
    r"(?:[\w./-]*/)?\.claude/hooks/session-start\.sh|"
    r"(?:[\w./-]*/)?\.claude/settings\.json)"
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
_PY_ANY_ASSIGN_RE = re.compile(
    r"\b(\w+)\s*=\s*f?((?:[\"'][^\"']*[\"']\s*)+|\w+)")
_MAX_VAR_HOPS = 5


def read_input():
    return json.load(sys.stdin)


def normalize(path):
    return (path or "").replace(os.sep, "/")


def is_protected_hook_path(path):
    p = normalize(path)
    return bool(_HOOK_SCRIPT_RE.search(p) or _SESSION_START_RE.search(p)
                or _SETTINGS_RE.search(p))


def _concat_quoted_literal(raw):
    return "".join(_QUOTED_SEGMENT_RE.findall(raw))


def _resolve_var_literal(command, var, upto, hops=0):
    """Same bounded (<=_MAX_VAR_HOPS) assignment-chain resolver as
    protect_never_touch.py's - see that module for the full rationale."""
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
    m = _PY_OPEN_LITERAL_ARG_RE.search(command)
    if not m:
        return None
    path_m = _PROTECTED_PATH_BARE_RE.search(_concat_quoted_literal(m.group(1)))
    return path_m.group(0) if path_m else None


def _py_open_var_target(command):
    m = _PY_OPEN_VAR_ARG_RE.search(command)
    if not m:
        return None
    literal = _resolve_var_literal(command, m.group(1), m.start())
    if literal is None:
        return None
    path_m = _PROTECTED_PATH_BARE_RE.search(literal)
    return path_m.group(0) if path_m else None


def bash_write_target(command):
    """Returns the matched protected-path string if `command` looks like
    it writes to a hook script/settings file via Bash, else None."""
    command = unwrap_eval(strip_prose_heredocs(command))
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


def _deny_or_bash_override(command, target, data):
    reason = (
        f"CLAUDE.md Never list을 실제로 강제하는 훅 트리 자체가 보호 대상 - "
        f"이 Bash 명령이 {target}에 쓰는 것으로 보임. 훅 스크립트/설정은 "
        "이 시스템 전체의 신뢰 전제라 사용자의 명시적, 그 자리에서의 "
        "사인오프 없이는 수정 불가. To override: add a trailing "
        f"`# HNCS-OVERRIDE: {HOOK_NAME}: <reason>` comment to this command."
    )
    decision = require_decision_or_deny(HOOK_NAME, SEVERITY, target, reason)
    if decision is None:
        return
    if is_subagent_call(data):
        deny(
            HOOK_NAME,
            reason + " 이 호출은 서브에이전트발이라(agent_id 있음) override를 "
            "받지 않음 - CRITICAL 등급에서 override는 self-servable이라는 게 "
            "가장 치명적인 지점이라, 훅 트리 수정의 서브에이전트발 시도는 "
            "override 불가로 막는다. 컨트롤러가 직접 실행할 것.",
            severity=SEVERITY, target=target, decision=decision,
        )
        return
    override_reason = bash_override(HOOK_NAME, command)
    if override_reason:
        allow_with_override(HOOK_NAME, SEVERITY, HOOK_NAME, target, override_reason,
                             decision=decision)
        return
    deny(HOOK_NAME, reason, severity=SEVERITY, target=target, decision=decision)


def _deny_or_sentinel_override(file_path, data):
    reason = (
        f"CLAUDE.md Never list을 실제로 강제하는 훅 트리 자체가 보호 대상 - "
        f"{file_path}는 이 시스템 전체의 신뢰 전제라 사용자의 명시적, 그 "
        "자리에서의 사인오프 없이는 수정 불가. To override: write "
        f'.claude/hooks/.pending_override.json with {{"rule": "{HOOK_NAME}", '
        f'"target": "{file_path}", "reason": "<reason>", "timestamp": '
        "<time.time()>}, then retry immediately."
    )
    decision = require_decision_or_deny(HOOK_NAME, SEVERITY, file_path, reason)
    if decision is None:
        return
    if is_subagent_call(data):
        deny(
            HOOK_NAME,
            reason + " 이 호출은 서브에이전트발이라(agent_id 있음) override를 "
            "받지 않음(CRITICAL). 컨트롤러가 직접 실행할 것.",
            severity=SEVERITY, target=file_path, decision=decision,
        )
        return
    override_reason = sentinel_override(HOOK_NAME, file_path)
    if override_reason:
        allow_with_override(HOOK_NAME, SEVERITY, HOOK_NAME, file_path, override_reason,
                             decision=decision)
        return
    deny(HOOK_NAME, reason, severity=SEVERITY, target=file_path, decision=decision)


def main():
    data = read_input()
    tool = data.get("tool_name")

    if tool == "Bash":
        command = str((data.get("tool_input") or {}).get("command", ""))
        target = bash_write_target(command)
        if target is None:
            allow()
            return
        _deny_or_bash_override(command, target, data)
        return

    if tool not in ("Edit", "Write", "MultiEdit"):
        allow()
        return
    file_path = (data.get("tool_input") or {}).get("file_path", "")
    if not is_protected_hook_path(file_path):
        allow()
        return
    _deny_or_sentinel_override(file_path, data)


if __name__ == "__main__":
    main()
