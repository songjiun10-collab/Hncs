"""`brands/fuji.py`의 `apply_classic_negative` 상수를 페어 정정 후의
`local-work-2026-08` 47쌍으로 재보정한다.

**왜**: `tools/evaluate_fuji_pairing_fix_impact.py`(2026-09-04)가 이 룩의
검증 데이터 47쌍 중 4쌍(8.5%)이 raw↔jpeg 오매칭으로 오염돼 있었고 모드
평균이 1.0532만큼 부풀려져 있었음을 확인했다. 사용자 승인(2026-09-04
"classic negative 재보정 ㄱㄱ")으로 진행한다.

**현행 상수의 출처가 다르다는 점(중요)**: 지금 값
(`sat_mult=0.65, contrast_n=1.4, black_lift=0.03, white_point=1.05`)은
imaging-resource X100V/X-T5/X-T4 28장의 **통계 매칭**(블랙p2/화이트p99.5/
채도 타깃, RMSE=5.7)으로 나온 것이지 raw+jpeg 페어의 ΔE00으로 피팅된 게
아니다. 이 스크립트가 쓰는 47쌍은 **전부 GFX50S II**이므로, 교체하면 이
룩은 GFX50S II 특화가 된다 - `apply_provia`가 GFX100RF 89쌍으로 셀프튜닝된
것과 같은 패턴이지만(전례 있음), 다른 바디에서 나빠질 수 있다는 뜻이다.
이 트레이드오프는 리포트와 `hybrid_engine/EVALUATION.md`에 남긴다.

**성공 기준(결과 보기 전에 확정, 2026-09-04)**: 5-fold 교차검증에서
이미지별 ΔE00을 현행 상수와 페어드로 비교해
**부트스트랩 95% CI(20000회, 고정 시드)가 0을 배제**하고 신규가 우세할
때만 교체를 권고한다. CI가 0을 포함하면 개선폭이 아무리 좋아 보여도
"판정 보류, 현행 유지"다(`hybrid_engine/CLAUDE.md`).

**양성 대조**: 탐색이 실제로 ΔE00을 움직이는지 먼저 확인한다(in-sample이
현행보다 나아지지 않으면 노브가 죽은 것이므로 결론을 낼 수 없다).

**이 스크립트는 `brands/fuji.py`를 수정하지 않는다.** 권고와 수치만 낸다 -
교체는 별도 커밋에서 사람이 확인하고 한다.

  ~/.hncs-hybrid-venv312/bin/python3 -m tools.recalibrate_fuji_classic_negative
"""
import csv
import json
import math
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import colour
import cv2
import numpy as np

from brands.fuji import apply_classic_negative
from tools.calibrate import load_neutral_render

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_DIR = os.path.join(BASE, "datasets", "fuji", "contributed", "local-work-2026-08")
OUT_REPORT = os.path.join(SET_DIR, "classic_negative_recalibration_report.json")

TARGET_MODE = "Classic Negative"
FIT_MAX_DIM = 300     # 탐색용 - 평가 반복이 많아 400보다 줄인다
VERIFY_MAX_DIM = 400  # 최종 확인용, tools/evaluate_fuji_preset_de00.py와 같은 값
N_FOLDS = 5
SEED = 0

CURRENT = dict(sat_mult=0.65, contrast_n=1.4, black_lift=0.03, white_point=1.05)
GRID = {
    "sat_mult": np.round(np.arange(0.45, 1.001, 0.05), 3),
    "contrast_n": np.round(np.arange(1.0, 2.21, 0.1), 3),
    "black_lift": np.round(np.arange(0.0, 0.121, 0.015), 3),
    "white_point": np.round(np.arange(0.90, 1.181, 0.02), 3),
}
N_PASSES = 3


def _film_mode(jpg_path):
    return subprocess.run(["exiftool", "-s3", "-FilmMode", jpg_path],
                          capture_output=True, text=True, timeout=30).stdout.strip()


def _to_lab(bgr_u8):
    rgb = np.clip(bgr_u8[:, :, ::-1].astype(np.float64) / 255.0, 0.0, 1.0)
    from skimage.color import rgb2lab
    return rgb2lab(rgb)


def _mean_de00(lab_a, lab_b):
    from skimage.color import deltaE_ciede2000
    return float(np.mean(deltaE_ciede2000(lab_a, lab_b)))


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
    print("판정: " + ("보류 (CI가 0 포함) - 현행 유지" if inconclusive
                     else (f"{label_b} 우세" if imp > 0 else f"{label_a} 우세")))
    return dict(mean_a=mean_a, mean_b=mean_b, improvement_pct=imp, n=n,
                wins=wins, losses=losses, p_value=p,
                ci_lo=ci_lo, ci_hi=ci_hi, inconclusive=bool(inconclusive))


def load_pairs(max_dim):
    rows = list(csv.DictReader(open(os.path.join(SET_DIR, "manifest.csv"),
                                    encoding="utf-8-sig")))
    out = []
    t0 = time.time()
    for r in rows:
        jpg = os.path.join(SET_DIR, "jpeg", r["filename_jpeg"])
        raw = os.path.join(SET_DIR, "raw", r["filename_raw"])
        if not (os.path.exists(jpg) and os.path.exists(raw)):
            continue
        if _film_mode(jpg) != TARGET_MODE:
            continue
        neutral = load_neutral_render(raw, max_dim=max_dim)
        target = cv2.imread(jpg)
        target = cv2.resize(target, (neutral.shape[1], neutral.shape[0]),
                            interpolation=cv2.INTER_AREA)
        out.append(dict(name=r["filename_raw"], neutral=neutral,
                        target_lab=_to_lab(target)))
        if len(out) % 10 == 0:
            print(f"  로드 {len(out)}개 ({time.time() - t0:.0f}s)", flush=True)
    return out


def de_for(pairs, params):
    return [_mean_de00(_to_lab(apply_classic_negative(p["neutral"].copy(), **params)),
                       p["target_lab"]) for p in pairs]


def coordinate_search(train, start):
    """좌표하강 - 파라미터 하나씩 격자를 훑어 학습 폴드 평균 ΔE00을 최소화."""
    params = dict(start)
    best = float(np.mean(de_for(train, params)))
    for _ in range(N_PASSES):
        improved = False
        for key, values in GRID.items():
            cur = params[key]
            for v in values:
                if float(v) == float(params[key]):
                    continue
                trial = dict(params, **{key: float(v)})
                score = float(np.mean(de_for(train, trial)))
                if score < best - 1e-6:
                    best, params, improved = score, trial, True
            if params[key] != cur:
                print(f"    {key}: {cur} -> {params[key]}  (ΔE00={best:.4f})",
                      flush=True)
        if not improved:
            break
    return params, best


def main():
    print(f"페어 로드 중 (max_dim={FIT_MAX_DIM})...", flush=True)
    pairs = load_pairs(FIT_MAX_DIM)
    n = len(pairs)
    print(f"Classic Negative 페어 {n}개\n")
    if n < 10:
        raise SystemExit("표본 부족")

    # 양성 대조: 전체로 한 번 피팅해서 in-sample이 실제로 내려가는지 확인.
    print("[양성 대조] 전체 표본 in-sample 탐색", flush=True)
    cur_in = float(np.mean(de_for(pairs, CURRENT)))
    full_params, full_in = coordinate_search(pairs, CURRENT)
    print(f"  현행 in-sample {cur_in:.4f} -> 탐색 후 {full_in:.4f}")
    if full_in >= cur_in - 1e-6:
        print("  ※ 탐색이 ΔE00을 전혀 못 낮춤 - 노브가 죽었거나 현행이 이미 최적."
              " 결론 낼 수 없으므로 중단한다.")
        raise SystemExit(1)

    # 5-fold CV - 폴드마다 학습 폴드로만 다시 탐색한다(데이터 누수 방지).
    rng = np.random.default_rng(SEED)
    folds = np.array_split(rng.permutation(n), N_FOLDS)
    cv_current = np.zeros(n)
    cv_new = np.zeros(n)
    fold_params = []
    for fi, test_idx in enumerate(folds):
        test_set = set(test_idx.tolist())
        train = [p for i, p in enumerate(pairs) if i not in test_set]
        print(f"\n[fold {fi + 1}/{N_FOLDS}] 학습 {len(train)}개", flush=True)
        params, _ = coordinate_search(train, CURRENT)
        fold_params.append(params)
        held = [pairs[i] for i in test_idx]
        for i, d in zip(test_idx, de_for(held, CURRENT)):
            cv_current[i] = d
        for i, d in zip(test_idx, de_for(held, params)):
            cv_new[i] = d
        print(f"  홀드아웃 현행 {np.mean([cv_current[i] for i in test_idx]):.4f} "
              f"-> 신규 {np.mean([cv_new[i] for i in test_idx]):.4f}")

    stats = summarize("현행 상수", cv_current, "재보정 상수", cv_new)
    passes = (not stats["inconclusive"]) and stats["improvement_pct"] > 0

    print(f"\n전체 표본 최종 상수: {full_params}")
    print(f"성공 기준(CI가 0 배제 + 신규 우세) 충족: {'예' if passes else '아니오'}")
    print("권고: " + ("상수 교체" if passes else "현행 유지"))

    report = {
        "purpose": "apply_classic_negative 재보정 - 페어 정정 후 47쌍 기준",
        "user_approval": "2026-09-04 'classic negative 재보정 ㄱㄱ'",
        "success_criterion_fixed_before_results":
            "5-fold CV 페어드 ΔE00에서 부트스트랩 95% CI(20000회, 고정 시드)가 "
            "0을 배제하고 신규가 우세할 때만 교체 권고. CI가 0을 포함하면 현행 유지",
        "caveat_body_monoculture":
            "47쌍 전부 GFX50S II. 현행 상수는 imaging-resource X100V/X-T5/X-T4 "
            "28장의 통계 매칭(RMSE=5.7)에서 나온 값이라 출처가 다르다. 교체하면 "
            "이 룩은 GFX50S II 특화가 되며 다른 바디에서 나빠질 수 있다",
        "set": "datasets/fuji/contributed/local-work-2026-08",
        "n_pairs": n,
        "fit_max_dim": FIT_MAX_DIM,
        "current_params": CURRENT,
        "positive_control": {"in_sample_current": cur_in,
                             "in_sample_after_search": full_in},
        "cv_folds": N_FOLDS,
        "fold_params": fold_params,
        "cv_de00_current_per_image": cv_current.tolist(),
        "cv_de00_new_per_image": cv_new.tolist(),
        "images": [p["name"] for p in pairs],
        "paired_stats": stats,
        "final_params_full_sample": full_params,
        "criterion_passed": bool(passes),
        "recommendation": "상수 교체" if passes else "현행 유지",
        "deployment_note": "이 스크립트는 brands/fuji.py를 수정하지 않는다",
    }
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n리포트: {OUT_REPORT}")


if __name__ == "__main__":
    main()
