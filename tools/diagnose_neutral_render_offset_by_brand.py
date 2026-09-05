"""`load_neutral_render()`의 노출/채도 계통 편향이 **후지만의 문제인지 전
브랜드 공통인지** 확인한다.

**왜 만들었나**: `tools/diagnose_fuji_neutral_render_offset.py`가 후지
GFX50S II Classic Negative 47쌍에서 카메라 JPEG 대비 neutral 렌더가 크게
어둡고(Lab L 중앙값 +74.851, 47/47) 과채도(HSV S -19.490, 0/47)라는 계통
편향을 확인했다. 원인은 `tools/calibrate.py:130`의 `no_auto_bright=True`다.

이게 후지 특유의 것이면 Classic Negative 재적합만의 문제지만, **모든
브랜드에 공통이면 이 저장소의 모든 population fit ΔE00 수치가 같은 왜곡된
기준선 위에 있다**는 뜻이라 파급이 훨씬 크다. 그래서 raw가 실제로 디스크에
남아 있는 다른 브랜드 세트에서 같은 다섯 지표를 잰다.

`brands/`나 `tools/calibrate.py`는 읽기만 한다 - 아무것도 수정하지 않는다.
판정은 브랜드별로 부호검정 + 부트스트랩 95% CI(20000회, 고정 시드)로 하고,
CI가 0을 포함하면 그 지표는 판정 보류로 적는다.

  ~/.hncs-hybrid-venv312/bin/python3 -m tools.diagnose_neutral_render_offset_by_brand
"""
import csv
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from tools.calibrate import load_neutral_render

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_DIM = 300
KEYS = ["lab_L_mean", "lab_L_median", "hsv_S_mean", "black_p2", "white_p995"]

# raw/가 실제로 디스크에 남아 있는 세트만 (raw/는 git-ignore 대상이라
# 클론마다 다르다 - 없으면 그 세트는 건너뛰고 그렇게 보고한다).
SETS = [
    ("hasselblad", "datasets/hasselblad/contributed/x1d-x2d100c-restore-2026-08"),
    ("hasselblad-xcd", "datasets/hasselblad/contributed/xcd-lenses-2026-08"),
    ("sony", "datasets/sony/contributed/dpreview-a7v-preprod-2026-08"),
    ("leica", "datasets/leica/contributed/dpreview-sl3p-2026-08"),
]
# 비교 기준 - 후지에서 이미 잰 값 (tools/diagnose_fuji_neutral_render_offset.py)
FUJI_REFERENCE = {"lab_L_mean": 50.476, "lab_L_median": 74.851,
                  "hsv_S_mean": -19.490, "black_p2": 7.106, "white_p995": 33.000}


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
    print(f"    {name:16s} {d.mean():+8.3f}  양수/음수 {pos:3d}/{neg:3d}  "
          f"p={p:.4f}  CI=[{lo:+.3f},{hi:+.3f}]"
          f"{'  판정 보류' if incon else ''}")
    return dict(mean_diff=float(d.mean()), n=n, positive=pos, negative=neg,
                p_value=p, ci_lo=lo, ci_hi=hi, inconclusive=bool(incon))


def run_set(label, rel_dir):
    set_dir = os.path.join(BASE, rel_dir)
    man = os.path.join(set_dir, "manifest.csv")
    if not os.path.exists(man):
        print(f"  [{label}] manifest 없음 - 건너뜀")
        return None
    rows = list(csv.DictReader(open(man, encoding="utf-8-sig")))
    diffs = {k: [] for k in KEYS}
    n_used, n_failed = 0, 0
    for r in rows:
        jpg = os.path.join(set_dir, "jpeg", r["filename_jpeg"])
        raw = os.path.join(set_dir, "raw", r["filename_raw"])
        if not (os.path.exists(jpg) and os.path.exists(raw)):
            continue
        try:
            neutral = load_neutral_render(raw, max_dim=MAX_DIM)
            target = cv2.imread(jpg)
            if target is None:
                n_failed += 1
                continue
            target = cv2.resize(target, (neutral.shape[1], neutral.shape[0]),
                                interpolation=cv2.INTER_AREA)
        except Exception:
            n_failed += 1
            continue
        ns, ts = _stats(neutral), _stats(target)
        for k in KEYS:
            diffs[k].append(ts[k] - ns[k])
        n_used += 1
    if n_used < 5:
        print(f"  [{label}] 사용 가능 쌍 {n_used}개 - 표본 부족, 건너뜀")
        return None
    print(f"\n  [{label}] {n_used}쌍 (디코드 실패 {n_failed}개) - "
          f"카메라 JPEG 에서 neutral 렌더를 뺀 차이")
    stats = {k: _paired(k, diffs[k]) for k in KEYS}
    return dict(label=label, set=rel_dir, n_pairs=n_used, n_failed=n_failed,
                stats=stats)


def main():
    print("load_neutral_render() 계통 편향 - 브랜드 교차 확인\n")
    print(f"  [fuji 기준값] Classic Negative 47쌍 "
          f"(tools/diagnose_fuji_neutral_render_offset.py):")
    for k, v in FUJI_REFERENCE.items():
        print(f"    {k:16s} {v:+8.3f}")

    results = [r for r in (run_set(lbl, d) for lbl, d in SETS) if r]

    print("\n=== 종합 ===")
    if not results:
        print("측정 가능한 세트 없음 (raw/는 git-ignore 대상이라 클론마다 다름)")
    for k in KEYS:
        vals = [(r["label"], r["stats"][k]) for r in results]
        same_sign = all(np.sign(s["mean_diff"]) == np.sign(FUJI_REFERENCE[k])
                        for _, s in vals)
        all_sig = all(not s["inconclusive"] for _, s in vals)
        detail = "  ".join(f"{lbl}={s['mean_diff']:+.2f}" for lbl, s in vals)
        print(f"  {k:16s} fuji={FUJI_REFERENCE[k]:+7.2f}  {detail}")
        print(f"    -> 부호 일치 {'예' if same_sign else '아니오'}, "
              f"모든 세트 CI가 0 배제 {'예' if all_sig else '아니오'}")

    universal = [k for k in KEYS
                 if results
                 and all(np.sign(r["stats"][k]["mean_diff"]) == np.sign(FUJI_REFERENCE[k])
                         and not r["stats"][k]["inconclusive"] for r in results)]
    print(f"\n전 브랜드 공통으로 확인된 편향 지표: {universal or '없음'}")
    print("해석: 공통이면 이 저장소의 모든 population fit ΔE00이 같은 기준선 "
          "위에 있다는 뜻 - 룩 간 상대비교는 유효하나 절대값은 "
          "no_auto_bright=True 렌더 기준임을 명시해야 한다.")

    out = os.path.join(BASE, "datasets", "neutral_render_offset_by_brand.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "purpose": "load_neutral_render()의 노출/채도 계통 편향이 후지 "
                       "고유인지 전 브랜드 공통인지 확인",
            "cause_under_test": "tools/calibrate.py:130 no_auto_bright=True",
            "metric": "카메라 JPEG 통계 - neutral 렌더 통계 (페어별), 부호검정 + "
                      "부트스트랩 95% CI 20000회 고정 시드",
            "fuji_reference": FUJI_REFERENCE,
            "sets": results,
            "universal_biased_metrics": universal,
            "modifies_shipped_code": False,
        }, f, indent=2, ensure_ascii=False)
    print(f"리포트: {out}")


if __name__ == "__main__":
    main()
