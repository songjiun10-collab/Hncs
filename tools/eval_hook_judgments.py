"""[maintenance] Decision Record 파이프라인(2026-08-16, `.claude/hooks/
_hook_common.py`의 `write_decision_record()`)이 남긴 "예측"과, 그 예측이
붙은 훅 결정의 실제 결과를 비교하는 리포트 도구. `tools/rotate_hook_logs.py`
와 같은 스타일 - 훅 체인에는 안 걸림, 수동 또는 Routine으로 가끔 실행.

이 스크립트가 하는 것: `.claude/hooks/violations_log.jsonl`/
`override_audit.jsonl`에서 `decision` 필드가 붙은 항목만 골라, 각 항목의
`decision_kind`에 따라 결과를 자동으로 분류한다 -

- `deny`: 아무것도 안 나감 -> "blocked".
- `ask`: 사람에게 프롬프트가 떴다는 것만 알 수 있고, 실제 답변(승인/거부)
  은 Claude Code 런타임이 훅 프로세스 밖에서 처리해서 **이 시스템 어디서도
  관측 불가능** -> "ask_unknown"(가짜 답을 지어내지 않는다).
- `log_and_allow`/`override`/`medium_approval`: 실제로 뭔가 나갔다는 뜻 -
  `git log`로 revert 커밋을 찾아 "reverted"/"not_reverted"로 분류(관찰
  기간이 아직 안 지났으면 "pending", 대상 커밋 자체를 못 찾으면
  "no_commit_signal").

`hybrid_engine/CLAUDE.md`의 "평균 차이만으로 승자를 부르지 않는다" 규율을
그대로 따라서, 표본이 `--min-n`(기본 20) 미만이면 severity 과대/과소평가
rate/verdict는 항상 `None`/"표본 부족" - raw count는 항상 보여주지만
퍼센트나 "경향"은 절대 작은 표본에서 단정하지 않는다.

  python3 -m tools.eval_hook_judgments                  # 리포트 출력 + learning_data.jsonl에 기록
  python3 -m tools.eval_hook_judgments --no-record       # 리포트만, 기록 안 함
  python3 -m tools.eval_hook_judgments --min-n 5
"""
import argparse
import json
import math
import os
import subprocess
from datetime import datetime, timedelta, timezone

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_VIOLATIONS_LOG = os.path.join(_REPO_ROOT, ".claude", "hooks", "violations_log.jsonl")
_DEFAULT_OVERRIDE_AUDIT_LOG = os.path.join(_REPO_ROOT, ".claude", "hooks", "override_audit.jsonl")
# tools/rotate_hook_logs.py의 _DEFAULT_LOGS에도 같은 경로가 3번째 항목으로
# 있음 - 두 파일이 독립 스크립트라는 관례(tools/CLAUDE.md)상 문자열을 그대로
# 중복시켰다. 이 파일 경로를 바꾸면 그쪽도 같이 바꿀 것.
_DEFAULT_LEARNING_DATA_LOG = os.path.join(_REPO_ROOT, ".claude", "hooks", "learning_data.jsonl")

_MIN_N_FOR_RATE = 20  # 이 미만이면 rate/verdict를 절대 안 냄, count만
_DEFAULT_REVERT_WINDOW_HOURS = 72
_DEFAULT_HIGH_CONFIDENCE = 0.7

# _hook_common.py의 SEVERITIES와 동일한 값 - tools/는 .claude/hooks/를 import
#하지 않는 독립 스크립트 관례(tools/CLAUDE.md)라 값만 복사, 심볼은 안 씀.
_SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

_OUTCOME_BLOCKED = "blocked"
_OUTCOME_ASK_UNKNOWN = "ask_unknown"
_OUTCOME_PENDING = "pending"
_OUTCOME_NO_COMMIT_SIGNAL = "no_commit_signal"
_OUTCOME_REVERTED = "reverted"
_OUTCOME_NOT_REVERTED = "not_reverted"


def _iter_jsonl(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def load_decision_events(violations_log_path=None, override_audit_log_path=None):
    """`violations_log.jsonl`에서 `decision` 필드가 있는 항목만 이벤트로
    반환한다 - `override_audit.jsonl`은 별도 이벤트로 추가하지 않고
    `git_sha`를 뒤에서 보강하는 용도로만 쓴다: `allow_with_override()`/
    `allow_with_medium_approval()`이 두 로그 모두에 같은 호출에 대한
    항목을 쓰기 때문에, override_audit 쪽도 독립 이벤트로 세면 같은
    실제 사건이 두 번 카운트된다. 매칭은 (rule/hook, target, timestamp)
    정확 일치 - 두 로그가 같은 함수 호출 안에서 거의 동시에 쓰여서
    보통 일치하지만, 실패해도(경계에 걸친 초 단위 차이 등) git_sha만
    비어있을 뿐 이벤트 자체는 그대로 남는다(best-effort 보강)."""
    violations_log_path = violations_log_path or _DEFAULT_VIOLATIONS_LOG
    override_audit_log_path = override_audit_log_path or _DEFAULT_OVERRIDE_AUDIT_LOG

    events = []
    for entry in _iter_jsonl(violations_log_path):
        if not entry.get("decision"):
            continue
        events.append({
            "timestamp": entry.get("timestamp"),
            "hook": entry.get("hook"),
            "severity": entry.get("severity"),
            "decision_kind": entry.get("decision_kind"),
            "overridden": entry.get("overridden"),
            "target": entry.get("target"),
            "decision": entry.get("decision"),
            "git_sha": None,
        })

    audit_git_sha = {}
    for entry in _iter_jsonl(override_audit_log_path):
        if not entry.get("decision"):
            continue
        key = (entry.get("rule"), entry.get("target"), entry.get("timestamp"))
        audit_git_sha[key] = entry.get("git_sha")

    for event in events:
        key = (event["hook"], event["target"], event["timestamp"])
        if key in audit_git_sha:
            event["git_sha"] = audit_git_sha[key]

    return events


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _run_git(args, repo_root=None, timeout=15):
    try:
        out = subprocess.run(["git"] + args, cwd=repo_root or _REPO_ROOT,
                              capture_output=True, text=True, timeout=timeout)
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def _parse_commit_lines(output):
    commits = []
    for line in output.splitlines():
        if "\x1f" not in line:
            continue
        sha, subject = line.split("\x1f", 1)
        commits.append((sha, subject))
    return commits


def commits_touching(target_path, since_ts, until_ts, repo_root=None):
    """target_path가 실제 레포 상대 파일 경로처럼 보일 때만 의미 있음 -
    호출자가 그 판단(`_looks_like_path()`)을 먼저 하고 부른다."""
    out = _run_git(
        ["log", "--follow", f"--since={_iso(since_ts)}", f"--until={_iso(until_ts)}",
         "--format=%H%x1f%s", "--", target_path],
        repo_root=repo_root,
    )
    return _parse_commit_lines(out)


def commits_since(since_ts, until_ts, repo_root=None):
    """경로 필터 없는 레포 전체 커밋 - target이 파일 경로가 아닐 때(브랜치
    이름, 셸 명령 전체 문자열 등)의 대략적인 fallback. "이 시간대에 뭐가
    커밋됐나"일 뿐, 가드된 액션과의 정확한 인과관계는 아니다."""
    out = _run_git(
        ["log", f"--since={_iso(since_ts)}", f"--until={_iso(until_ts)}", "--format=%H%x1f%s"],
        repo_root=repo_root,
    )
    return _parse_commit_lines(out)


def find_reverting_commit(subject, repo_root=None):
    """`git revert`가 기본으로 쓰는 `Revert "<원래 subject>"[...]` 형태의
    커밋 subject를 찾는다(이 세션이 실제로 만든
    `Revert "test: protect_test_coverage ask() 라이브 검증용..."` 커밋과
    같은 패턴). 찾으면 sha, 없으면 None."""
    out = _run_git(["log", "--all", "--format=%H%x1f%s"], repo_root=repo_root)
    prefix = f'Revert "{subject}"'
    for sha, s in _parse_commit_lines(out):
        if s.startswith(prefix):
            return sha
    return None


def _looks_like_path(target):
    if not target or "\n" in target or " " in target:
        return False
    return "/" in target or "." in target


def _parse_entry_timestamp(entry):
    try:
        return datetime.fromisoformat(entry["timestamp"])
    except (KeyError, TypeError, ValueError):
        return None


def classify_outcome(entry, repo_root=None, revert_window_hours=_DEFAULT_REVERT_WINDOW_HOURS, now=None):
    """decision_kind별 분류 - 모듈 docstring 참고. `ask`는 항상
    "ask_unknown"(실제 답변이 관측 불가능한 구조적 한계, 재발견될 버그가
    아님). `deny`는 항상 "blocked"(아무것도 안 나감, revert할 것도 없음).
    나머지(log_and_allow/override/medium_approval)는 실제로 뭔가 나갔다는
    뜻이라 시간 경과 + git log로 판정."""
    decision_kind = entry.get("decision_kind")
    if decision_kind == "deny":
        return _OUTCOME_BLOCKED
    if decision_kind == "ask":
        return _OUTCOME_ASK_UNKNOWN

    ts = _parse_entry_timestamp(entry)
    if ts is None:
        return _OUTCOME_NO_COMMIT_SIGNAL
    now = now or datetime.now(timezone.utc)
    window_end = ts + timedelta(hours=revert_window_hours)
    if now < window_end:
        return _OUTCOME_PENDING

    # The resulting commit can land any time between the decision and now -
    # revert_window_hours only gates *how long to wait* before concluding
    # "not reverted" (the "pending" check above), it is NOT the upper bound
    # for finding the original commit itself. find_reverting_commit()
    # separately searches all history (`git log --all`) with no time bound
    # at all, so a revert that happens long after this observation window
    # is still found correctly.
    since_ts, until_ts = ts.timestamp(), now.timestamp()
    target = entry.get("target")
    commits = []
    if _looks_like_path(target):
        commits = commits_touching(target, since_ts, until_ts, repo_root=repo_root)
    if not commits:
        commits = commits_since(since_ts, until_ts, repo_root=repo_root)
    if not commits:
        return _OUTCOME_NO_COMMIT_SIGNAL

    for _sha, subject in commits:
        if find_reverting_commit(subject, repo_root=repo_root):
            return _OUTCOME_REVERTED
    return _OUTCOME_NOT_REVERTED


def _severity_rank(severity):
    try:
        return _SEVERITIES.index(severity)
    except ValueError:
        return None


def _over_under_match(entry):
    decision = entry.get("decision") or {}
    self_rank = _severity_rank(decision.get("self_severity"))
    fixed_rank = _severity_rank(entry.get("severity"))
    if self_rank is None or fixed_rank is None:
        return None
    if self_rank > fixed_rank:
        return "over"
    if self_rank < fixed_rank:
        return "under"
    return "match"


def _sign_test_p(wins, losses):
    """`hybrid_engine/calibrate_profile.py`의 `_sign_test_p`를 로컬로
    복사 - tools/↔hybrid_engine/ 경계 넘어 private 심볼 import 안 함,
    tools/CLAUDE.md의 "실험끼리 결합 안 함"과 같은 원칙."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def _calibration_verdict(over_count, under_count, p_value, alpha=0.05):
    if p_value > alpha:
        return "유의미한 편향 없음"
    if over_count > under_count:
        return f"과대평가 경향(p={p_value:.4f})"
    return f"과소평가 경향(p={p_value:.4f})"


def compute_calibration(events, min_n=_MIN_N_FOR_RATE,
                         high_confidence_threshold=_DEFAULT_HIGH_CONFIDENCE,
                         repo_root=None, revert_window_hours=_DEFAULT_REVERT_WINDOW_HOURS,
                         now=None):
    """raw count는 항상 반환. severity 과대/과소평가의 rate/verdict는
    판정 가능한(determinable) 표본이 min_n 이상일 때만 채워짐 - 아니면
    None/"표본 부족", hybrid_engine/CLAUDE.md의 통계 규율과 같은 정신."""
    classified = [(e, classify_outcome(e, repo_root=repo_root,
                                        revert_window_hours=revert_window_hours, now=now))
                  for e in events]

    n_blocked = sum(1 for _, o in classified if o == _OUTCOME_BLOCKED)
    n_ask_unknown = sum(1 for _, o in classified if o == _OUTCOME_ASK_UNKNOWN)
    n_pending = sum(1 for _, o in classified if o == _OUTCOME_PENDING)
    n_no_commit_signal = sum(1 for _, o in classified if o == _OUTCOME_NO_COMMIT_SIGNAL)
    determinable = [(e, o) for e, o in classified if o in (_OUTCOME_REVERTED, _OUTCOME_NOT_REVERTED)]
    n_determinable = len(determinable)

    def _conf(e):
        return (e.get("decision") or {}).get("confidence") or 0.0

    high_total = sum(1 for e, _ in determinable if _conf(e) >= high_confidence_threshold)
    high_reverted = sum(1 for e, o in determinable
                         if _conf(e) >= high_confidence_threshold and o == _OUTCOME_REVERTED)
    low_total = n_determinable - high_total
    low_reverted = sum(1 for e, o in determinable
                        if _conf(e) < high_confidence_threshold and o == _OUTCOME_REVERTED)

    result = {
        "n_events": len(events),
        "n_blocked": n_blocked,
        "n_ask_unknown": n_ask_unknown,
        "n_pending": n_pending,
        "n_no_commit_signal": n_no_commit_signal,
        "n_determinable": n_determinable,
        "confidence_crosstab": {
            "high_confidence_total": high_total,
            "high_confidence_reverted": high_reverted,
            "low_confidence_total": low_total,
            "low_confidence_reverted": low_reverted,
        },
        "reverted_events": [e for e, o in classified if o == _OUTCOME_REVERTED],
    }

    if n_determinable >= min_n:
        over = sum(1 for e, _ in determinable if _over_under_match(e) == "over")
        under = sum(1 for e, _ in determinable if _over_under_match(e) == "under")
        match = sum(1 for e, _ in determinable if _over_under_match(e) == "match")
        p_value = _sign_test_p(over, under)
        result["severity_calibration"] = {
            "over_count": over, "under_count": under, "match_count": match,
            "p_value": p_value,
            "verdict": _calibration_verdict(over, under, p_value),
        }
    else:
        result["severity_calibration"] = {
            "over_count": None, "under_count": None, "match_count": None,
            "p_value": None,
            "verdict": f"표본 부족(insufficient_n, n={n_determinable} < min_n={min_n})",
        }

    return result


def render_report(calibration):
    lines = [
        f"decision-record 이벤트: {calibration['n_events']}개",
        f"  blocked(deny): {calibration['n_blocked']}",
        f"  ask_unknown(사람 답변 관측 불가): {calibration['n_ask_unknown']}",
        f"  pending(관찰 기간 안 지남): {calibration['n_pending']}",
        f"  no_commit_signal: {calibration['n_no_commit_signal']}",
        f"  판정 가능(determinable): {calibration['n_determinable']}",
    ]
    sc = calibration["severity_calibration"]
    if sc["p_value"] is None:
        lines.append(f"  severity 과대/과소평가: {sc['verdict']}")
    else:
        lines.append(
            f"  severity 과대/과소평가: 과대={sc['over_count']}, 과소={sc['under_count']}, "
            f"일치={sc['match_count']}, {sc['verdict']}"
        )
    ct = calibration["confidence_crosstab"]
    lines.append(
        f"  confidence x reverted: high_conf(>=threshold) "
        f"{ct['high_confidence_reverted']}/{ct['high_confidence_total']}, "
        f"low_conf {ct['low_confidence_reverted']}/{ct['low_confidence_total']}"
    )
    reverted = calibration["reverted_events"]
    if reverted:
        lines.append(f"\n반드시 사람이 확인할 것 - revert된 이벤트 {len(reverted)}개:")
        for e in reverted:
            d = e.get("decision") or {}
            lines.append(
                f"  - {e.get('hook')} / target={e.get('target')!r} / "
                f"self_severity={d.get('self_severity')} confidence={d.get('confidence')} "
                f"reason={d.get('reason')!r}"
            )
    else:
        lines.append("\nrevert된 이벤트 없음.")
    return "\n".join(lines)


def append_learning_data(calibration, out_path=None, now=None):
    """실행당 요약 레코드 1개만 추가 - 원본 이벤트는 이미
    violations_log.jsonl/override_audit.jsonl에 있으므로 여기엔 안 남김."""
    out_path = out_path or _DEFAULT_LEARNING_DATA_LOG
    now = now or datetime.now(timezone.utc)
    record = {
        "generated_at": now.isoformat(timespec="seconds"),
        "n_events": calibration["n_events"],
        "n_determinable": calibration["n_determinable"],
        "n_pending": calibration["n_pending"],
        "n_ask_unknown": calibration["n_ask_unknown"],
        "severity_calibration": calibration["severity_calibration"],
        "confidence_crosstab": calibration["confidence_crosstab"],
    }
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--violations-log", default=_DEFAULT_VIOLATIONS_LOG)
    parser.add_argument("--override-audit-log", default=_DEFAULT_OVERRIDE_AUDIT_LOG)
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--revert-window-hours", type=float, default=_DEFAULT_REVERT_WINDOW_HOURS)
    parser.add_argument("--min-n", type=int, default=_MIN_N_FOR_RATE)
    parser.add_argument("--high-confidence-threshold", type=float, default=_DEFAULT_HIGH_CONFIDENCE)
    parser.add_argument("--json-out", default=_DEFAULT_LEARNING_DATA_LOG)
    parser.add_argument("--no-record", action="store_true",
                         help="learning_data.jsonl에 안 남기고 리포트만 출력")
    args = parser.parse_args()

    events = load_decision_events(args.violations_log, args.override_audit_log)
    calibration = compute_calibration(
        events, min_n=args.min_n, high_confidence_threshold=args.high_confidence_threshold,
        repo_root=args.repo_root, revert_window_hours=args.revert_window_hours,
    )
    print(render_report(calibration))
    if not args.no_record:
        append_learning_data(calibration, out_path=args.json_out)


if __name__ == "__main__":
    main()
