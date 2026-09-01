#!/usr/bin/env python3
"""PreToolUse hook (matcher: Edit|Write|MultiEdit), MEDIUM severity. Scoped
to README.md/README.ko.md/CLAUDE.md/hybrid_engine/EVALUATION.md (any
CLAUDE.md in the tree, not just root - project convention is per-
directory CLAUDE.md files). Root CLAUDE.md: "Make every claim checkable:
name the file, show the number, quote the command you actually ran."

Heuristic: if the text being added contains a numeric performance/scale
claim (%, "배"/"times faster", a bare count like "N brands"/"N presets")
with no nearby evidence marker (a command in backticks, a file path, "실행"
/"확인"/"로그"/"run"/"log"/"verified"), it flags it. Many legitimate doc
edits add a number that's already obviously checkable from context (e.g.
table row counts) without restating the command inline every time, so
this is MEDIUM (softer default), not HIGH/CRITICAL.

**정정(2026-08-15)**: 원래 `ask()`(사람 확인 프롬프트)를 썼는데, 서브
에이전트로 실측한 결과 디스패치된 subagent의 Edit 콜에서는 `ask()`가
아무 denial도 ask 프롬프트도 없이 그냥 조용히 통과됨(subagent 컨텍스트엔
프롬프트를 띄울 화면이 없어서로 추정 - fail-open 방향). 이 프로젝트의
평상시 워크플로우가 Controller가 subagent를 디스패치해서 실제 작업을
시키는 구조라, `ask()`는 정확히 그 경우에 보호 기능이 0이 됨. deny +
override로 바꿔서 orchestrator든 subagent든 동일하게 동작하도록 함(둘 다
결정론적 파일/텍스트 체크지 UI 렌더링에 안 기댐) - MEDIUM 등급 라벨은
유지하되(정말 사소한 건 override 한 줄로 바로 뚫림), 메커니즘은 HIGH와
같은 sentinel override.

**정정(2026-08-16)**: "그 애매한 중간단계?" - plain self-declared
override가 MEDIUM-APPROVE와 나란히 열려있으니 컨트롤러가 항상 더 쉬운
쪽(override 한 줄)을 써서 "상위 에이전트 승인" 경로가 사실상 죽은
코드였음. **plain override 제거, MEDIUM-APPROVE(opus 전용)만 유효**.

**정정(2026-08-20, README "알려진 한계" 2차 라운드 #9/#10/#11, 7차,
8차 - 4개 실측 결함 수정)**: 원래 근거-마커 체크가 전체 텍스트에 대해
"패턴이 어딘가 있냐"만 boolean으로 봐서 (1) `log\b`에 앞쪽 경계가 없어
"catalog"/"backlog" 같은 무관한 단어에도 매칭됐고, (2) `.py`/`.md`
마커는 그 파일이 실제로 존재하는지 전혀 확인 안 했고(존재하지 않는
파일 언급도 통과), (3) 주장-근거 짝짓기가 "같은 문장/근처"가 아니라
"편집 텍스트 전체 어딘가"라서 진짜 근거가 있는 한 문장이 완전히
무관한 다른 무근거 주장까지 무임승차시켰고, (4) backtick 마커는 안
내용을 전혀 안 봐서 `\`이거 그냥 지어낸 숫자임\`` 같은 자기모순
텍스트도 근거로 쳤다. 문장 단위로 쪼개서 각 주장 근처(같은 문장 ±1)에
실제로 그럴듯한 근거가 있는지 확인하도록 다시 짰다."""
import json
import os
import re
import sys

from _hook_common import (_repo_root, allow, allow_with_medium_approval, deny,
                           medium_approval, require_decision_or_deny,
                           write_pending_caution)

HOOK_NAME = "protect_claim_evidence"
SEVERITY = "MEDIUM"

_TARGET_FILE_RE = re.compile(
    r"(^|/)(README(\.\w+)?\.md|CLAUDE\.md|hybrid_engine/EVALUATION\.md)$")

_NUMERIC_CLAIM_RE = re.compile(
    r"[+-]?\d+(?:\.\d+)?\s*%|"          # +9.12%, 15%
    r"\d+\s*(?:x|배)|"                  # 3x faster, 2배 - no trailing \b:
    r"\b\d+\s*(?:brands?|presets?|프리셋|브랜드|pairs?|쌍)",
    # ^ no trailing \b: Korean particles attach directly to an English
    # word/number with no space ("15 brands를"), and \w is unicode-aware
    # so \b doesn't fire between "brands" and "를" - both count as "word"
    # characters to Python's re module.
    re.IGNORECASE,
)
_BACKTICK_RE = re.compile(r"`([^`]+)`")
# A backtick-quoted evidence marker must itself look like a command or
# path - contains a path separator, a recognized extension, or a space
# (command-with-args shape) - not just any word someone put in backticks.
_PLAUSIBLE_BACKTICK_CONTENT_RE = re.compile(r"[/\\]|\.\w{1,5}\b|\s")
_TEXT_EVIDENCE_MARKER_RE = re.compile(
    r"실행|확인됨|검증|\blog\b|\brun\b|\bverified\b", re.IGNORECASE)
# .py/.md mentions count as evidence only if that file actually exists -
# extracted separately from _TEXT_EVIDENCE_MARKER_RE so main() can check
# existence before accepting the match.
_FILE_MENTION_RE = re.compile(r"[\w./-]+\.(?:py|md)\b", re.IGNORECASE)

# Sentence-ish split: after ., !, ? or a newline, followed by whitespace.
# Approximate on purpose (same "text-pattern based" tradeoff as every
# other hook here) - good enough to separate the claims that actually
# appear in this project's docs, not a real NLP sentence boundary.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?\n])\s+")


def read_input():
    return json.load(sys.stdin)


def is_claim_bearing_doc(path):
    return bool(_TARGET_FILE_RE.search((path or "").replace(os.sep, "/")))


def has_evidence_marker(sentence):
    if _TEXT_EVIDENCE_MARKER_RE.search(sentence):
        return True
    for content in _BACKTICK_RE.findall(sentence):
        if _PLAUSIBLE_BACKTICK_CONTENT_RE.search(content):
            return True
    for mention in _FILE_MENTION_RE.findall(sentence):
        if os.path.exists(os.path.join(_repo_root(), mention)):
            return True
    return False


def unbacked_claim_reason(added_text):
    # Same-sentence only, deliberately - README round 8 finding #10 was
    # specifically that "an adjacent sentence has real evidence" let an
    # unrelated claim vouch off it. A ±1-sentence window closes most of
    # the whole-text-boolean gap but still lets exactly that pattern
    # through (a genuinely backed claim right next to an unrelated
    # unbacked one) - same-sentence is the tighter bound the finding
    # actually asked for ("각 주장 근처에 각자의 근거"). Costs some
    # false positives on the legitimate "claim here, evidence next
    # clause" writing pattern - MEDIUM tier's opus-approval override
    # exists for exactly that case.
    sentences = _SENTENCE_SPLIT_RE.split(added_text)
    for sentence in sentences:
        if not _NUMERIC_CLAIM_RE.search(sentence):
            continue
        if has_evidence_marker(sentence):
            continue
        return (
            f"This addition contains a numeric claim (\"{sentence.strip()[:80]}\") "
            "with no nearby evidence marker (a real command/path in backticks, "
            "a file that actually exists, or 'verified/run/log' mention). "
            "Root CLAUDE.md: \"Make every claim checkable: name the file, "
            "show the number, quote the command you actually ran.\" Confirm "
            "this number is backed by something checkable, near the claim "
            "itself - not just somewhere else in this same edit."
        )
    return None


def main():
    data = read_input()
    tool = data.get("tool_name")
    if tool not in ("Edit", "Write", "MultiEdit"):
        allow()
        return
    ti = data.get("tool_input") or {}
    file_path = ti.get("file_path", "")
    if not is_claim_bearing_doc(file_path):
        allow()
        return

    if tool == "Write":
        added_text = ti.get("content", "")
    elif tool == "MultiEdit":
        added_text = "\n".join(e.get("new_string", "") for e in (ti.get("edits") or []))
    else:
        added_text = ti.get("new_string", "")

    reason = unbacked_claim_reason(added_text)
    if reason is None:
        allow()
        return

    decision = require_decision_or_deny(HOOK_NAME, SEVERITY, file_path, reason)
    if decision is None:
        return

    caution = medium_approval(HOOK_NAME, file_path)
    if caution is not None:
        write_pending_caution(data.get("tool_use_id"), caution)
        allow_with_medium_approval(HOOK_NAME, SEVERITY, HOOK_NAME, file_path, caution,
                                    decision=decision)
        return

    deny(
        HOOK_NAME,
        f"{reason} No plain override for MEDIUM (2026-08-16: removed - it "
        "made the opus-approval path pointless since a one-line override "
        "was always easier). Dispatch an opus Agent whose response "
        f'contains "MEDIUM-APPROVE: {HOOK_NAME} :: {file_path} :: <caution>" '
        "- the next matching call will be let through with that caution "
        "delivered back to you.",
        severity=SEVERITY, target=file_path, decision=decision,
    )


if __name__ == "__main__":
    main()
