"""`brands/fuji.py`에 `apply_velvia`가 없는 게 실제로 손해인지 잰다 -
신설할지는 별도 결정이므로 이 스크립트는 아무 함수도 만들지 않는다.

**배경**: `tools/evaluate_fuji_film_mode_separation.py`(2026-09-04)가
같은 장면 묶음에서 Provia와 Velvia의 실제 모드거리를 4.310으로 쟀는데
(그 묶음 바닥 0.336), `tests/test_brands.py`의 `FUJI_COLOR_PRESETS` 13개에
Velvia가 없다. 즉 크기가 측정된 미구현 모드다. 그렇다고 바로 만들 일은
아니고, **기존 룩으로 얼마나 커버되는지**부터 봐야 한다.

**질문**: Velvia로 찍은 JPEG을 타깃으로 놓았을 때
(a) 무보정 neutral 렌더, (b) 가장 가까운 기존 룩인 `apply_provia`,
(c) 참고로 채도가 센 다른 룩들 - 중 무엇이 얼마나 맞나. `apply_provia`가
이미 크게 줄여준다면 전용 함수의 여지가 작고, 별로 못 줄이면 그만큼이
`apply_velvia`가 가져갈 몫이다.

**방법**: `tools/evaluate_fuji_preset_de00.py`와 같은 경로 -
`load_neutral_render(raw, max_dim=400)` → 룩 적용 → 카메라 JPEG을
타깃으로 화소별 ΔE00 평균. Velvia 페어는 같은 프레임의 raw/jpeg이므로
화소가 정렬돼 있어 전역 평균이 아니라 화소별 비교가 가능하다(같은 장면
묶음 분석에서 전역 평균 Lab을 썼던 것과 다른 점).

**통계**: n=8 페어드 표본이라 `summarize()`(부호검정 + 부트스트랩 95% CI
20000회 고정 시드)를 그대로 복사해 붙였다 - 형제 `evaluate_*.py`를
import하지 않는 컨벤션(`tools/CLAUDE.md`). n=8은 작고, 그 자체가 결과의
일부다.

**배포 아님**: `brands/fuji.py`를 수정하지 않는다. 측정만 한다.

  ~/.hncs-hybrid-venv312/bin/python3 -m tools.evaluate_fuji_velvia_gap
"""
import csv
import json
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import colour
import cv2
import numpy as np

from tools.calibrate import load_neutral_render

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_DIR = os.path.join(BASE, "datasets", "fuji", "contributed", "local-work-2026-08")
OUT_REPORT = os.path.join(SET_DIR, "velvia_gap_report.json")
MAX_DIM = 400
TARGET_MODE = "F2/Fujichrome (Velvia)"

# 비교할 기존 룩 - apply_provia가 주 후보고, 나머지는 "채도 센 쪽이면
# 우연히 더 맞지 않나"를 확인하는 대조군이다.
CANDIDATE_LOOKS = ["apply_provia", "apply_astia", "apply_classic_chrome",
                   "apply_reala_ace", "apply_nostalgic_neg"]

# 기준선: 이 룩 계열이 **자기 모드**에서 내는 통상 정확도. Velvia 잔여오차가
# 이보다 크면 전용 함수가 가져갈 몫이 있고, 비슷하면 여지가 작다.
BENCHMARK_MODE = "F0/Standard (Provia)"
BENCHMARK_LOOK = "apply_provia"


def _film_mode(jpg_path):
    out = subprocess.run(["exiftool", "-s3", "-FilmMode", jpg_path],
                         capture_output=True, text=True, timeout=30).stdout
    return out.strip()


def _to_linear(bgr_u8):
    rgb = np.clip(bgr_u8[:, :, ::-1].astype(np.float64) / 255.0, 0.0, 1.0)
    return colour.cctf_decoding(rgb, function="sRGB")


def _mean_delta_e(lin_a, lin_b):
    from skimage.color import deltaE_ciede2000, rgb2lab
    a = colour.cctf_encoding(np.clip(lin_a, 0.0, 1.0), function="sRGB")
    b = colour.cctf_encoding(np.clip(lin_b, 0.0, 1.0), function="sRGB")
    return float(np.mean(deltaE_ciede2000(rgb2lab(a), rgb2lab(b))))


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n))


def summarize(label_a, des_a, label_b, des_b, n_bootstrap=20000, seed=0):
    """페어드 비교 - des_b가 더 작으면 양수 improvement.
    `hybrid_engine/calibrate_profile_leica.py`의 것과 같은 통계, 컨벤션대로 복붙."""
    a, b = np.asarray(des_a, float), np.asarray(des_b, float)
    n = len(a)
    diff = a - b
    mean_a, mean_b = float(a.mean()), float(b.mean())
    imp = (mean_a - mean_b) / mean_a * 100.0 if mean_a else float("nan")
    wins, losses = int((diff > 0).sum()), int((diff < 0).sum())
    rng = np.random.default_rng(seed)
    boot = np.array([diff[rng.integers(0, n, n)].mean() for _ in range(n_bootstrap)])
    ci_lo, ci_hi = (float(v) for v in np.percentile(boot, [2.5, 97.5]))
    p = _sign_test_p(wins, losses)
    inconclusive = ci_lo <= 0.0 <= ci_hi
    print(f"\n=== {label_a} vs {label_b} (n={n}) ===")
    print(f"평균 {label_a} ΔE00={mean_a:.4f}  평균 {label_b} ΔE00={mean_b:.4f}  "
          f"개선폭={imp:+.2f}%")
    print(f"승/패={wins}/{losses}  부호검정 p={p:.4f}  "
          f"부트스트랩 95% CI=[{ci_lo:+.4f}, {ci_hi:+.4f}]")
    print("판정: " + ("보류 (CI가 0 포함)" if inconclusive
                     else (f"{label_b} 우세" if imp > 0 else f"{label_a} 우세")))
    return dict(mean_a=mean_a, mean_b=mean_b, improvement_pct=imp,
                wins=wins, losses=losses, p_value=p,
                ci_lo=ci_lo, ci_hi=ci_hi, inconclusive=bool(inconclusive))


def main():
    import importlib
    fuji = importlib.import_module("brands.fuji")

    rows = []
    with open(os.path.join(SET_DIR, "manifest.csv"), encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    pairs = []
    for r in rows:
        jpg = os.path.join(SET_DIR, "jpeg", r["filename_jpeg"])
        raw = os.path.join(SET_DIR, "raw", r["filename_raw"])
        if not (os.path.exists(jpg) and os.path.exists(raw)):
            continue
        if _film_mode(jpg) != TARGET_MODE:
            continue
        pairs.append((r["filename_raw"], raw, jpg))
    print(f"Velvia 페어 {len(pairs)}개")
    if len(pairs) < 3:
        raise SystemExit("표본 부족")

    per_look = {name: [] for name in CANDIDATE_LOOKS}
    neutral_de = []
    names = []
    for name, raw, jpg in pairs:
        neutral = load_neutral_render(raw, max_dim=MAX_DIM)
        target = cv2.imread(jpg)
        target = cv2.resize(target, (neutral.shape[1], neutral.shape[0]),
                            interpolation=cv2.INTER_AREA)
        t_lin = _to_linear(target)
        neutral_de.append(_mean_delta_e(_to_linear(neutral), t_lin))
        for look in CANDIDATE_LOOKS:
            out = getattr(fuji, look)(neutral.copy())
            if out.ndim == 2:
                out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
            per_look[look].append(_mean_delta_e(_to_linear(out), t_lin))
        names.append(name)
        print(f"  {name}: 무보정 {neutral_de[-1]:.3f}  "
              + "  ".join(f"{lk[len('apply_'):]} {per_look[lk][-1]:.3f}"
                          for lk in CANDIDATE_LOOKS), flush=True)

    stats = {}
    for look in CANDIDATE_LOOKS:
        stats[look] = summarize("무보정", neutral_de, look, per_look[look])

    best = min(CANDIDATE_LOOKS, key=lambda lk: float(np.mean(per_look[lk])))
    best_mean = float(np.mean(per_look[best]))
    print(f"\n가장 가까운 기존 룩: {best} "
          f"(평균 ΔE00 {best_mean:.4f}, 무보정 {float(np.mean(neutral_de)):.4f})")

    # 기준선: 위 잔여오차가 큰지 작은지는 우리 룩들이 **자기 모드**에서 내는
    # 값과 비교해야 안다. 같은 세트의 Provia 페어에 apply_provia를 돌린다 -
    # 이게 이 룩 계열의 통상 정확도이고, apply_velvia를 새로 만들어도
    # 넘기 어려운 수준이다.
    bench_pairs = []
    for r in rows:
        jpg = os.path.join(SET_DIR, "jpeg", r["filename_jpeg"])
        raw = os.path.join(SET_DIR, "raw", r["filename_raw"])
        if os.path.exists(jpg) and os.path.exists(raw) \
                and _film_mode(jpg) == BENCHMARK_MODE:
            bench_pairs.append((r["filename_raw"], raw, jpg))
    bench_de = []
    for name, raw, jpg in bench_pairs:
        neutral = load_neutral_render(raw, max_dim=MAX_DIM)
        target = cv2.imread(jpg)
        target = cv2.resize(target, (neutral.shape[1], neutral.shape[0]),
                            interpolation=cv2.INTER_AREA)
        out = getattr(fuji, BENCHMARK_LOOK)(neutral.copy())
        bench_de.append(_mean_delta_e(_to_linear(out), _to_linear(target)))
    bench_mean = float(np.mean(bench_de)) if bench_de else float("nan")
    print(f"기준선: {BENCHMARK_LOOK}를 자기 모드({BENCHMARK_MODE}) "
          f"{len(bench_pairs)}쌍에 적용 → 평균 ΔE00 {bench_mean:.4f}")
    print(f"→ Velvia 잔여 {best_mean:.4f} vs 자기모드 기준선 {bench_mean:.4f}: "
          f"{'기준선보다 나쁨 - 전용 함수 여지 있음' if best_mean > bench_mean else '기준선 수준 - 전용 함수 여지 작음'}")

    report = {
        "question": "brands/fuji.py에 apply_velvia가 없는 게 실제로 손해인가 - "
                    "기존 룩으로 Velvia JPEG이 얼마나 커버되나",
        "context": "tools/evaluate_fuji_film_mode_separation.py가 같은 장면 묶음에서 "
                   "Provia vs Velvia 실제 모드거리를 4.310으로 쟀다(그 묶음 바닥 0.336)",
        "target_film_mode": TARGET_MODE,
        "set": "datasets/fuji/contributed/local-work-2026-08",
        "n_pairs": len(pairs),
        "images": names,
        "method": "load_neutral_render(raw, max_dim=400) -> 룩 적용 -> 카메라 JPEG "
                  "타깃으로 화소별 ΔE00 평균. 같은 프레임이라 화소 정렬됨",
        "no_correction_de00_per_image": neutral_de,
        "look_de00_per_image": per_look,
        "paired_stats_vs_no_correction": stats,
        "closest_existing_look": best,
        "closest_existing_look_de00": best_mean,
        "benchmark": {
            "meaning": "이 룩 계열이 자기 모드에서 내는 통상 정확도 - Velvia "
                       "잔여오차가 이보다 크면 전용 함수가 가져갈 몫이 있다",
            "look": BENCHMARK_LOOK, "mode": BENCHMARK_MODE,
            "n_pairs": len(bench_pairs), "de00_mean": bench_mean,
            "de00_per_image": bench_de,
        },
        "deployment": "배포 아님 - brands/fuji.py를 수정하지 않는다. apply_velvia "
                      "신설 여부는 별도 결정",
    }
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n리포트: {OUT_REPORT}")


if __name__ == "__main__":
    main()
