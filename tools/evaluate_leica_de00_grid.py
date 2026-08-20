"""
Leica SL3-P / Q3 43 raw+jpeg 페어로 첫 raw 기반 캘리브레이션 - Sony a7V
때(tools/evaluate_sony_a7v_grid_search.py, brands/sony_a7v.py 이력) b2/w995
percentile RMSE를 목적함수로 쓴 그리드서치가 RMSE로는 크게 이기고도 실제
ΔE00으로는 졌던 교훈을 반영해서, 처음부터 ΔE00(CIEDE2000)을 직접
목적함수로 그리드서치한다. 두 바디를 따로 처리(센서/렌즈 시스템이 달라
같은 커브를 가정할 근거가 없음 - Hasselblad X2D II를 다른 세대와 분리한
것과 같은 이유).

brands/leica.py의 apply_leica_look()(population-fit, M9/X Vario/SL2 기반)은
이 실험으로 손대지 않는다 - brands/CLAUDE.md 원칙. 결과가 좋으면 별도
파일에 새 함수로 추가한다.

  python3 -m tools.evaluate_leica_de00_grid sl3p
  python3 -m tools.evaluate_leica_de00_grid q343
"""
import csv
import math
import os
import sys

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.curve import film_curve
from core.validation import is_image_array_usable
from tools.calibrate import load_neutral_render

RAW_DIR = "/Users/songjiun/Documents/raw pair"
DATASET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "datasets", "leica")

TARGETS = {
    "sl3p": ("sl3p_raw_jpeg_pairs_clean.csv", "LEICA SL3-P"),
    "q343": ("q343_raw_jpeg_pairs_clean.csv", "LEICA Q3 43"),
}

GRID_MAX_DIM = 200
CONFIRM_MAX_DIM = 400
CLAHE_CLIP = 1.25  # population-fit 값 차용, 미검증 - 이번 실험 범위 밖

TOE_LIFTS = (0.0, 0.02, 0.036, 0.06)
SHOULDER_STARTS = (0.50, 0.58, 0.66, 0.70, 0.74, 0.78, 0.82)
WHITE_POINTS = (0.85, 0.90, 0.95, 1.0)  # Sony 교훈 반영 - 1.0 이하만 (경계 넘기지 않음)
COMBOS = [(tl, ss, wp) for tl in TOE_LIFTS for ss in SHOULDER_STARTS for wp in WHITE_POINTS]

# 기존 population-fit 기본값(brands/leica.py) - 세 바디 population 평균 기준
CUR_TOE_LIFT, CUR_SHOULDER_START, CUR_WHITE_POINT = 9.2 / 255, 0.78, 229.8 / 255


def apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip=CLAHE_CLIP):
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)
    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def load_target_linear(jpg_path, shape_hw):
    bgr = cv2.imread(jpg_path)
    bgr = cv2.resize(bgr, (shape_hw[1], shape_hw[0]), interpolation=cv2.INTER_AREA)
    rgb = bgr[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def bgr_u8_to_linear(bgr_u8):
    rgb = bgr_u8[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def mean_delta_e(linear_a, linear_b):
    from skimage.color import rgb2lab, deltaE_ciede2000
    a = colour.cctf_encoding(np.clip(linear_a, 0.0, 1.0), function="sRGB")
    b = colour.cctf_encoding(np.clip(linear_b, 0.0, 1.0), function="sRGB")
    return float(np.mean(deltaE_ciede2000(rgb2lab(a), rgb2lab(b))))


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def main():
    key = sys.argv[1] if len(sys.argv) > 1 else "sl3p"
    manifest_name, model = TARGETS[key]
    manifest = os.path.join(DATASET_DIR, manifest_name)
    rows = list(csv.DictReader(open(manifest)))
    print(f"{model} 페어 후보: {len(rows)}개", flush=True)

    pairs = []
    for i, r in enumerate(rows):
        raw_path = os.path.join(RAW_DIR, r['raw_file'])
        jpg_path = os.path.join(RAW_DIR, r['jpeg_file'])
        if not (os.path.exists(raw_path) and os.path.exists(jpg_path)):
            continue
        try:
            neutral_grid = load_neutral_render(raw_path, max_dim=GRID_MAX_DIM)
            neutral_confirm = load_neutral_render(raw_path, max_dim=CONFIRM_MAX_DIM)
        except Exception as e:
            print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 디코드 실패: {e}", flush=True)
            continue
        target_img = cv2.imread(jpg_path)
        if target_img is None or not is_image_array_usable(target_img):
            continue
        target_grid = load_target_linear(jpg_path, neutral_grid.shape[:2])
        target_confirm = load_target_linear(jpg_path, neutral_confirm.shape[:2])
        pairs.append(dict(name=r['raw_file'], neutral_grid=neutral_grid, target_grid=target_grid,
                           neutral_confirm=neutral_confirm, target_confirm=target_confirm))
        print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 등록", flush=True)

    n = len(pairs)
    print(f"\n사용 가능한 페어: {n}개", flush=True)

    print(f"\n{len(COMBOS)}개 조합 x {n}쌍 - ΔE00 행렬 계산중(저해상도)...", flush=True)
    de00 = np.zeros((len(COMBOS), n))
    for ci, (tl, ss, wp) in enumerate(COMBOS):
        for pi, p in enumerate(pairs):
            out = apply_population_fit_look(p['neutral_grid'], tl, ss, wp)
            de00[ci, pi] = mean_delta_e(bgr_u8_to_linear(out), p['target_grid'])
        if ci % 20 == 0:
            print(f"  콤보 {ci}/{len(COMBOS)}", flush=True)

    old_des = []
    for p in pairs:
        out = apply_population_fit_look(p['neutral_confirm'], CUR_TOE_LIFT, CUR_SHOULDER_START,
                                         CUR_WHITE_POINT)
        old_des.append(mean_delta_e(bgr_u8_to_linear(out), p['target_confirm']))
    old_des = np.array(old_des)

    print(f"\n=== LOO 검증({n}폴드, 선택은 저해상도 / 평가는 고해상도) ===", flush=True)
    loo_des = []
    chosen_counts = {}
    for i in range(n):
        train_mask = np.ones(n, dtype=bool)
        train_mask[i] = False
        best_ci = int(np.argmin(de00[:, train_mask].mean(axis=1)))
        chosen_counts[COMBOS[best_ci]] = chosen_counts.get(COMBOS[best_ci], 0) + 1
        tl, ss, wp = COMBOS[best_ci]
        out = apply_population_fit_look(pairs[i]['neutral_confirm'], tl, ss, wp)
        de = mean_delta_e(bgr_u8_to_linear(out), pairs[i]['target_confirm'])
        loo_des.append(de)
        print(f"  [{i+1}/{n}] {pairs[i]['name']} ΔE00={de:.3f} (old={old_des[i]:.3f})", flush=True)

    loo_des = np.array(loo_des)
    diff = old_des - loo_des
    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())
    mean_old, mean_new = float(old_des.mean()), float(loo_des.mean())
    improvement_pct = (mean_old - mean_new) / mean_old * 100.0

    rng = np.random.RandomState(0)
    boot = np.empty(20000)
    for i in range(20000):
        idx = rng.randint(0, n, n)
        boot[i] = diff[idx].mean()
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
    p_value = _sign_test_p(wins, losses)

    print(f"\n=== {model}: LOO ΔE00 그리드서치 vs 기존(population-fit) (n={n}) ===")
    print(f"평균 기존 ΔE00={mean_old:.3f}  평균 LOO ΔE00={mean_new:.3f}  개선폭={improvement_pct:+.2f}%")
    print(f"승/패={wins}/{losses}  부호검정 p={p_value:.4f}")
    print(f"부트스트랩 95% CI(평균차)=[{ci_lo:+.3f}, {ci_hi:+.3f}]")
    if ci_lo <= 0 <= ci_hi:
        print("판정: 보류 (CI가 0 포함)")
    else:
        print(f"판정: {'LOO 그리드서치 우세' if improvement_pct > 0 else '기존 우세'}")

    print("\n폴드별 선택 조합 상위:")
    for combo, cnt in sorted(chosen_counts.items(), key=lambda kv: -kv[1])[:5]:
        print(f"  {cnt:3d}/{n}  toe_lift={combo[0]}, shoulder_start={combo[1]}, white_point={combo[2]}")


if __name__ == "__main__":
    main()
