# Sony Body-Level Source Recognition (Pilot) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure, with leave-one-out cross-validation and significance testing, whether per-camera-body `toe_lift`/`white_point` targets predict a held-out Sony photo's own black/white point better than the existing brand-pooled targets — per body, individually.

**Architecture:** A new standalone research script (`tools/evaluate_sony_body_split.py`) reads the already-collected per-image population statistics (`sony_stats_result.csv`, 115 rows: 5 Sony bodies x n=23), and for every image computes two competing LOO predictions of that image's own `b2` (black p2) and `w995` (white p99.5): the brand-pooled mean (over the other 114 images, any body) and the body-specific mean (over the other 22 images of the same body). It reuses `tools/evaluate_hncs_blend.py`'s `summarize()`/`_sign_test_p()`/`print_summary()` verbatim (copied, not imported, per `tools/CLAUDE.md`) to run the project's standard 4-part significance test per body per statistic (10 tests total: 5 bodies x {b2, w995}).

**This plan stops at measurement + recording the result in `hybrid_engine/EVALUATION.md`.** It does **not** wire any per-body override into `hybrid_engine/core/preset_inverse.py` or `hybrid_engine/convert.py` — per root `CLAUDE.md`'s "never ship an experimental result automatically" rule and this repo's established practice (the illuminant-blend experiment's win on 2026-08-03 still isn't wired into shipped `hybrid_engine.convert` either). If the results support adopting one or more bodies, that's a separate follow-up task gated on the owner reviewing the real numbers this plan produces — the design for that wiring (`SONY_MODEL_CODES`, `detect_body_from_exif()`, `curve_params(brand, body=None)`, and their unit tests) is already fully specified in the spec's "구현 설계" and "테스트" sections for whenever that follow-up happens; this plan does not implement or test any of it.

**Tech Stack:** Python 3, `numpy` (already a dependency, via the copied `summarize()`), `unittest`, standard-library `csv`/`math`.

## Global Constraints

- `brands/sony.py`'s `apply_sony_look()` must NEVER be modified — this plan only reads population numbers already recorded in its docstring/source data, never touches the function itself.
- `hybrid_engine/core/preset_inverse.py`, `hybrid_engine/convert.py` are **not modified by this plan** (see Architecture above).
- Data source: `sony_stats_result.csv` at the repo root (115 rows, header `camera,filename,url,b2,w995,med,sat,dark_pct`) - **git-ignored**, already present in this environment. Never re-scrape or re-download; if it's missing, stop and report `BLOCKED` rather than fabricating numbers.
- Body key format: strip the `"Sony "` prefix from the CSV's `camera` column to get the body key (`"Sony A7 III"` -> `"A7 III"`) - this must exactly match the body names already used in `brands/sony.py`'s docstring (`A7`, `A7R`, `A7S`, `A7 III`, `A7 IV`).
- Statistics: copy `summarize()`, `_sign_test_p()`, and `print_summary()` from `tools/evaluate_hncs_blend.py:369-461` verbatim into the new script - do not import them (`tools/CLAUDE.md`: "Standalone. Never import from a sibling `evaluate_*.py` — copy the loader instead"). `summarize()`'s bootstrap uses `n_bootstrap=20000, seed=0` (its defaults) - do not change them.
- In `summarize(per_fold, ...)`, `per_fold` rows are `(name, value_a, value_b)` and **lower value_b is a win for b** - value_a must be the pooled-prediction error, value_b the body-prediction error, so that "b가 이겼다" means the body-specific target predicted better.
- A body is only a genuine win if **both** `b2` and `w995` tests independently produce a bootstrap 95% CI that does not straddle zero in the "body wins" direction - report each body's verdict for both statistics separately, do not average them into one number.
- Record the real result honestly in `hybrid_engine/EVALUATION.md` regardless of outcome (win, loss, or inconclusive, per body) - a body failing (A7 III is expected to, per the spec's documented sampling-bias caveat) is not a bug to fix, it's the finding.
- Link to the spec from `hybrid_engine/EVALUATION.md` as `../docs/superpowers/specs/2026-08-05-sony-body-source-recognition-design.md` (relative from `hybrid_engine/`, per `docs/CLAUDE.md`'s link-resolution rule).

---

### Task 1: `tools/evaluate_sony_body_split.py` — LOO prediction-error computation

**Files:**
- Create: `tools/evaluate_sony_body_split.py`
- Test: `tests/test_evaluate_sony_body_split.py`

**Interfaces:**
- Consumes: nothing from elsewhere in the codebase (standalone script, per `tools/CLAUDE.md`). `sony_stats_result.csv` is read directly.
- Produces: `load_rows(csv_path) -> list[dict]` (each dict has keys `"body"`, `"name"`, `"b2"`, `"w995"`), `loo_errors(rows, stat_key) -> list[dict]` (each dict has keys `"body"`, `"name"`, `"pooled_error"`, `"body_error"`), `summarize(per_fold, n_bootstrap=20000, seed=0) -> dict`, `print_summary(s, label_a="A", label_b="B") -> None`. Task 2's real run and regression test call `load_rows`, `loo_errors`, and `summarize` directly.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_evaluate_sony_body_split.py`:

```python
import csv
import os
import tempfile
import unittest

from tools.evaluate_sony_body_split import load_rows, loo_errors


class TestLoadRows(unittest.TestCase):
    def test_strips_sony_prefix_and_parses_floats(self):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["camera", "filename", "url", "b2", "w995", "med", "sat", "dark_pct"])
                writer.writerow(["Sony A7 III", "img1.jpg", "http://x", "10.7", "185.3", "70.0", "91.8", "20.0"])
            rows = load_rows(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["body"], "A7 III")
            self.assertEqual(rows[0]["name"], "img1.jpg")
            self.assertAlmostEqual(rows[0]["b2"], 10.7)
            self.assertAlmostEqual(rows[0]["w995"], 185.3)
        finally:
            os.remove(path)

    def test_reads_all_rows(self):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["camera", "filename", "url", "b2", "w995", "med", "sat", "dark_pct"])
                writer.writerow(["Sony A7", "a.jpg", "u", "1", "2", "3", "4", "5"])
                writer.writerow(["Sony A7R", "b.jpg", "u", "6", "7", "8", "9", "10"])
            rows = load_rows(path)
            self.assertEqual(len(rows), 2)
            self.assertEqual([r["body"] for r in rows], ["A7", "A7R"])
        finally:
            os.remove(path)


class TestLooErrors(unittest.TestCase):
    def setUp(self):
        # 2 bodies, 3 images each, exact hand-computed expected errors
        self.rows = [
            {"body": "X", "name": "x0", "b2": 10.0},
            {"body": "X", "name": "x1", "b2": 12.0},
            {"body": "X", "name": "x2", "b2": 14.0},
            {"body": "Y", "name": "y0", "b2": 20.0},
            {"body": "Y", "name": "y1", "b2": 22.0},
            {"body": "Y", "name": "y2", "b2": 24.0},
        ]

    def test_returns_one_row_per_input_image(self):
        errors = loo_errors(self.rows, "b2")
        self.assertEqual(len(errors), 6)

    def test_holdout_x0_pooled_and_body_errors(self):
        # held-out x0=10.0: others = [12,14,20,22,24] -> pooled mean 18.4 -> |10-18.4|=8.4
        # same-body(X) others = [12,14] -> body mean 13.0 -> |10-13.0|=3.0
        errors = loo_errors(self.rows, "b2")
        x0 = next(e for e in errors if e["name"] == "x0")
        self.assertAlmostEqual(x0["pooled_error"], 8.4)
        self.assertAlmostEqual(x0["body_error"], 3.0)
        self.assertEqual(x0["body"], "X")

    def test_holdout_y0_pooled_and_body_errors(self):
        # held-out y0=20.0: others = [10,12,14,22,24] -> pooled mean 16.4 -> |20-16.4|=3.6
        # same-body(Y) others = [22,24] -> body mean 23.0 -> |20-23.0|=3.0
        errors = loo_errors(self.rows, "b2")
        y0 = next(e for e in errors if e["name"] == "y0")
        self.assertAlmostEqual(y0["pooled_error"], 3.6)
        self.assertAlmostEqual(y0["body_error"], 3.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_evaluate_sony_body_split -v`
Expected: `ModuleNotFoundError: No module named 'tools.evaluate_sony_body_split'` (or `ImportError`) - the module doesn't exist yet.

- [ ] **Step 3: Write `tools/evaluate_sony_body_split.py`**

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_evaluate_sony_body_split -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/evaluate_sony_body_split.py tests/test_evaluate_sony_body_split.py
git commit -m "Add Sony body-split LOO evaluation script (pooled vs per-body prediction error)"
```

---

### Task 2: Run the real evaluation and record the result

**Files:**
- Modify: `tests/test_evaluate_sony_body_split.py` (append a `TestSummarizeRecordedRun` class)
- Modify: `hybrid_engine/EVALUATION.md` (append a new section at the end)

**Interfaces:**
- Consumes: `tools.evaluate_sony_body_split.load_rows`, `loo_errors`, `summarize` (from Task 1).
- Produces: nothing further consumes this - it's the terminal task of this plan.

- [ ] **Step 1: Run the real evaluation**

`sony_stats_result.csv` is already present in this environment (115 rows, confirmed during spec research - do not re-derive or re-scrape it). This is pure in-memory computation on a small CSV (no image decoding, no RAW, no network) - it should complete in well under a second, no background/`nohup` handling needed.

```bash
python3 -m tools.evaluate_sony_body_split > /tmp/sony_body_split_output.log 2>&1
cat /tmp/sony_body_split_output.log
```

Expected: two `=== ... ===` sections (블랙p2/b2, 화이트p99.5/w995), each with 5 `--- <body> (n=23) ---` subsections showing `print_summary()` output.

- [ ] **Step 2: Add a regression test reproducing the real recorded run**

`main()` already prints a `PER_FOLD_<stat_key>_<body> = [...]` line (Python
list-literal syntax, spaces in body names replaced with `_`) for each of
the 10 body x statistic combinations, right in `/tmp/sony_body_split_output.log`
from Step 1 - `grep "^  PER_FOLD_" /tmp/sony_body_split_output.log` finds
all 10 lines. Copy each one's list literal verbatim into the matching
`_RECORDED_*` constant below - no need to hand-transcribe or re-run
anything.

Append to `tests/test_evaluate_sony_body_split.py` (add `from tools.evaluate_sony_body_split import summarize` to the existing import line):

```python
# 실제 LOO 재실행 기록값(sony_stats_result.csv, 115장) -
# hybrid_engine/EVALUATION.md의 "Sony 바디별 소스 인식 파일럿" 절에
# 실린 것과 정확히 같다. 각각 (name, pooled_error, body_error).
_RECORDED_B2_A7 = [
    # <Step 1 로그에서 뽑은 b2/A7 per_fold 23줄을 여기 옮겨적는다>
]
_RECORDED_B2_A7R = [
    # <b2/A7R 23줄>
]
_RECORDED_B2_A7S = [
    # <b2/A7S 23줄>
]
_RECORDED_B2_A7_III = [
    # <b2/A7 III 23줄>
]
_RECORDED_B2_A7_IV = [
    # <b2/A7 IV 23줄>
]
_RECORDED_W995_A7 = [
    # <w995/A7 23줄>
]
_RECORDED_W995_A7R = [
    # <w995/A7R 23줄>
]
_RECORDED_W995_A7S = [
    # <w995/A7S 23줄>
]
_RECORDED_W995_A7_III = [
    # <w995/A7 III 23줄>
]
_RECORDED_W995_A7_IV = [
    # <w995/A7 IV 23줄>
]


class TestSummarizeRecordedRun(unittest.TestCase):
    """hybrid_engine/EVALUATION.md에 기록된 실제 LOO 결과를 재현하는
    회귀 테스트 - 10개(5바디 x 2통계) 전부, 실행 없이 감사 가능."""

    def test_b2_a7_reproduces_documented_verdict(self):
        s = summarize(_RECORDED_B2_A7)
        self.assertAlmostEqual(s["mean_a"], <실제값>, places=3)
        self.assertAlmostEqual(s["mean_b"], <실제값>, places=3)
        self.assertAlmostEqual(s["sign_test_p"], <실제값>, places=9)

    def test_b2_a7r_reproduces_documented_verdict(self):
        s = summarize(_RECORDED_B2_A7R)
        self.assertAlmostEqual(s["mean_a"], <실제값>, places=3)
        self.assertAlmostEqual(s["mean_b"], <실제값>, places=3)
        self.assertAlmostEqual(s["sign_test_p"], <실제값>, places=9)

    def test_b2_a7s_reproduces_documented_verdict(self):
        s = summarize(_RECORDED_B2_A7S)
        self.assertAlmostEqual(s["mean_a"], <실제값>, places=3)
        self.assertAlmostEqual(s["mean_b"], <실제값>, places=3)
        self.assertAlmostEqual(s["sign_test_p"], <실제값>, places=9)

    def test_b2_a7_iii_reproduces_documented_verdict(self):
        s = summarize(_RECORDED_B2_A7_III)
        self.assertAlmostEqual(s["mean_a"], <실제값>, places=3)
        self.assertAlmostEqual(s["mean_b"], <실제값>, places=3)
        self.assertAlmostEqual(s["sign_test_p"], <실제값>, places=9)

    def test_b2_a7_iv_reproduces_documented_verdict(self):
        s = summarize(_RECORDED_B2_A7_IV)
        self.assertAlmostEqual(s["mean_a"], <실제값>, places=3)
        self.assertAlmostEqual(s["mean_b"], <실제값>, places=3)
        self.assertAlmostEqual(s["sign_test_p"], <실제값>, places=9)

    def test_w995_a7_reproduces_documented_verdict(self):
        s = summarize(_RECORDED_W995_A7)
        self.assertAlmostEqual(s["mean_a"], <실제값>, places=3)
        self.assertAlmostEqual(s["mean_b"], <실제값>, places=3)
        self.assertAlmostEqual(s["sign_test_p"], <실제값>, places=9)

    def test_w995_a7r_reproduces_documented_verdict(self):
        s = summarize(_RECORDED_W995_A7R)
        self.assertAlmostEqual(s["mean_a"], <실제값>, places=3)
        self.assertAlmostEqual(s["mean_b"], <실제값>, places=3)
        self.assertAlmostEqual(s["sign_test_p"], <실제값>, places=9)

    def test_w995_a7s_reproduces_documented_verdict(self):
        s = summarize(_RECORDED_W995_A7S)
        self.assertAlmostEqual(s["mean_a"], <실제값>, places=3)
        self.assertAlmostEqual(s["mean_b"], <실제값>, places=3)
        self.assertAlmostEqual(s["sign_test_p"], <실제값>, places=9)

    def test_w995_a7_iii_reproduces_documented_verdict(self):
        s = summarize(_RECORDED_W995_A7_III)
        self.assertAlmostEqual(s["mean_a"], <실제값>, places=3)
        self.assertAlmostEqual(s["mean_b"], <실제값>, places=3)
        self.assertAlmostEqual(s["sign_test_p"], <실제값>, places=9)

    def test_w995_a7_iv_reproduces_documented_verdict(self):
        s = summarize(_RECORDED_W995_A7_IV)
        self.assertAlmostEqual(s["mean_a"], <실제값>, places=3)
        self.assertAlmostEqual(s["mean_b"], <실제값>, places=3)
        self.assertAlmostEqual(s["sign_test_p"], <실제값>, places=9)
```

Fill in every `<실제값>` with the actual numbers `print_summary()` printed in Step 1's log for that exact body/statistic - read them directly from `/tmp/sony_body_split_output.log`, do not guess or hand-round. This mirrors `tests/test_evaluate_hncs_blend.py`'s `TestSummarizeRecordedRun`.

Run: `python3 -m unittest tests.test_evaluate_sony_body_split -v`
Expected: all tests PASS, including the new 10-test `TestSummarizeRecordedRun` class.

- [ ] **Step 3: Document the result in `hybrid_engine/EVALUATION.md`**

Append a new section at the end of `hybrid_engine/EVALUATION.md`:

```markdown
## Sony 바디별 소스 인식 파일럿

`hybrid_engine.convert`의 소스 시그니처 역산(`remove_camera_signature()`,
`hybrid_engine/core/preset_inverse.py`)이 지금은 브랜드 하나당 pooled
커브 하나만 쓰는데, Sony 5바디(A7/A7R/A7S/A7 III/A7 IV, `brands/sony.py`
population 통계, 바디당 n=23)로 바디별 커브가 더 정확한 예측을 주는지
leave-one-out으로 검증했다. 설계 근거:
[docs/superpowers/specs/2026-08-05-sony-body-source-recognition-design.md](../docs/superpowers/specs/2026-08-05-sony-body-source-recognition-design.md).

115장 전부에 대해 한 장씩 held-out - 브랜드 pooled 예측(나머지 114장
평균)과 바디별 예측(같은 바디 나머지 22장 평균)의 오차(|실제값-예측값|)를
블랙p2(b2)/화이트p99.5(w995) 각각 비교, 바디별로 개별 판정.

<Step 1 로그에서 각 바디 x 통계 조합의 print_summary() 출력을 요약해
표로 삽입: 바디 | 통계 | 평균 pooled 오차 | 평균 바디별 오차 | 개선폭 |
부호검정 p | 부트스트랩 95% CI | 판정>

**A7 III**: <실제 판정 - brands/sony.py docstring이 이미 밝힌 "105mm/
28-200mm 렌즈 테스트 표본 편향" 가설이 이 검증에서 확인됐는지 여부를
명시적으로 적는다>

**채택**: <b2/w995 둘 다 CI가 0을 포함하지 않아 채택된 바디 목록, 없으면
"없음">. 이 파일럿은 측정까지만 하고 `hybrid_engine/core/preset_inverse.py`
로의 실제 배선은 여기서 하지 않는다(설계는
[스펙](../docs/superpowers/specs/2026-08-05-sony-body-source-recognition-design.md)의
"구현 설계" 절에 이미 있음 - 채택 여부를 owner가 검토한 뒤 별도 작업으로
진행).

`brands/sony.py`의 `apply_sony_look()`이나 다른 어떤 shipped `apply_*`도
이 파일럿으로 건드리지 않았다.
```

Fill in the `<...>` placeholders with the real table and verdicts from Step 1's log - do not invent or approximate them. Every number in this section must trace back to `/tmp/sony_body_split_output.log`.

- [ ] **Step 4: Run the full test suite**

Run: `python3 -m unittest discover -s tests`
Expected: all tests PASS (the pre-existing 615 minus the 8 environment-only torch/GUI errors already present before this plan, plus this plan's new tests).

- [ ] **Step 5: Commit the real results**

```bash
git add tests/test_evaluate_sony_body_split.py hybrid_engine/EVALUATION.md
git commit -m "Record Sony body-split source-recognition LOO result (115 images, 5 bodies)"
```
