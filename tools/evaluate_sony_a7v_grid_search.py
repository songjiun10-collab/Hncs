"""
Sony a7 V(ILCE-7M5) 75쌍 raw+jpeg 페어로 진짜 전/후 그리드서치 - Sony는
이제까지 population-fit(brands/sony.py, raw 기준선 없음)뿐이었는데 처음으로
raw+jpeg 페어를 확보해서 Hasselblad와 동일한 방법론(그레이딩 전 중립
렌더링 -> 베이스라인, 카메라 JPEG -> 타깃)을 적용한다.

apply_sony_look()(population-fit, brands/sony.py)은 이 실험으로 손대지
않는다 - brands/CLAUDE.md의 "기존 apply_* 수정 금지" 원칙. 결과가 좋으면
별도 파일(brands/sony_a7v.py)에 새 함수로 추가한다.

  python3 -m tools.evaluate_sony_a7v_grid_search
"""
import csv
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.curve import film_curve
from core.validation import is_image_array_usable
from tools.calibrate import load_neutral_render, gray_stats, _resize_to_max_dim

RAW_DIR = "/Users/songjiun/Documents/raw pair"
MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "datasets", "sony", "a7v_raw_jpeg_pairs_clean.csv")


def apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip):
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)
    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def main():
    rows = list(csv.DictReader(open(MANIFEST)))
    print(f"Sony a7V 페어 후보: {len(rows)}개", flush=True)

    dataset = []
    for i, r in enumerate(rows):
        raw_path = os.path.join(RAW_DIR, r['raw_file'])
        jpeg_path = os.path.join(RAW_DIR, r['jpeg_file'])
        if not (os.path.exists(raw_path) and os.path.exists(jpeg_path)):
            continue
        try:
            neutral = load_neutral_render(raw_path)
        except Exception as e:
            print(f"  [{i+1}/{len(rows)}] {r['raw_file']} raw 디코드 실패: {e}", flush=True)
            continue
        target_img = cv2.imread(jpeg_path)
        if target_img is None or not is_image_array_usable(target_img):
            print(f"  [{i+1}/{len(rows)}] {r['jpeg_file']} jpeg 로드 실패", flush=True)
            continue
        target_img = _resize_to_max_dim(target_img, 2000)
        target_stats = gray_stats(target_img)
        shadow_valid = target_stats['dark_pct'] > 5
        dataset.append(dict(name=r['raw_file'], neutral=neutral, target=target_stats,
                             shadow_valid=shadow_valid))
        print(f"  [{i+1}/{len(rows)}] {r['raw_file']} OK - "
              f"타깃 b2={target_stats['b2']:.1f} w995={target_stats['w995']:.1f}", flush=True)

    n = len(dataset)
    print(f"\n사용 가능한 페어: {n}개 (그림자유효 {sum(d['shadow_valid'] for d in dataset)}개)")

    def pair_error(d, s):
        err = (s['w995'] - d['target']['w995']) ** 2
        if d['shadow_valid']:
            err += (s['b2'] - d['target']['b2']) ** 2
        return err

    # 현재 population-fit 기본값(brands/sony.py) 대비 비교용
    CUR_TOE_LIFT, CUR_SHOULDER_START, CUR_WHITE_POINT, CUR_CLAHE_CLIP = 9.1 / 255, 0.78, 228.6 / 255, 1.25

    TOE_LIFTS = (0.0, 0.02, 0.036, 0.06)
    SHOULDER_STARTS = (0.50, 0.58, 0.66, 0.70, 0.74, 0.78, 0.82)
    # white_point가 1.0(탐색범위 상한)에서 잡혀서 범위를 위로 넓힘 -
    # Hasselblad v10 때(brands/hasselblad.py 이력)와 같은 패턴
    # 2026-08 정정: white_point>1.0 쪽으로 그리드서치가 확장되면서
    # RMSE(percentile)는 크게 이겼지만(52.7%) 실제 ΔE00은 오히려 유의하게
    # 졌다(-1.02%, tools/evaluate_sony_a7v_de00.py) - 목적함수(percentile)를
    # 과도하게 겨냥한 하이라이트 클리핑으로 의심되어 1.0 이하로 되돌림.
    WHITE_POINTS = (0.85, 0.90, 0.897, 0.95, 1.0)
    combos = [(tl, ss, wp) for tl in TOE_LIFTS for ss in SHOULDER_STARTS for wp in WHITE_POINTS]

    print(f"\n{len(combos)}개 조합 x {n}쌍 - 오차 행렬 계산중...", flush=True)
    sqerr = np.zeros((len(combos), n), dtype=np.float64)
    for ci, (tl, ss, wp) in enumerate(combos):
        for pi, d in enumerate(dataset):
            graded = apply_population_fit_look(d['neutral'], tl, ss, wp, CUR_CLAHE_CLIP)
            sqerr[ci, pi] = pair_error(d, gray_stats(graded))
        if ci % 50 == 0:
            print(f"  콤보 {ci}/{len(combos)}", flush=True)

    in_sample_best_ci = int(np.argmin(sqerr.mean(axis=1)))
    toe_lift, shoulder_start, white_point = combos[in_sample_best_ci]
    err = sqerr[in_sample_best_ci].mean()
    print(f"\n=== in-sample 최적 파라미터 (RMSE={err ** 0.5:.2f}) ===")
    print(f"toe_lift={toe_lift}, shoulder_start={shoulder_start}, white_point={white_point}, "
          f"clahe_clip={CUR_CLAHE_CLIP}(고정)")

    baseline_sqerr = np.array([pair_error(d, gray_stats(apply_population_fit_look(
        d['neutral'], CUR_TOE_LIFT, CUR_SHOULDER_START, CUR_WHITE_POINT, CUR_CLAHE_CLIP)))
        for d in dataset])
    print(f"\n기존 population-fit(brands/sony.py) RMSE={(baseline_sqerr.mean()) ** 0.5:.2f}")
    print(f"신규 raw+jpeg 그리드서치(in-sample) RMSE={err ** 0.5:.2f}")

    # === LOO 검증 ===
    print(f"\n=== LOO 검증({n}폴드) ===", flush=True)
    paired = []
    chosen_counts = {}
    for i in range(n):
        train_mask = np.ones(n, dtype=bool)
        train_mask[i] = False
        train_mean = sqerr[:, train_mask].mean(axis=1)
        best_ci = int(np.argmin(train_mean))
        loo_e = sqerr[best_ci, i]
        paired.append((dataset[i]['name'], baseline_sqerr[i] ** 0.5, loo_e ** 0.5))
        chosen_counts[combos[best_ci]] = chosen_counts.get(combos[best_ci], 0) + 1

    from tools.calibrate import summarize, print_summary
    s = summarize(paired)
    print_summary(s, label_a="기존(population-fit)", label_b="LOO 그리드서치")

    print("\n폴드별 선택 조합 상위:")
    for combo, cnt in sorted(chosen_counts.items(), key=lambda kv: -kv[1])[:5]:
        print(f"  {cnt:3d}/{n}  toe_lift={combo[0]}, shoulder_start={combo[1]}, white_point={combo[2]}")


if __name__ == "__main__":
    main()
