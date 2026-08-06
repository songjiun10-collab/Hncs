"""
main(origin)과 candidate(로컬 v13) 두 apply_hncs 파라미터 후보를, 둘 다
안 갖고 있던 조합의 데이터 - X2D II 41장을 포함한 dpreview 클린 95쌍
(datasets/hasselblad/dpreview_raw_jpeg_pairs_clean.csv) - 로 직접
맞대결시킨다.

두 후보는 shoulder_start=0.5/white_point=1.0에는 이미 합의했고, 실질
쟁점은 exposure_gamma(0.8 vs 0.7)와 toe_lift(0.0 vs 0.005)뿐이라 그리드
서치가 아니라 단순 페어드 비교(LOO 아님 - 파라미터 자체가 고정된 두
후보를 비교하는 것뿐이라 학습이 없다):

  main      : toe_lift=0.0,   shoulder_start=0.5, white_point=1.0, exposure_gamma=0.8
  candidate : toe_lift=0.005, shoulder_start=0.5, white_point=1.0, exposure_gamma=0.7

  python3 -m tools.evaluate_exposure_gamma_x2dii
"""
import csv
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.hasselblad import apply_hncs
from core.validation import is_image_array_usable
from tools.calibrate import load_neutral_render, gray_stats, _resize_to_max_dim, summarize, print_summary

RAW_DIR = "/Users/songjiun/Documents/raw pair"
MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "datasets", "hasselblad", "dpreview_raw_jpeg_pairs_clean.csv")

MAIN = dict(toe_lift=0.0, shoulder_start=0.5, white_point=1.0, exposure_gamma=0.8)
CANDIDATE = dict(toe_lift=0.005, shoulder_start=0.5, white_point=1.0, exposure_gamma=0.7)


def pair_error(stats, target, shadow_valid):
    err = (stats['w995'] - target['w995']) ** 2
    if shadow_valid:
        err += (stats['b2'] - target['b2']) ** 2
    return err


def main():
    rows = list(csv.DictReader(open(MANIFEST)))
    print(f"페어 {len(rows)}개 (X2D II 포함 5세대)", flush=True)

    per_fold = []
    per_fold_by_gen = {}
    for i, r in enumerate(rows):
        raw_path = os.path.join(RAW_DIR, r['raw_file'])
        jpg_path = os.path.join(RAW_DIR, r['jpeg_file'])
        if not (os.path.exists(raw_path) and os.path.exists(jpg_path)):
            print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 파일 없음, 제외")
            continue
        try:
            neutral = load_neutral_render(raw_path)
        except Exception as e:
            print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 디코드 실패: {e}")
            continue
        target_img = cv2.imread(jpg_path)
        if target_img is None or not is_image_array_usable(target_img):
            print(f"  [{i+1}/{len(rows)}] {r['jpeg_file']} 로드 실패")
            continue
        target_img = _resize_to_max_dim(target_img, 2000)
        target = gray_stats(target_img)
        shadow_valid = target['dark_pct'] > 5

        stats_a = gray_stats(apply_hncs(neutral, **MAIN))
        stats_b = gray_stats(apply_hncs(neutral, **CANDIDATE))
        err_a = pair_error(stats_a, target, shadow_valid)
        err_b = pair_error(stats_b, target, shadow_valid)

        per_fold.append((r['raw_file'], err_a, err_b))
        per_fold_by_gen.setdefault(r['model'], []).append((r['raw_file'], err_a, err_b))
        print(f"  [{i+1}/{len(rows)}] {r['raw_file']} ({r['model']}) "
              f"main_err={err_a:.1f} candidate_err={err_b:.1f}", flush=True)

    print(f"\n사용 가능한 페어: {len(per_fold)}개", flush=True)

    s = summarize(per_fold)
    print("\n=== 전체 (95쌍, X2D II 41 포함) ===")
    print_summary(s, label_a="main(eg=0.8,tl=0.0)", label_b="candidate(eg=0.7,tl=0.005)")

    for gen, fold in sorted(per_fold_by_gen.items()):
        if len(fold) < 2:
            continue
        gs = summarize(fold)
        print(f"\n=== {gen} (n={len(fold)}) ===")
        print_summary(gs, label_a="main", label_b="candidate")


if __name__ == "__main__":
    main()
