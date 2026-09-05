"""Classic Negative의 큰 ΔE00이 **룩 상수 탓인지 RAW 렌더 노출 탓인지**를
가른다.

**배경**: `tools/diagnose_fuji_neutral_render_offset.py`가
`load_neutral_render()` 출력이 카메라 JPEG보다 Lab L 중앙값 기준 크게 어둡고
채도가 높다는 계통 편향을 확인했다(47/47쌍, 부트스트랩 95% CI 0 배제). 원인은
`tools/calibrate.py:130`의 `no_auto_bright=True` - RAF의 노출 헤드룸을 쓰지
않는 "무가공 베이스라인"이라 의도된 동작이다.

**가르는 실험**: `apply_classic_negative`의 **현행 상수를 하나도 바꾸지 않고**
렌더만 auto-bright 켠 버전으로 갈아끼워 ΔE00을 다시 잰다.

- ΔE00이 크게 떨어지면: 현행 상수는 멀쩡하고 큰 오차는 렌더 노출 격차였다.
  -> `tools/recalibrate_fuji_classic_negative.py`가 찾은 "개선"은 룩 상수로
  노출을 보정한 것이므로 배포하면 안 된다.
- 거의 안 떨어지면: 격차가 룩 자체에 있다. -> 재보정 결과가 유효하다.

성공 기준을 결과 보기 전에 못 박는다: **페어드 부트스트랩 95% CI(20000회,
고정 시드)가 0을 배제하고 auto-bright 렌더가 우세할 때만** "렌더 노출이
원인"으로 판정한다. CI가 0을 포함하면 판정 보류다.

`tools/calibrate.py`와 `brands/fuji.py`는 읽기만 한다 - 어느 파일도 수정하지
않는다.

  ~/.hncs-hybrid-venv312/bin/python3 -m tools.diagnose_fuji_autobright_vs_look
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
import rawpy

from brands.fuji import apply_classic_negative
from hybrid_engine.utils.evaluate import mean_delta_e
from tools.calibrate import load_neutral_render

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_DIR = os.path.join(BASE, "datasets", "fuji", "contributed", "local-work-2026-08")
MAX_DIM = 400
FILM_MODE = "Classic Negative"


def _resize_max_dim(img, max_dim):
    h, w = img.shape[:2]
    s = max_dim / float(max(h, w))
    if s >= 1.0:
        return img
    return cv2.resize(img, (int(round(w * s)), int(round(h * s))),
                      interpolation=cv2.INTER_AREA)


def load_autobright_render(raw_path, max_dim=MAX_DIM):
    """`load_neutral_render()`와 동일하되 auto-bright만 켠다."""
    with rawpy.imread(raw_path) as raw:
        rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=False,
                              output_bps=8, gamma=(2.222, 4.5))
    return _resize_max_dim(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), max_dim)


def _film_mode(jpg_path):
    return subprocess.run(["exiftool", "-s3", "-FilmMode", jpg_path],
                          capture_output=True, text=True, timeout=30).stdout.strip()


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n))


def summarize(a, b, label_a, label_b, n_bootstrap=20000, seed=0):
    """a - b 를 페어드로 비교. 양수면 b(두 번째)가 우세."""
    d = np.asarray(a, float) - np.asarray(b, float)
    n = len(d)
    rng = np.random.default_rng(seed)
    boot = np.array([d[rng.integers(0, n, n)].mean() for _ in range(n_bootstrap)])
    lo, hi = (float(v) for v in np.percentile(boot, [2.5, 97.5]))
    wins, losses = int((d > 0).sum()), int((d < 0).sum())
    p = _sign_test_p(wins, losses)
    incon = lo <= 0.0 <= hi
    print(f"\n평균 {label_a} ΔE00={np.mean(a):.4f}  평균 {label_b} ΔE00={np.mean(b):.4f}  "
          f"개선폭={100.0 * d.mean() / np.mean(a):+.2f}%")
    print(f"승/패={wins}/{losses}  부호검정 p={p:.4f}  "
          f"부트스트랩 95% CI=[{lo:+.4f}, {hi:+.4f}]")
    print(f"판정: {'판정 보류 (CI가 0 포함)' if incon else (label_b + ' 우세' if d.mean() > 0 else label_a + ' 우세')}")
    return dict(mean_a=float(np.mean(a)), mean_b=float(np.mean(b)), n=n,
                wins=wins, losses=losses, p_value=p, ci_lo=lo, ci_hi=hi,
                inconclusive=bool(incon))


def main():
    rows = list(csv.DictReader(open(os.path.join(SET_DIR, "manifest.csv"),
                                    encoding="utf-8-sig")))
    de_neutral, de_autobright, names = [], [], []
    for r in rows:
        jpg = os.path.join(SET_DIR, "jpeg", r["filename_jpeg"])
        raw = os.path.join(SET_DIR, "raw", r["filename_raw"])
        if not (os.path.exists(jpg) and os.path.exists(raw)):
            continue
        if _film_mode(jpg) != FILM_MODE:
            continue
        nr = load_neutral_render(raw, max_dim=MAX_DIM)
        ab = load_autobright_render(raw, max_dim=MAX_DIM)
        # 두 렌더의 리사이즈 반올림이 1px 어긋날 수 있다 - neutral 쪽에 맞춘다
        if ab.shape[:2] != nr.shape[:2]:
            ab = cv2.resize(ab, (nr.shape[1], nr.shape[0]),
                            interpolation=cv2.INTER_AREA)
        tgt = cv2.resize(cv2.imread(jpg), (nr.shape[1], nr.shape[0]),
                         interpolation=cv2.INTER_AREA)
        de_neutral.append(mean_delta_e(apply_classic_negative(nr), tgt))
        de_autobright.append(mean_delta_e(apply_classic_negative(ab), tgt))
        names.append(r["filename_raw"])
        if len(names) % 10 == 0:
            print(f"  {len(names)}개 처리", flush=True)

    print(f"\n[{FILM_MODE}] {len(names)}쌍 - apply_classic_negative 현행 상수 고정, "
          f"RAW 렌더만 교체")
    stats = summarize(de_neutral, de_autobright, "neutral(현행)", "auto-bright")

    out = os.path.join(SET_DIR, "autobright_vs_look_classic_negative.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "question": "Classic Negative의 큰 ΔE00이 룩 상수 탓인가 RAW 렌더 "
                        "노출 탓인가",
            "method": "apply_classic_negative 현행 상수 고정, load_neutral_render "
                      "(no_auto_bright=True) vs 동일 설정에 auto-bright만 켠 렌더",
            "criterion": "페어드 부트스트랩 95% CI 20000회 고정 시드가 0을 배제하고 "
                         "auto-bright가 우세할 때만 '렌더 노출이 원인'으로 판정",
            "film_mode": FILM_MODE,
            "set": "datasets/fuji/contributed/local-work-2026-08",
            "n_pairs": len(names),
            "images": names,
            "delta_e_neutral": de_neutral,
            "delta_e_autobright": de_autobright,
            "stats": stats,
        }, f, indent=2, ensure_ascii=False)
    print(f"리포트: {out}")


if __name__ == "__main__":
    main()
