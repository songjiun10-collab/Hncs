"""Shared allow/deny/override helpers for this project's PreToolUse/
PostToolUse hooks.

## Severity tiers (2026-08 redesign, user-specified)

- LOW: allow, log only (no interruption).
- MID/HIGH/CRITICAL: deny unless a valid override is present (see below).
  Mechanically identical across all three tiers - severity is now purely
  a label/messaging-tone distinction, not a different code path.

**정정(2026-08-15)**: MID originally used `permissionDecision: "ask"`
(falls through to Claude Code's normal interactive permission prompt) on
the theory that a human glance beats a hard block for lower-stakes
findings. Dispatched a real subagent to test whether this hook chain
applies to subagent tool calls at all, and found: Bash-triggered deny
hooks (e.g. `protect_destructive.py`) correctly blocked the subagent, but
an `ask()`-based hook (`protect_claim_evidence.py`) let the subagent's
Edit through with no prompt and no denial - there's no interactive
surface to render the prompt on inside a subagent's own turn, so it
silently resolved to allow. Since this project's normal workflow is a
Controller dispatching Implementer/Reviewer subagents to do the actual
work, `ask()` provided zero protection in exactly that case. All three
`ask()`-using hooks were converted to deny+override; `ask()` remains
defined below (still valid, still used if some future hook genuinely
only ever fires on direct orchestrator calls) but no active hook calls it
as of this correction. The `_hook_common.py` git_sha handling below was
also never actually a CRITICAL-only gate - see the note in
`_record_override()`.

**추가 재설계 (2026-08-15, 사용자 확정 스펙)**: 4단계를 실제로 다르게
동작시킨다 -

- LOW: `log_and_allow()` - 항상 allow, 로그만(기존 그대로).
- MEDIUM: "상위 에이전트가 허용하면 실행 에이전트가 실행, 단 주의사항
  전달." 일반 override(자기 자신이 사유를 써서 통과)에 더해,
  `record_agent_approval.py`(PostToolUse, Agent matcher)가 실제
  디스패치된 서브에이전트의 응답에서 `MEDIUM-APPROVE: <rule> ::
  <target> :: <caution>` 마커를 파싱하고(2026-08-16 정정: "에이전트는
  오퍼스 허락만 유효" - 모델이 opus일 때만 인정, sonnet도 불인정)
  `medium_approval()`로 소비 가능한 승인을 기록한다 - 자기 자신이
  바로 못 쓰고 진짜 Agent 디스패치가 있어야 생기는 sentinel이라 일반
  override보다 위조 난이도가 한 단계 높다. 통과시킬 때 caution 문구는
  `write_pending_caution()`으로 `tool_use_id`에 묶어 기록하고,
  `deliver_caution.py`(PostToolUse, Edit|Write|MultiEdit matcher)가 같은
  `tool_use_id`로 찾아서 `additionalContext`로 실행 에이전트한테
  전달한다 - PreToolUse의 "allow" 시 `permissionDecisionReason`은 모델한테
  전달 안 된다는 게 문서상 확정이라(2026-08-15 claude-code-guide 조사),
  PostToolUse의 `additionalContext`(같은 툴 결과에 append, 문서상 확정)로
  우회했다.
- HIGH: "사람 승인." `is_subagent_call(data)`로 분기 - 오케스트레이터
  직접 호출(agent_id 없음)이면 `ask()`(실측 확인된 대로 실제 사람
  프롬프트가 뜬다), 서브에이전트발 호출(agent_id 있음)이면 override
  없이는 무조건 deny(ask()가 서브에이전트에서 fail-open이라는 걸 이미
  확인했으므로 - 위 정정 항목 참고). override는 두 경로 모두에서 여전히
  유효한 사전 선언 우회.
- CRITICAL: `protect_never_touch.py`/`protect_destructive.py`/
  `protect_push_safety.py`(force-push)에서 서브에이전트발 호출은
  override조차 받지 않고 무조건 deny - "override는 self-servable"이라는
  한계가 가장 치명적인 등급이라, 서브에이전트가 스스로 bash 주석/sentinel
  파일을 써서 통과하는 경로 자체를 없앴다. 오케스트레이터 직접 호출은
  기존 override 메커니즘 그대로(이 세션의 learned-LUT 리팩토링이 바로
  이 경로로 진행됐다).

## Override mechanism

The point (user's own framing): "훅은 개발자를 대신해 판단하지 않는다.
훅은 '위험한 행동을 무의식적으로 해버리는 것'만 막는다" - hooks don't
substitute for the developer's judgment; they only stop an unconscious/
silent slide into a dangerous action. A deliberate, explicitly-declared
override is always allowed through, but it leaves a permanent trace of
why.

Two ways to declare an override, matching the two hook trigger shapes:

1. **Bash-triggered guards** (destructive ops, push safety): the command
   text itself carries a trailing marker comment -
   `... # HNCS-OVERRIDE: <rule>: <reason>`. Parsed by `bash_override()`.
2. **Edit/Write/MultiEdit-triggered guards** (never-touch): tool_input has
   no room for a custom field, so the override is declared via a sentinel
   file written *before* the guarded call - `.claude/hooks/
   .pending_override.json` (`{"rule", "target", "reason", "timestamp"}`).
   Checked (and consumed - single use) by `sentinel_override()`.

Every successful override is logged to `override_audit.jsonl` (separate
from `violations_log.jsonl`, which is for calls that were actually
blocked) with `{timestamp, rule, severity, target, reason, git_sha}` -
`git_sha` is always computed here, never taken from the caller, so the
audit trail can't be backdated or spoofed by whatever wrote the marker."""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
_LOG_PATH = os.environ.get(
    "HNCS_HOOK_VIOLATIONS_LOG", os.path.join(_HOOKS_DIR, "violations_log.jsonl"))
_OVERRIDE_AUDIT_PATH = os.environ.get(
    "HNCS_HOOK_OVERRIDE_AUDIT_LOG", os.path.join(_HOOKS_DIR, "override_audit.jsonl"))
_SENTINEL_PATH = os.environ.get(
    "HNCS_HOOK_OVERRIDE_SENTINEL", os.path.join(_HOOKS_DIR, ".pending_override.json"))
_MEDIUM_APPROVAL_PATH = os.environ.get(
    "HNCS_HOOK_MEDIUM_APPROVAL_SENTINEL",
    os.path.join(_HOOKS_DIR, ".pending_medium_approval.json"))
_PENDING_CAUTION_PATH = os.environ.get(
    "HNCS_HOOK_PENDING_CAUTION", os.path.join(_HOOKS_DIR, ".pending_caution.json"))

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

_BASH_OVERRIDE_RE = re.compile(
    r"#\s*HNCS-OVERRIDE:\s*(?P<rule>[\w.-]+)\s*:\s*(?P<reason>.+?)\s*$")

_SENTINEL_MAX_AGE_SECONDS = 600  # 10min - forces a fresh, deliberate write
_MEDIUM_APPROVAL_MAX_AGE_SECONDS = 600


def allow():
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "allow"}}))


def log_and_allow(hook_name, severity, reason):
    """LOW tier: record the finding to violations_log.jsonl (so it's
    visible to a human reviewing the log later) but never interrupt the
    call - no deny, no ask, no override needed. For findings real enough
    to be worth a durable trace but not real enough to justify friction on
    the current action (e.g. a missing Agent `model` field - a cost
    nit, not a correctness/safety issue)."""
    _log_event(hook_name, severity, reason, overridden=False)
    allow()


def is_subagent_call(data):
    """True if this PreToolUse/PostToolUse hook input came from a
    dispatched subagent's own tool call rather than the direct
    orchestrator - detected via the `agent_id` field, confirmed
    empirically (2026-08-15, live subagent dispatch + diagnostic hook) to
    be present only on subagent-originated calls, absent on direct
    orchestrator calls."""
    return "agent_id" in data


def ask(hook_name, severity, reason):
    """HIGH tier's default path for a DIRECT orchestrator call only
    (agent_id absent from the hook input - check with is_subagent_call()
    before calling this). Hands off to Claude Code's own interactive
    permission prompt - human approves/denies, in the moment, through the
    normal UI. Confirmed live (2026-08-15) to actually surface a real
    prompt for direct calls, both approved and denied independently.

    NEVER call this when is_subagent_call(data) is True: confirmed live
    that ask() silently resolves to allow with no prompt at all inside a
    dispatched subagent's own turn - there's no interactive surface to
    render it on. That fail-open behavior is exactly why the 3 former
    MID-tier ask() users were converted to deny+override (see the
    2026-08-15 correction above); HIGH's use of ask() here is safe only
    because it's gated on agent_id being absent.

    Logged like deny() so violations_log.jsonl carries every HIGH-tier
    trigger, not only the ones a human happened to deny."""
    _log_event(hook_name, severity, reason, overridden=False)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "ask",
        "permissionDecisionReason": reason}}))


def high_tier_decision(hook_name, severity, reason, data):
    """Shared HIGH-tier default-path decision, used AFTER a caller has
    already checked for and found no override. Branches on
    is_subagent_call(data): a direct orchestrator call gets a real ask()
    prompt; a subagent-originated call gets a hard deny (no ask fallback,
    since ask() fails open there) - the subagent must either have a
    pre-declared override, or the action must be re-run directly by the
    orchestrator where a human can actually be asked."""
    if is_subagent_call(data):
        deny(
            hook_name,
            reason + " 이 호출은 서브에이전트발이라(agent_id 있음) ask() "
            "프롬프트를 띄울 화면이 없음(2026-08-15 실측 확인) - 사람 "
            "승인을 받으려면 컨트롤러가 이 액션을 직접 실행하거나, "
            "디스패치 전에 override를 미리 declare할 것.",
            severity=severity,
        )
    else:
        ask(hook_name, severity, reason)


def deny(hook_name, reason, severity="HIGH"):
    _log_event(hook_name, severity, reason, overridden=False)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": reason}}))


def allow_with_override(hook_name, severity, rule, target, reason):
    """MID/HIGH/CRITICAL tier, override matched: log to both the violations
    log (so the near-miss is visible in the same place as a real deny)
    and the override audit log (so it's separately searchable), then
    allow."""
    note = f"OVERRIDDEN ({severity}, rule={rule}): {reason}"
    _log_event(hook_name, severity, note, overridden=True)
    _record_override(rule, severity, target, reason)
    allow()


def bash_override(rule, command):
    """Parses a trailing `# HNCS-OVERRIDE: <rule>: <reason>` marker out of
    a Bash command string. Returns the reason string if present and the
    rule name matches, else None. Does not care where in the command the
    marker appears (checked line by line) - shell comments are valid
    anywhere a new logical line/statement can start."""
    for line in command.splitlines():
        m = _BASH_OVERRIDE_RE.search(line)
        if m and m.group("rule") == rule and m.group("reason").strip():
            return m.group("reason").strip()
    return None


def sentinel_override(rule, target):
    """Checks `.pending_override.json` for a fresh (<=10min old), matching
    (same rule + same target) override request, and consumes it (deletes
    the file) if found. Returns the reason string, or None. `target`
    comparison is exact-string - callers should normalize paths the same
    way on both sides (write and check)."""
    if not os.path.exists(_SENTINEL_PATH):
        return None
    try:
        with open(_SENTINEL_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    try:
        age = time.time() - float(data.get("timestamp", 0))
    except (TypeError, ValueError):
        return None
    if age > _SENTINEL_MAX_AGE_SECONDS:
        return None
    if data.get("rule") != rule or data.get("target") != target:
        return None
    reason = str(data.get("reason") or "").strip()
    if not reason:
        return None
    try:
        os.remove(_SENTINEL_PATH)
    except OSError:
        pass
    return reason


def write_sentinel_override(rule, target, reason):
    """Writes the pending-override sentinel. Called by the agent (via a
    Write tool call to this exact path) immediately before the guarded
    Edit/Write/MultiEdit call it's meant to unblock. Not called by hook
    scripts themselves - this is here so the one write site has a single,
    documented implementation instead of ad-hoc JSON construction."""
    with open(_SENTINEL_PATH, "w", encoding="utf-8") as f:
        json.dump({"rule": rule, "target": target, "reason": reason,
                    "timestamp": time.time()}, f)


def medium_approval(rule, target):
    """MEDIUM tier's "상위 에이전트 승인" path. Checks
    `.pending_medium_approval.json` for a fresh (<=10min), matching (same
    rule + target) approval written by record_agent_approval.py's
    PostToolUse hook after parsing a `MEDIUM-APPROVE: <rule> :: <target>
    :: <caution>` marker out of an actual dispatched subagent's response
    (only recorded if that dispatch used opus specifically - 2026-08-16
    correction, sonnet no longer counts). Unlike the plain
    override sentinel, the calling hook/agent can't write this file
    directly - it only exists after a real Agent dispatch produced a
    matching response, so it's a stronger signal than a bare self-
    declared override, though not proof against a controller writing a
    fake approving dispatch (the "override is self-servable" limitation
    in README.md applies here too, just one level removed).

    Returns the caution string, or None. Consumes (deletes) on match."""
    if not os.path.exists(_MEDIUM_APPROVAL_PATH):
        return None
    try:
        with open(_MEDIUM_APPROVAL_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    try:
        age = time.time() - float(data.get("timestamp", 0))
    except (TypeError, ValueError):
        return None
    if age > _MEDIUM_APPROVAL_MAX_AGE_SECONDS:
        return None
    if data.get("rule") != rule or data.get("target") != target:
        return None
    caution = str(data.get("caution") or "").strip()
    if not caution:
        return None
    try:
        os.remove(_MEDIUM_APPROVAL_PATH)
    except OSError:
        pass
    return caution


def write_medium_approval(rule, target, caution):
    """Called by record_agent_approval.py after parsing a genuine
    MEDIUM-APPROVE marker out of a dispatched subagent's response - not
    called by the guarded hook itself, and not meant to be written
    ad-hoc by an agent the way write_sentinel_override() is."""
    with open(_MEDIUM_APPROVAL_PATH, "w", encoding="utf-8") as f:
        json.dump({"rule": rule, "target": target, "caution": caution,
                    "timestamp": time.time()}, f)


def allow_with_medium_approval(hook_name, severity, rule, target, caution):
    """MEDIUM tier, higher-agent approval matched (medium_approval()):
    log like an override (visible in violations_log.jsonl next to real
    denials, plus a separate override_audit.jsonl entry tagged with the
    caution text) and allow. Delivering the caution text to the executing
    agent is a separate step (write_pending_caution() + deliver_caution.py)
    - this function only records that the approval was consumed."""
    note = f"MEDIUM-APPROVED (rule={rule}): {caution}"
    _log_event(hook_name, severity, note, overridden=True)
    _record_override(rule, severity, target, f"[상위 에이전트 승인] {caution}")
    allow()


def write_pending_caution(tool_use_id, caution):
    """Records a caution message for delivery via deliver_caution.py's
    PostToolUse hook once the just-approved call actually completes,
    correlated by tool_use_id - present on both the PreToolUse and
    PostToolUse hook input for the same call (confirmed empirically
    2026-08-15). Single-record, like this project's other sentinel files:
    only the most recently written caution is deliverable."""
    if not tool_use_id:
        return
    with open(_PENDING_CAUTION_PATH, "w", encoding="utf-8") as f:
        json.dump({"tool_use_id": tool_use_id, "caution": caution,
                    "timestamp": time.time()}, f)


def pop_pending_caution(tool_use_id):
    """Consumes and returns the caution text queued for `tool_use_id` via
    write_pending_caution(), or None if there isn't one."""
    if not tool_use_id or not os.path.exists(_PENDING_CAUTION_PATH):
        return None
    try:
        with open(_PENDING_CAUTION_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if data.get("tool_use_id") != tool_use_id:
        return None
    caution = str(data.get("caution") or "").strip()
    try:
        os.remove(_PENDING_CAUTION_PATH)
    except OSError:
        pass
    return caution or None


def current_head_sha():
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=_repo_root(),
                              capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def _repo_root():
    return os.path.dirname(os.path.dirname(_HOOKS_DIR))


def _record_override(rule, severity, target, reason):
    """git_sha is recorded for every override regardless of severity - it's
    an audit-trail field (proves which commit the override was granted
    at), not a gating check. An earlier docstring draft implied CRITICAL
    required the override's git_sha to match current HEAD as an extra
    verification step; that was never implemented - `sentinel_override()`/
    `bash_override()` don't branch on severity at all. Fixed in place
    rather than silently rewritten, per this project's own "append a
    dated correction" convention."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": rule,
        "severity": severity,
        "target": target,
        "reason": reason,
        "git_sha": current_head_sha(),
    }
    try:
        with open(_OVERRIDE_AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[_hook_common] failed to write override audit log: {e}",
              file=sys.stderr)


def _log_event(hook_name, severity, reason, overridden):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hook": hook_name,
        "severity": severity,
        "overridden": overridden,
        "reason": reason,
    }
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[_hook_common] failed to write violations log: {e}",
              file=sys.stderr)
