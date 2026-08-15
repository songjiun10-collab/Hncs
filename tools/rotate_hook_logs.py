"""[maintenance] `.claude/hooks/violations_log.jsonl`과`override_audit.jsonl`은
append-only + git-tracked이라 계속 커진다 - 지금은 작지만(11줄), 몇 달 실사용
후엔 파일이 무거워지고 diff 노이즈도 커진다. 이 스크립트는 retention 기간보다
오래된 항목을 월별 아카이브 파일로 옮기고 활성 로그는 최근 것만 남긴다.

훅 체인에는 안 걸었다 - 매 툴콜마다 로그 파일 크기를 재는 건 불필요한
오버헤드다. 대신 가끔(예: 월 1회) 수동으로 돌리거나 Routine으로 스케줄.

  python3 -m tools.rotate_hook_logs                      # 기본 두 로그, 90일 보관
  python3 -m tools.rotate_hook_logs --retention-days 30
  python3 -m tools.rotate_hook_logs path/to/other.jsonl
"""
import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

_DEFAULT_LOGS = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 ".claude", "hooks", "violations_log.jsonl"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 ".claude", "hooks", "override_audit.jsonl"),
]


def _parse_timestamp(entry):
    """entry["timestamp"]는 isoformat(timespec="seconds") - "+00:00"
    오프셋 형태(_hook_common.py가 항상 UTC로 씀). 못 읽으면 None(그런
    항목은 안전하게 "최근"으로 취급해 보관한다 - 잘못 지우는 것보다
    안전)."""
    try:
        return datetime.fromisoformat(entry["timestamp"])
    except (KeyError, TypeError, ValueError):
        return None


def rotate(log_path, retention_days=90, now=None):
    """log_path의 항목을 훑어 retention_days보다 오래된 것을 월별
    <log_path 베이스이름>.<YYYY-MM>.jsonl로 옮기고, 활성 로그는 최근
    항목만 남긴다. 여러 번 돌려도 안전(archived 항목은 활성 로그에서
    제거되므로 재실행 시 다시 안 걸림). 반환값: {"kept": n, "archived":
    {"YYYY-MM": n, ...}}."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days)

    if not os.path.exists(log_path):
        return {"kept": 0, "archived": {}}

    with open(log_path, encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]

    kept_lines = []
    archived_by_month = defaultdict(list)

    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            kept_lines.append(line)  # 파싱 안 되는 줄은 안전하게 보관
            continue
        ts = _parse_timestamp(entry)
        if ts is None or ts >= cutoff:
            kept_lines.append(line)
        else:
            archived_by_month[ts.strftime("%Y-%m")].append(line)

    if not archived_by_month:
        return {"kept": len(kept_lines), "archived": {}}

    base, ext = os.path.splitext(log_path)
    counts = {}
    for month, month_lines in archived_by_month.items():
        archive_path = f"{base}.{month}{ext}"
        with open(archive_path, "a", encoding="utf-8") as f:
            f.writelines(month_lines)
        counts[month] = len(month_lines)

    with open(log_path, "w", encoding="utf-8") as f:
        f.writelines(kept_lines)

    return {"kept": len(kept_lines), "archived": counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="*", default=_DEFAULT_LOGS,
                         help="회전시킬 .jsonl 로그 경로들 (기본: violations_log/override_audit)")
    parser.add_argument("--retention-days", type=int, default=90,
                         help="활성 로그에 남길 최근 기간(기본 90일)")
    args = parser.parse_args()

    for log_path in args.logs:
        result = rotate(log_path, retention_days=args.retention_days)
        if result["archived"]:
            archived_desc = ", ".join(f"{m}: {n}개" for m, n in sorted(result["archived"].items()))
            print(f"{log_path}: {result['kept']}개 유지, 아카이브됨 ({archived_desc})")
        else:
            print(f"{log_path}: {result['kept']}개 유지, 아카이브 대상 없음")


if __name__ == "__main__":
    main()
