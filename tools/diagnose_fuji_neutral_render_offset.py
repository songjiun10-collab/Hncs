"""`load_neutral_render()` 출력과 카메라 JPEG 사이에 **룩과 무관한 전역
노출/톤 격차**가 있는지 진단한다.

**왜 만들었나**: `tools/recalibrate_fuji_classic_negative.py`로
`apply_classic_negative`를 재보정하던 중(2026-09-04, 사용자 승인), 좌표하강이
네 파라미터를 **전부 격자 경계까지** 밀어붙였다 - `sat_mult` 0.65→0.45(하한),
`contrast_n` 1.4→1.0(하한), `black_lift` 0.03→0.12(상한),
`white_point` 1.05→1.18(상한). ΔE00은 14.53에서 8.70까지 떨어졌지만, 방향이
"밝기 크게 올리고 · S커브 제거 · 채도 절반"이라 필름 시뮬레이션 특성을
다듬는 게 아니라 입력/타깃의 전역 격차를 룩 상수로 흡수하는 모양이었다.

**가설**: `load_neutral_render()`(libraw 기본 렌더)가 카메라 JPEG보다
어둡고/채도가 높아서, 어떤 룩을 얹든 그 격차가 먼저 잡히고 룩 파라미터가
그 보정에 소모된다.

**방법**: 룩을 전혀 적용하지 않은 neutral 렌더와 카메라 JPEG의 전역
통계(Lab L 평균/중앙값, HSV S 평균, 밝기 p2/p99.5)를 페어별로 비교한다.
계통 편향이면 47쌍 대부분에서 같은 부호로 나온다 - 부호 일관성과
부트스트랩 95% CI로 확인한다.

이 진단이 맞으면 재보정으로 상수만 바꾸는 건 잘못된 처방이다(룩이 노출
보정기가 된다). 대상 모드를 인자로 받아 다른 필름모드에도 돌릴 수 있다.

  ~/.hncs-hybrid-venv312/bin/python3 -m tools.diagnose_fuji_neutral_render_offset ["Classic Negative"]
"""
import csv
import json
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from tools.calibrate import load_neutral_render

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_DIR = os.path.join(BASE, "datasets", "fuji", "contributed", "local-work-2026-08")
MAX_DIM = 300


def _film_mode(jpg_path):
    return subprocess.run(["exiftool", "-s3", "-FilmMode", jpg_path],
                          capture_output=True, text=True, timeout=30).stdout.strip()


def _stats(bgr_u8):
    lab = cv2.cvtColor(bgr_u8, cv2.COLOR_BGR2LAB)
    hsv = cv2.cvtColor(bgr_u8, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(bgr_u8, cv2.COLOR_BGR2GRAY).astype(np.float64)
    return dict(
        lab_L_mean=float(lab[:, :, 0].mean()),
        lab_L_median=float(np.median(lab[:, :, 0])),
        hsv_S_mean=float(hsv[:, :, 1].mean()),
        black_p2=float(np.percentile(gray, 2)),
        white_p995=float(np.percentile(gray, 99.5)),
    )


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n))


def _paired(name, diffs, n_bootstrap=20000, seed=0):
    d = np.asarray(diffs, float)
    n = len(d)
    rng = np.random.default_rng(seed)
    boot = np.array([d[rng.integers(0, n, n)].mean() for _ in range(n_bootstrap)])
    lo, hi = (float(v) for v in np.percentile(boot, [2.5, 97.5]))
    pos, neg = int((d > 0).sum()), int((d < 0).sum())
    p = _sign_test_p(pos, neg)
    incon = lo <= 0.0 <= hi
    print(f"  {name:16s} 평균차(JPEG - neutral) {d.mean():+8.3f}  "
          f"양수/음수 {pos:2d}/{neg:2d}  p={p:.4f}  CI=[{lo:+.3f},{hi:+.3f}]"
          f"{'  판정 보류' if incon else ''}")
    return dict(mean_diff=float(d.mean()), n=n, positive=pos, negative=neg,
                p_value=p, ci_lo=lo, ci_hi=hi, inconclusive=bool(incon))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "Classic Negative"
    out_report = os.path.join(
        SET_DIR, f"neutral_render_offset_{mode.replace(' ', '_').lower()}.json")

    rows = list(csv.DictReader(open(os.path.join(SET_DIR, "manifest.csv"),
                                    encoding="utf-8-sig")))
    keys = ["lab_L_mean", "lab_L_median", "hsv_S_mean", "black_p2", "white_p995"]
    diffs = {k: [] for k in keys}
    names = []
    for r in rows:
        jpg = os.path.join(SET_DIR, "jpeg", r["filename_jpeg"])
        raw = os.path.join(SET_DIR, "raw", r["filename_raw"])
        if not (os.path.exists(jpg) and os.path.exists(raw)):
            continue
        if _film_mode(jpg) != mode:
            continue
        neutral = load_neutral_render(raw, max_dim=MAX_DIM)
        target = cv2.imread(jpg)
        target = cv2.resize(target, (neutral.shape[1], neutral.shape[0]),
                            interpolation=cv2.INTER_AREA)
        ns, ts = _stats(neutral), _stats(target)
        for k in keys:
            diffs[k].append(ts[k] - ns[k])
        names.append(r["filename_raw"])
        if len(names) % 10 == 0:
            print(f"  {len(names)}개 처리", flush=True)

    print(f"\n[{mode}] {len(names)}쌍 - 카메라 JPEG 에서 neutral 렌더를 뺀 차이\n")
    stats = {k: _paired(k, diffs[k]) for k in keys}

    systematic = [k for k in keys if not stats[k]["inconclusive"]]
    print(f"\n계통 편향으로 확인된 지표: {systematic or '없음'}")
    report = {
        "purpose": "load_neutral_render() 출력과 카메라 JPEG 사이의 룩과 무관한 "
                   "전역 노출/톤 격차 진단",
        "trigger": "tools/recalibrate_fuji_classic_negative.py 실행 중 좌표하강이 "
                   "4개 파라미터를 전부 격자 경계로 밀어붙인 것(sat_mult 0.45 하한, "
                   "contrast_n 1.0 하한, black_lift 0.12 상한, white_point 1.18 상한)",
        "film_mode": mode,
        "set": "datasets/fuji/contributed/local-work-2026-08",
        "n_pairs": len(names),
        "images": names,
        "metric": "카메라 JPEG 통계 - neutral 렌더 통계 (페어별), 부호검정 + "
                  "부트스트랩 95% CI 20000회 고정 시드",
        "stats": stats,
        "systematic_offsets": systematic,
    }
    with open(out_report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"리포트: {out_report}")


if __name__ == "__main__":
    main()
