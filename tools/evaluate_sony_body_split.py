"""연구용 - Sony 5바디(A7/A7R/A7S/A7 III/A7 IV)의 population 통계에서,
hybrid_engine.convert의 소스 역산이 브랜드 전체 pooled 타깃 대신
바디별 타깃을 쓰면 held-out 사진 예측이 더 정확해지는지 leave-one-out
으로 검증. 설계 근거:
docs/superpowers/specs/2026-08-05-sony-body-source-recognition-design.md.

sony_stats_result.csv(git-ignored, 115행 - 이미지 재디코드 없이 이
CSV만으로 평가 가능, core/stats.py의 image_stats() 결과가 이미
컬럼으로 들어있음)를 읽어, 사진 하나를 뺄 때마다 두 가지 예측을 만든다:
브랜드 pooled(나머지 114장 평균)과 바디별(같은 바디 나머지 22장 평균).
각 예측의 오차(|실제값 - 예측값|)를 b2(블랙p2)/w995(화이트p99.5) 따로
계산해서, 바디별로 5개씩 leave-one-out 페어드 비교를 만든다.

  python3 -m tools.evaluate_sony_body_split
"""
import csv
import math
import os

import numpy as np

CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sony_stats_result.csv")


def load_rows(csv_path=CSV_PATH):
    """CSV를 body/name/b2/w995만 남긴 dict 리스트로 반환. camera
    컬럼(예: "Sony A7 III")에서 "Sony " 접두어를 떼면 brands/sony.py
    docstring의 바디 키("A7 III" 등)와 정확히 일치한다."""
    rows = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            rows.append({
                "body": row["camera"].removeprefix("Sony "),
                "name": row["filename"],
                "b2": float(row["b2"]),
                "w995": float(row["w995"]),
            })
    return rows


def loo_errors(rows, stat_key):
    """rows(여러 바디가 섞인 리스트) 전체에 대해 held-out 사진마다
    (body, name, pooled_error, body_error) dict를 반환.
    pooled_error = |실제값 - (그 사진 뺀 전체 나머지 평균)|
    body_error  = |실제값 - (그 사진 뺀 같은 바디 나머지 평균)|"""
    out = []
    for i, row in enumerate(rows):
        others = rows[:i] + rows[i + 1:]
        pooled_pred = sum(r[stat_key] for r in others) / len(others)
        same_body = [r for r in others if r["body"] == row["body"]]
        body_pred = sum(r[stat_key] for r in same_body) / len(same_body)
        actual = row[stat_key]
        out.append({
            "body": row["body"],
            "name": row["name"],
            "pooled_error": abs(actual - pooled_pred),
            "body_error": abs(actual - body_pred),
        })
    return out


def _sign_test_p(wins, losses):
    """부호검정 양측 p값(정확 이항, 무승부 제외). scipy 의존 없이
    math.comb으로 직접 계산한다. tools/evaluate_hncs_blend.py에서
    그대로 복사(tools/CLAUDE.md: 공용 helper를 import하지 않고 각
    evaluate_*.py가 독립적으로 복사해서 쓴다)."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def summarize(per_fold, n_bootstrap=20000, seed=0):
    """페어드 비교 통계. per_fold의 각 행은 (name, value_a, value_b)
    - value_a가 기준(pooled 오차), value_b가 비교 대상(바디별 오차).
    오차는 낮을수록 좋으므로, value_b가 value_a보다 작을 때(=바디별
    예측이 더 정확) 개선폭이 양수가 된다. tools/evaluate_hncs_blend.py
    에서 그대로 복사."""
    a = np.array([row[1] for row in per_fold], dtype=np.float64)
    b = np.array([row[2] for row in per_fold], dtype=np.float64)
    n = len(per_fold)
    diff = a - b
    mean_a = float(a.mean())
    mean_b = float(b.mean())
    improvement_pct = (mean_a - mean_b) / mean_a * 100.0

    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())
    sd_diff = float(diff.std(ddof=1)) if n > 1 else 0.0
    sem_diff = sd_diff / math.sqrt(n) if n > 1 else 0.0
    t_stat = float(diff.mean() / sem_diff) if sem_diff > 0 else 0.0

    rng = np.random.default_rng(seed)
    boot_diff, boot_pct = [], []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, n)
        boot_diff.append(float(diff[idx].mean()))
        boot_pct.append(float((a[idx].mean() - b[idx].mean())
                              / a[idx].mean() * 100.0))
    ci_diff = tuple(float(v) for v in np.percentile(boot_diff, [2.5, 97.5]))
    ci_pct = tuple(float(v) for v in np.percentile(boot_pct, [2.5, 97.5]))

    dropone = []
    for i in range(n):
        keep = np.ones(n, dtype=bool)
        keep[i] = False
        dropone.append(float((a[keep].mean() - b[keep].mean())
                             / a[keep].mean() * 100.0))

    inconclusive = ci_diff[0] <= 0.0 <= ci_diff[1]
    if inconclusive:
        verdict = ("판정 보류 - 평균 차이가 0과 구분되지 않는다"
                   "(95% 부트스트랩 CI가 0을 포함)")
    elif improvement_pct > 0:
        verdict = "B가 이겼다"
    else:
        verdict = "A가 더 낫다"

    return {
        "n": n,
        "mean_a": mean_a,
        "mean_b": mean_b,
        "mean_diff": float(diff.mean()),
        "median_diff": float(np.median(diff)),
        "improvement_pct": improvement_pct,
        "b_wins": wins,
        "a_wins": losses,
        "sd_diff": sd_diff,
        "sem_diff": sem_diff,
        "t_stat": t_stat,
        "sign_test_p": _sign_test_p(wins, losses),
        "ci_diff": ci_diff,
        "ci_pct": ci_pct,
        "dropone_pct_min": min(dropone),
        "dropone_pct_max": max(dropone),
        "dropone_flips_sign": min(dropone) <= 0.0 <= max(dropone),
        "inconclusive": inconclusive,
        "verdict": verdict,
    }


def print_summary(s, label_a="A", label_b="B"):
    print()
    print(f"평균 {label_a} 오차 (n={s['n']}): {s['mean_a']:.3f}")
    print(f"평균 {label_b} 오차 (n={s['n']}): {s['mean_b']:.3f}")
    print(f"개선폭({label_b} 기준): {s['improvement_pct']:.1f}%")
    print(f"폴드 승패: {label_b} {s['b_wins']}승 {label_a} {s['a_wins']}패")
    print(f"페어드 차이({label_a}-{label_b}): 평균 {s['mean_diff']:+.3f} / 중앙값 "
          f"{s['median_diff']:+.3f} / 표준편차 {s['sd_diff']:.3f} "
          f"(t={s['t_stat']:.2f}, df={s['n'] - 1})")
    print(f"부호검정 양측 p = {s['sign_test_p']:.3f}")
    print(f"부트스트랩 95% CI - 평균 오차 차이: "
          f"[{s['ci_diff'][0]:+.3f}, {s['ci_diff'][1]:+.3f}] / "
          f"개선폭: [{s['ci_pct'][0]:+.1f}%, {s['ci_pct'][1]:+.1f}%]")
    print(f"drop-one 민감도: 한 장을 빼면 개선폭이 "
          f"{s['dropone_pct_min']:.1f}% ~ {s['dropone_pct_max']:.1f}% 사이로 움직인다"
          + (" (부호가 뒤집힌다)" if s["dropone_flips_sign"] else ""))
    print(f"판정: {s['verdict']}")


def main():
    rows = load_rows()
    bodies = sorted(set(r["body"] for r in rows))
    for stat_key, stat_label in (("b2", "블랙p2"), ("w995", "화이트p99.5")):
        errors = loo_errors(rows, stat_key)
        print(f"\n=== {stat_label} ({stat_key}) ===")
        for body in bodies:
            per_fold = [(e["name"], e["pooled_error"], e["body_error"])
                        for e in errors if e["body"] == body]
            print(f"\n--- {body} (n={len(per_fold)}) ---")
            for name, pooled_error, body_error in per_fold:
                print(f"  [{name}] pooled_error={pooled_error:.4f} "
                      f"body_error={body_error:.4f}")
            print(f"  PER_FOLD_{stat_key}_{body.replace(' ', '_')} = {per_fold!r}")
            s = summarize(per_fold)
            print_summary(s, label_a="pooled", label_b="바디별")


if __name__ == "__main__":
    main()
