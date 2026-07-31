"""rawpy postprocess()의 chromatic_aberration=(red_scale, blue_scale)
파라미터가 핫셀블라드 13쌍(raw+jpeg)의 ΔE(CIEDE2000)를 줄이는지
leave-one-out 교차검증으로 확인한다. 설계 근거:
docs/superpowers/specs/2026-07-31-chromatic-aberration-correction-design.md

  python3 -m tools.evaluate_chromatic_aberration

이번 세션에서 처음으로 "디코드 단계"(그 이전 20여 회의 모든 실험은
디코드 이후 그레이월드/톤커브/LUT/공간연산만 조정)를 건드리는 실험이다.

**측정된 성능 특성** (설계 문서에 근거 기록): chromatic_aberration이
지정된 decode_raw() 호출은 같은 RAW 파일을 처음 열 때(OS 페이지캐시
미스) ~19.6초, 같은 파일을 다시 열 때(캐시 히트) ~2~4.6초 걸린다.
(1.0, 1.0)은 인자를 아예 안 넘긴 것과 바이트 단위로 동일한 결과를
낸다(실측 확인) - 그래서 베이스라인도 그리드의 (1.0, 1.0) 지점 재사용.
디코드+축소본을 (pair명, red_scale, blue_scale)로 캐시해서 13개 LOO
폴드 전체에서 같은 조합을 한 번만 디코드한다 - 총 13쌍 x 81격자점 =
1053회 디코드, 실측 총 실행시간 ~60~70분. 반드시 백그라운드로 돌릴 것.
"""
import csv
import glob
import itertools
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from hybrid_engine.utils.evaluate import mean_delta_e
from hybrid_engine.utils.io import decode_raw, load_image_linear

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_ROOT, "raw_calib_cache")
CSV_PATH = os.path.join(_ROOT, "datasets", "hasselblad", "hasselblad_raw_jpeg_pairs.csv")

RED_GRID = [0.98, 0.985, 0.99, 0.995, 1.0, 1.005, 1.01, 1.015, 1.02]
BLUE_GRID = [0.98, 0.985, 0.99, 0.995, 1.0, 1.005, 1.01, 1.015, 1.02]

DOWNSAMPLE_MAX_DIM = 512

_DECODE_CACHE = {}
_TARGET_CACHE = {}


def _resize_max_dim(img, max_dim):
    """긴 변이 max_dim을 넘으면 종횡비 유지한 채 축소. 이미 작으면
    그대로 반환(no-op)."""
    h, w = img.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    if scale >= 1.0:
        return img
    new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = cv2.resize(img.astype(np.float32), (new_w, new_h),
                          interpolation=cv2.INTER_AREA)
    return resized.astype(np.float64)


def load_pairs(csv_path=CSV_PATH, cache_dir=CACHE_DIR):
    """CSV의 jpeg_url basename 13개를 읽어 raw/target 경로와 함께
    dict 리스트로 반환."""
    pairs = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            name = os.path.basename(row["jpeg_url"])
            matches = [m for m in glob.glob(os.path.join(cache_dir, name + ".*"))
                       if not m.endswith(".target.jpg")]
            if len(matches) != 1:
                raise FileNotFoundError(f"raw for {name}: expected 1 match, got {matches}")
            pairs.append({
                "name": name,
                "raw_path": matches[0],
                "target_path": os.path.join(cache_dir, name + ".target.jpg"),
            })
    return pairs


def _decoded_and_target(pair, red_scale, blue_scale):
    """(디코드+축소본, 축소된 타깃) - (name, red_scale, blue_scale)로
    캐시해서 LOO 폴드 간 같은 조합의 RAW 재디코드를 막는다."""
    key = (pair["name"], red_scale, blue_scale)
    if key not in _DECODE_CACHE:
        decoded = decode_raw(pair["raw_path"],
                              chromatic_aberration=(red_scale, blue_scale))
        _DECODE_CACHE[key] = _resize_max_dim(decoded, DOWNSAMPLE_MAX_DIM)
    decoded = _DECODE_CACHE[key]
    name = pair["name"]
    if name not in _TARGET_CACHE:
        _TARGET_CACHE[name] = load_image_linear(pair["target_path"],
                                                  resize_to=decoded.shape[:2])
    return decoded, _TARGET_CACHE[name]


def delta_e_for(pair, red_scale, blue_scale):
    decoded, target = _decoded_and_target(pair, red_scale, blue_scale)
    return mean_delta_e(decoded, target)


def grid_search(train_pairs):
    """train_pairs 평균 ΔE(CIEDE2000)가 최소인 (red_scale, blue_scale)
    반환 - 9x9=81 전 조합 탐색."""
    best_params, best_de = (1.0, 1.0), float("inf")
    for red_scale, blue_scale in itertools.product(RED_GRID, BLUE_GRID):
        des = [delta_e_for(p, red_scale, blue_scale) for p in train_pairs]
        mean_de = float(np.mean(des))
        if mean_de < best_de:
            best_de, best_params = mean_de, (red_scale, blue_scale)
    return best_params


def run_loocv():
    pairs = load_pairs()
    per_fold = []
    for i, held_out in enumerate(pairs):
        train = pairs[:i] + pairs[i + 1:]
        best_red, best_blue = grid_search(train)
        de_baseline = delta_e_for(held_out, 1.0, 1.0)
        de_corrected = delta_e_for(held_out, best_red, best_blue)
        per_fold.append((held_out["name"], de_baseline, de_corrected,
                          best_red, best_blue))
        print(f"  [{held_out['name']}] baseline ΔE={de_baseline:.3f} "
              f"corrected ΔE={de_corrected:.3f} "
              f"params=({best_red}, {best_blue})", flush=True)
    return per_fold


def _sign_test_p(wins, losses):
    """부호검정 양측 p값(정확 이항, 무승부 제외). scipy 의존 없이
    math.comb으로 직접 계산한다."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def summarize(per_fold, n_bootstrap=20000, seed=0):
    """폴드별 (name, de_baseline, de_corrected, red_scale, blue_scale)
    리스트 -> 요약 통계 dict. 평균 차이 하나로 승패를 선언하지 않는다 -
    부호검정, 부트스트랩 신뢰구간, drop-one 민감도를 같이 내고 0을
    포함하면 '판정 보류'로 보고한다. 순수 함수라 기록된 폴드 결과만
    으로도 재현할 수 있다(tests/test_evaluate_chromatic_aberration.py)."""
    baseline = np.array([row[1] for row in per_fold], dtype=np.float64)
    corrected = np.array([row[2] for row in per_fold], dtype=np.float64)
    n = len(per_fold)
    diff = baseline - corrected  # 양수 = 보정이 그 폴드에서 더 좋음(ΔE 감소)
    mean_baseline = float(baseline.mean())
    mean_corrected = float(corrected.mean())
    improvement_pct = (mean_baseline - mean_corrected) / mean_baseline * 100.0

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
        boot_pct.append(float((baseline[idx].mean() - corrected[idx].mean())
                              / baseline[idx].mean() * 100.0))
    ci_diff = tuple(float(v) for v in np.percentile(boot_diff, [2.5, 97.5]))
    ci_pct = tuple(float(v) for v in np.percentile(boot_pct, [2.5, 97.5]))

    dropone = []
    for i in range(n):
        keep = np.ones(n, dtype=bool)
        keep[i] = False
        dropone.append(float((baseline[keep].mean() - corrected[keep].mean())
                             / baseline[keep].mean() * 100.0))

    inconclusive = ci_diff[0] <= 0.0 <= ci_diff[1]
    if inconclusive:
        verdict = ("판정 보류 - 평균 차이가 0과 구분되지 않는다"
                   "(95% 부트스트랩 CI가 0을 포함)")
    elif improvement_pct > 0:
        verdict = "색수차 보정이 이겼다"
    else:
        verdict = "보정 없음(기존 decode_raw())이 더 낫다"

    return {
        "n": n,
        "mean_baseline": mean_baseline,
        "mean_corrected": mean_corrected,
        "mean_diff": float(diff.mean()),
        "median_diff": float(np.median(diff)),
        "improvement_pct": improvement_pct,
        "corrected_wins": wins,
        "baseline_wins": losses,
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


def print_summary(s):
    print()
    print(f"평균 baseline ΔE (CIEDE2000, n={s['n']}): {s['mean_baseline']:.3f}")
    print(f"평균 corrected ΔE (CIEDE2000, n={s['n']}): {s['mean_corrected']:.3f}")
    print(f"개선폭: {s['improvement_pct']:.1f}%")
    print(f"폴드 승패: 보정 {s['corrected_wins']}승 {s['baseline_wins']}패")
    print(f"페어드 차이: 평균 {s['mean_diff']:+.3f} / 중앙값 "
          f"{s['median_diff']:+.3f} / 표준편차 {s['sd_diff']:.3f} "
          f"(t={s['t_stat']:.2f}, df={s['n'] - 1})")
    print(f"부호검정 양측 p = {s['sign_test_p']:.3f}")
    print(f"부트스트랩 95% CI - 평균 ΔE 차이: "
          f"[{s['ci_diff'][0]:+.3f}, {s['ci_diff'][1]:+.3f}] / "
          f"개선폭: [{s['ci_pct'][0]:+.1f}%, {s['ci_pct'][1]:+.1f}%]")
    print(f"drop-one 민감도: 한 쌍을 빼면 개선폭이 "
          f"{s['dropone_pct_min']:.1f}% ~ {s['dropone_pct_max']:.1f}% 사이로 움직인다"
          + (" (부호가 뒤집힌다)" if s["dropone_flips_sign"] else ""))
    print(f"판정: {s['verdict']}")


def main():
    per_fold = run_loocv()
    print_summary(summarize(per_fold))


if __name__ == "__main__":
    main()
