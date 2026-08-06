"""
X2D II 전용 파라미터가 풀링(main) 기본값 대비 유의미하게 나은지 -
`tools.calibrate.run_grid_search_loo_per_generation`이 65쌍(X2D II 없음)
세대들에 대해 한 것과 정확히 같은 방법론을, dpreview에서 받은 X2D II
41쌍(전부 클린, 편집 오염 없음)에 적용한다.

폴드마다 held-out 1쌍을 빼고 나머지 40쌍에서 4-파라미터 그리드
(exposure_gamma x toe_lift x shoulder_start x white_point, 441콤보)의
평균오차 최소 조합을 뽑아 그 held-out 쌍에 적용 - RMSE(b2/w995
percentile) 기준. main(현재 apply_hncs 기본값)과 페어드 비교.

LOO에 이어 **5-fold**도 같은 오차 행렬로 돌린다. 441개 후보가 전부 고정
상수라(데이터에 적응적으로 피팅되는 게 없음) 그리드 선택 자체엔 내부
CV를 얹어도 값이 안 바뀌지만(외부 루프가 이미 leak-free LOO라 이미
중첩 CV와 수학적으로 동일), 학습셋을 40쌍(LOO)에서 33쌍 안팎(5-fold)
으로 줄이면 "선택이 실제로 더 적은 데이터에서도 안정적인가"는 별개로
확인된다 - 더 보수적인 out-of-sample 추정치로 취급.

  python3 -m tools.evaluate_x2dii_generation_loo
"""
import csv
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.hasselblad import apply_hncs
from core.validation import is_image_array_usable
from tools.calibrate import (
    load_neutral_render, gray_stats, _resize_to_max_dim,
    _grid_search_combos, _fold_best_combo, summarize, print_summary,
)

RAW_DIR = "/Users/songjiun/Documents/raw pair"
MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "datasets", "hasselblad", "dpreview_raw_jpeg_pairs_clean.csv")


def pair_error(stats, target, shadow_valid):
    err = (stats['w995'] - target['w995']) ** 2
    if shadow_valid:
        err += (stats['b2'] - target['b2']) ** 2
    return err


def main():
    rows = [r for r in csv.DictReader(open(MANIFEST)) if r['model'] == 'X2D II 100C']
    print(f"X2D II 페어 {len(rows)}개", flush=True)

    dataset = []
    for i, r in enumerate(rows):
        raw_path = os.path.join(RAW_DIR, r['raw_file'])
        jpg_path = os.path.join(RAW_DIR, r['jpeg_file'])
        if not (os.path.exists(raw_path) and os.path.exists(jpg_path)):
            continue
        try:
            neutral = load_neutral_render(raw_path)
        except Exception as e:
            print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 디코드 실패: {e}")
            continue
        target_img = cv2.imread(jpg_path)
        if target_img is None or not is_image_array_usable(target_img):
            continue
        target_img = _resize_to_max_dim(target_img, 2000)
        target = gray_stats(target_img)
        dataset.append(dict(name=r['raw_file'], neutral=neutral, target=target,
                             shadow_valid=target['dark_pct'] > 5))
        print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 처리 완료", flush=True)

    n = len(dataset)
    print(f"\n사용 가능한 페어: {n}개")

    combos = _grid_search_combos()
    print(f"{len(combos)}개 파라미터 조합 x {n}쌍 - 오차 행렬 계산중...", flush=True)
    sqerr = np.zeros((len(combos), n), dtype=np.float64)
    for ci, (eg, tl, ss, wp) in enumerate(combos):
        for pi, d in enumerate(dataset):
            graded = apply_hncs(d['neutral'], toe_lift=tl, shoulder_start=ss,
                                 white_point=wp, exposure_gamma=eg)
            sqerr[ci, pi] = pair_error(gray_stats(graded), d['target'], d['shadow_valid'])
        if ci % 50 == 0:
            print(f"  콤보 {ci}/{len(combos)}", flush=True)

    baseline_sqerr = np.array([pair_error(gray_stats(apply_hncs(d['neutral'])),
                                           d['target'], d['shadow_valid'])
                                for d in dataset])

    paired = []
    chosen_combo_counts = {}
    for i in range(n):
        best_ci = _fold_best_combo(sqerr, i)
        loo_e = sqerr[best_ci, i]
        paired.append((dataset[i]['name'], baseline_sqerr[i] ** 0.5, loo_e ** 0.5))
        chosen_combo_counts[combos[best_ci]] = chosen_combo_counts.get(combos[best_ci], 0) + 1

    s = summarize(paired)
    print(f"\n=== X2D II 100C (n={n}) - main(풀링) vs X2D II 전용 LOO ===")
    print_summary(s, label_a="main(풀링)", label_b="X2D II 전용")

    print("\n폴드별 선택 조합 빈도:")
    for combo, cnt in sorted(chosen_combo_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {cnt:3d}/{n}  exposure_gamma={combo[0]}, toe_lift={combo[1]}, "
              f"shoulder_start={combo[2]}, white_point={combo[3]}")

    in_sample_best_ci = int(np.argmin(sqerr.mean(axis=1)))
    best_combo = combos[in_sample_best_ci]
    print(f"\n전체 {n}쌍으로 피팅한 in-sample 최적 조합(배포 후보): "
          f"exposure_gamma={best_combo[0]}, toe_lift={best_combo[1]}, "
          f"shoulder_start={best_combo[2]}, white_point={best_combo[3]}")

    # --- 5-fold (더 보수적인 out-of-sample 추정치) ---
    K = 5
    rng = np.random.RandomState(0)
    order = rng.permutation(n)
    folds = np.array_split(order, K)

    paired_kfold = []
    kfold_combo_counts = {}
    for fi, test_idx in enumerate(folds):
        train_idx = np.setdiff1d(order, test_idx)
        best_ci = int(np.argmin(sqerr[:, train_idx].mean(axis=1)))
        kfold_combo_counts[combos[best_ci]] = kfold_combo_counts.get(combos[best_ci], 0) + len(test_idx)
        for i in test_idx:
            paired_kfold.append((dataset[i]['name'], baseline_sqerr[i] ** 0.5,
                                  sqerr[best_ci, i] ** 0.5))
        print(f"  fold {fi+1}/{K}: test n={len(test_idx)}, train n={len(train_idx)}, "
              f"선택 조합={combos[best_ci]}", flush=True)

    sk = summarize(paired_kfold)
    print(f"\n=== X2D II 100C (n={n}) - main(풀링) vs X2D II 전용 {K}-fold ===")
    print_summary(sk, label_a="main(풀링)", label_b=f"X2D II 전용({K}-fold)")

    print(f"\n{K}-fold 폴드별 선택 조합(가중치=그 폴드 test n):")
    for combo, cnt in sorted(kfold_combo_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {cnt:3d}/{n}  exposure_gamma={combo[0]}, toe_lift={combo[1]}, "
              f"shoulder_start={combo[2]}, white_point={combo[3]}")


if __name__ == "__main__":
    main()
