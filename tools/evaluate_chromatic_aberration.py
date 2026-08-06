"""
색수차 보정(chromatic_aberration) 실험 - rawpy raw.postprocess()의
chromatic_aberration=(red_scale, blue_scale) 파라미터(기본 (1,1)=
보정없음)로 렌즈 횡색수차를 보정하면 ΔE00이 줄어드는지 확인한다.

origin 저장소(GitHub songjiun10-collab/Hncs)의
docs/superpowers/specs/2026-07-31-chromatic-aberration-correction-design.md
설계를 이 로컬 체크아웃(hybrid_engine 없음)에 맞게 재현 - 13쌍(X1D
전용) 대신 dpreview.com에서 받은 편집 오염 제외 클린 95쌍(5세대 중
4세대: CFV/X2D/X2D II/X1D II, X1D는 클린 표본 1장뿐이라 그리드서치
자체가 무의미해서 제외)을 쓴다.

  python3 -m tools.evaluate_chromatic_aberration

apply_hncs()는 건드리지 않는다(원본 스펙과 동일한 이유 - 이 실험은
raw 디코드 단계 전용, 톤커브 단계와 무관).
"""
import csv
import itertools
import math
import os
import sys
import time

import cv2
import numpy as np
import rawpy
from skimage.color import rgb2lab, deltaE_ciede2000

RAW_DIR = "/Users/songjiun/Documents/raw pair"
MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "datasets", "hasselblad", "dpreview_raw_jpeg_pairs_clean.csv")
DOWNSAMPLE_MAX_DIM = 512
SCALES = [0.98, 0.985, 0.99, 0.995, 1.0, 1.005, 1.01, 1.015, 1.02]
COMBOS = list(itertools.product(SCALES, SCALES))  # (red_scale, blue_scale), 81개


def _resize_max_dim(img, max_dim=DOWNSAMPLE_MAX_DIM):
    h, w = img.shape[:2]
    scale = max_dim / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def decode_raw(raw_path, chromatic_aberration=None, max_dim=DOWNSAMPLE_MAX_DIM):
    """rawpy 기본 색공간(camera_wb, sRGB, gamma=(1,1) pure linear) -
    hybrid_engine/utils/io.py의 decode_raw()와 동일 정의. half_size=True로
    데모자이크를 건너뛰어 81콤보 x 95쌍 규모 그리드서치 속도를 확보한다
    (색수차는 전역 채널 스케일링이라 다운샘플/half_size가 결과를 실질적
    으로 왜곡하지 않는다는 게 원본 스펙의 판단, 이 세션의 다른 실험에서도
    반복 확인된 가정)."""
    kwargs = dict(
        use_camera_wb=True,
        no_auto_bright=True,
        output_bps=16,
        output_color=rawpy.ColorSpace.sRGB,
        gamma=(1, 1),
        half_size=True,
    )
    if chromatic_aberration is not None:
        kwargs["chromatic_aberration"] = chromatic_aberration
    with rawpy.imread(raw_path) as raw:
        rgb16 = raw.postprocess(**kwargs)
    rgb16 = _resize_max_dim(rgb16, max_dim)
    return rgb16.astype(np.float64) / 65535.0


def load_target_srgb(jpeg_path, shape_hw):
    bgr = cv2.imread(jpeg_path)
    if bgr is None:
        return None
    bgr = cv2.resize(bgr, (shape_hw[1], shape_hw[0]), interpolation=cv2.INTER_AREA)
    return bgr[:, :, ::-1]


def linear_to_srgb8(rgb_linear):
    # 별도 colour-science 의존 없이 표준 sRGB OETF를 직접 구현
    x = np.clip(rgb_linear, 0.0, 1.0)
    low = x <= 0.0031308
    out = np.where(low, x * 12.92, 1.055 * np.power(np.maximum(x, 1e-8), 1 / 2.4) - 0.055)
    return (np.clip(out, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def mean_delta_e(rgb_a_u8, rgb_b_u8):
    lab_a = rgb2lab(rgb_a_u8.astype(np.float64) / 255.0)
    lab_b = rgb2lab(rgb_b_u8.astype(np.float64) / 255.0)
    return float(np.mean(deltaE_ciede2000(lab_a, lab_b)))


def _sign_test_p(n_better, n_worse):
    n = n_better + n_worse
    if n == 0:
        return 1.0
    k = min(n_better, n_worse)
    total = sum(math.comb(n, i) for i in range(0, k + 1))
    return min(1.0, 2 * total / (2 ** n))


def _bootstrap_ci(diffs, n_resamples=10000, seed=0):
    rng = np.random.RandomState(seed)
    diffs = np.asarray(diffs)
    means = np.empty(n_resamples)
    n = len(diffs)
    for i in range(n_resamples):
        idx = rng.randint(0, n, n)
        means[i] = diffs[idx].mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def _paired_t(diffs):
    diffs = np.asarray(diffs)
    n = len(diffs)
    mean = diffs.mean()
    se = diffs.std(ddof=1) / math.sqrt(n)
    return mean / se if se > 0 else float("inf")


def summarize(baseline_de, best_de, names):
    diffs = np.asarray(baseline_de) - np.asarray(best_de)  # 양수 = 보정이 더 나음
    n_better = int((diffs > 1e-9).sum())
    n_worse = int((diffs < -1e-9).sum())
    n_tie = len(diffs) - n_better - n_worse
    p = _sign_test_p(n_better, n_worse)
    t = _paired_t(diffs)
    ci_lo, ci_hi = _bootstrap_ci(diffs)
    rel_pct = float(diffs.mean() / np.mean(baseline_de) * 100)

    drop_one = []
    for i in range(len(diffs)):
        rest = np.delete(diffs, i)
        drop_one.append(float(rest.mean()))

    return dict(
        n=len(diffs), mean_baseline=float(np.mean(baseline_de)), mean_best=float(np.mean(best_de)),
        mean_diff=float(diffs.mean()), rel_pct=rel_pct, n_better=n_better, n_worse=n_worse, n_tie=n_tie,
        sign_test_p=p, t_stat=t, ci_lo=ci_lo, ci_hi=ci_hi,
        drop_one_min=min(drop_one), drop_one_max=max(drop_one),
    )


def print_summary(s):
    print(f"\n=== 요약 (n={s['n']}) ===")
    print(f"보정없음 평균 ΔE00={s['mean_baseline']:.3f}  LOO 최적보정 평균 ΔE00={s['mean_best']:.3f}")
    print(f"평균 개선폭={s['mean_diff']:+.3f} ({s['rel_pct']:+.2f}%)")
    print(f"승/패/동률={s['n_better']}/{s['n_worse']}/{s['n_tie']}  부호검정 p={s['sign_test_p']:.4f}")
    print(f"대응표본 t={s['t_stat']:.3f}")
    print(f"부트스트랩 95% CI=[{s['ci_lo']:+.3f}, {s['ci_hi']:+.3f}]")
    print(f"drop-one 민감도 범위=[{s['drop_one_min']:+.3f}, {s['drop_one_max']:+.3f}]")
    if s['ci_lo'] <= 0 <= s['ci_hi']:
        print("판정: 보류 (95% CI가 0을 포함)")
    else:
        direction = "개선" if s['mean_diff'] > 0 else "악화"
        print(f"판정: 방향 있음 - 색수차 보정이 평균 {abs(s['rel_pct']):.2f}% {direction}")


def main():
    rows = list(csv.DictReader(open(MANIFEST)))
    print(f"페어 {len(rows)}개, 콤보 {len(COMBOS)}개 (red_scale x blue_scale) - "
          f"총 {len(rows) * len(COMBOS)}회 디코드 예정", flush=True)

    # matrix[i][combo_idx] = 그 콤보로 디코드했을 때의 ΔE00
    matrix = np.zeros((len(rows), len(COMBOS)), dtype=np.float64)
    names = []
    t0 = time.time()
    for i, r in enumerate(rows):
        raw_path = os.path.join(RAW_DIR, r["raw_file"])
        jpg_path = os.path.join(RAW_DIR, r["jpeg_file"])
        names.append(r["raw_file"])
        target_u8 = None
        for j, combo in enumerate(COMBOS):
            try:
                linear = decode_raw(raw_path, chromatic_aberration=combo)
            except Exception as e:
                print(f"  [{i+1}/{len(rows)}] {r['raw_file']} combo={combo} 디코드 실패: {e}", flush=True)
                matrix[i, j] = np.nan
                continue
            if target_u8 is None:
                target_u8 = load_target_srgb(jpg_path, linear.shape[:2])
                if target_u8 is None:
                    print(f"  [{i+1}/{len(rows)}] {r['jpeg_file']} 타깃 로드 실패", flush=True)
                    break
            out_u8 = linear_to_srgb8(linear)
            matrix[i, j] = mean_delta_e(out_u8, target_u8)
        elapsed = time.time() - t0
        eta = elapsed / (i + 1) * (len(rows) - i - 1)
        print(f"  [{i+1}/{len(rows)}] {r['raw_file']} ({r['model']}) 완료  "
              f"({elapsed:.0f}s경과, 예상잔여 {eta:.0f}s)", flush=True)

    np.save("/tmp/ca_matrix.npy", matrix)
    with open("/tmp/ca_names.txt", "w") as f:
        f.write("\n".join(names))

    baseline_idx = COMBOS.index((1.0, 1.0))
    baseline_de = matrix[:, baseline_idx]

    # LOO: 매 fold마다 나머지 n-1쌍 평균 ΔE가 최소인 콤보를 훈련데이터로 선택
    best_de = np.zeros(len(rows))
    chosen_combos = []
    for i in range(len(rows)):
        train_mask = np.ones(len(rows), dtype=bool)
        train_mask[i] = False
        train_means = np.nanmean(matrix[train_mask], axis=0)
        best_combo_idx = int(np.nanargmin(train_means))
        chosen_combos.append(COMBOS[best_combo_idx])
        best_de[i] = matrix[i, best_combo_idx]

    print("\n=== 페어별 (보정없음 ΔE00, LOO 최적보정 ΔE00, 선택된 콤보) ===")
    for i, r in enumerate(rows):
        print(f"  {r['raw_file']:20s} ({r['model']:16s})  base={baseline_de[i]:6.3f}  "
              f"best={best_de[i]:6.3f}  combo={chosen_combos[i]}")

    s = summarize(baseline_de, best_de, names)
    print_summary(s)


if __name__ == "__main__":
    main()
