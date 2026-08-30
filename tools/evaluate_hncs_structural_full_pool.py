"""
tools/evaluate_hncs_structural.py의 94쌍(dpreview 클린, 4세대) 재검증이
"방향은 양수지만 CI가 여전히 0을 포함"으로 보류됐던 걸, 이번 세션에
`tools.calibrate.collect_local_pairs()`(2026-08 dedup 수정 후)로 모인
전체 로컬 하셀블라드 raw+jpeg 풀(365쌍, 6세대 - 이전 94쌍의 약 4배)로
다시 확인한다(사용자 지시 - "표본도 커져서 가능할듯"). 방법론은
evaluate_hncs_structural.py와 동일(하드클러스터 vs 블렌딩 vs
apply_hncs(), 필름커브 고정, 5-fold CV, 부호검정+부트스트랩 CI) -
데이터 로더만 `/Users/songjiun/Documents/raw pair`(이번 세션 로컬에
없음) 대신 `datasets/hasselblad/contributed/*/`에서 읽도록 교체.
chroma 그리드는 계산량 관리를 위해 1024->256(16x16)으로 축소(표본이
4배 늘어난 만큼 폴드당 학습 비용이 커져서 그리드는 줄여 총량 유지).

  python3 -m tools.evaluate_hncs_structural_full_pool
"""
import itertools
import math
import os
import subprocess
import sys
import time
import json

import colour
import cv2
import numpy as np
import rawpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.hasselblad import apply_hncs
from core.curve import film_curve
from tools.calibrate import collect_local_pairs

CLUSTER_THRESHOLD_R_OVER_B = 0.9
DOWNSAMPLE_MAX_DIM = 512
GRID_DOWNSAMPLE_MAX_DIM = 160

SAT_MULT_GRID = np.linspace(0.80, 1.20, 16)
HUE_SHIFT_GRID = np.linspace(-8.0, 8.0, 16)
CHROMA_COMBOS = list(itertools.product(SAT_MULT_GRID, HUE_SHIFT_GRID))  # 256개

FILM_CURVE_TOE_LIFT = 0.005
FILM_CURVE_SHOULDER_START = 0.5
FILM_CURVE_WHITE_POINT = 1.0

N_FOLDS = 5

_KNOWN_BAD_RAW_FILES = {"4589763049.3fr"}


def read_as_shot_neutral(path):
    out = subprocess.run(["exiftool", "-json", "-AsShotNeutral", path],
                          capture_output=True, text=True, timeout=30)
    data = json.loads(out.stdout) if out.stdout.strip() else [{}]
    raw_value = (data[0] if data else {}).get("AsShotNeutral")
    if not raw_value:
        return None
    parts = str(raw_value).replace(",", " ").split()
    try:
        values = [float(p) for p in parts]
    except ValueError:
        return None
    return np.array(values[:3], dtype=np.float64) if len(values) >= 3 else None


def decode_raw_native(raw_path, max_dim=DOWNSAMPLE_MAX_DIM):
    with rawpy.imread(raw_path) as raw:
        rgb16 = raw.postprocess(
            use_camera_wb=False, use_auto_wb=False, user_wb=[1.0, 1.0, 1.0, 1.0],
            no_auto_bright=True, output_bps=16, output_color=rawpy.ColorSpace.raw,
            gamma=(1, 1), half_size=True,
        )
    h, w = rgb16.shape[:2]
    scale = max_dim / max(h, w)
    if scale < 1:
        rgb16 = cv2.resize(rgb16, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return rgb16.astype(np.float64) / 65535.0


def decode_raw_libraw(raw_path, max_dim=DOWNSAMPLE_MAX_DIM):
    with rawpy.imread(raw_path) as raw:
        rgb16 = raw.postprocess(
            use_camera_wb=True, no_auto_bright=True, output_bps=16,
            output_color=rawpy.ColorSpace.sRGB, gamma=(1, 1), half_size=True,
        )
    h, w = rgb16.shape[:2]
    scale = max_dim / max(h, w)
    if scale < 1:
        rgb16 = cv2.resize(rgb16, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return rgb16.astype(np.float64) / 65535.0


def decode_and_white_balance(raw_path, max_dim=DOWNSAMPLE_MAX_DIM):
    native_rgb = decode_raw_native(raw_path, max_dim)
    asn = read_as_shot_neutral(raw_path)
    if asn is None:
        raise ValueError(f"AsShotNeutral 없음: {raw_path}")
    return native_rgb / asn


def classify_illuminant_cluster(as_shot_neutral, threshold=CLUSTER_THRESHOLD_R_OVER_B):
    r_over_b = as_shot_neutral[0] / as_shot_neutral[2]
    return "cluster_a" if r_over_b < threshold else "cluster_b"


def fit_color_matrix(sources, targets, ridge=1.0):
    feats = [s.reshape(-1, 3) for s in sources]
    X = np.concatenate(feats, axis=0)
    Y = np.concatenate([t.reshape(-1, 3) for t in targets], axis=0)
    if ridge == 0.0:
        matrix, _, _, _ = np.linalg.lstsq(X, Y, rcond=None)
    else:
        k = X.shape[1]
        matrix = np.linalg.solve(X.T @ X + ridge * np.eye(k), X.T @ Y)
    return matrix


def apply_color_matrix(rgb_linear, matrix):
    return np.clip(rgb_linear @ matrix, 0.0, None)


def apply_chroma_lut(img_rgb, sat_mult, hue_shift_deg):
    clipped = np.clip(img_rgb, 0.0, 1.0).astype(np.float32)
    hsv = cv2.cvtColor(clipped, cv2.COLOR_RGB2HSV)
    hsv[..., 0] = (hsv[..., 0] + hue_shift_deg) % 360.0
    hsv[..., 1] = np.clip(hsv[..., 1] * sat_mult, 0.0, 1.0)
    out = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
    return np.clip(out, 0.0, 1.0).astype(np.float64)


def shared_film_curve(rgb_linear):
    return film_curve(np.clip(rgb_linear, 0.0, 1.0), toe_lift=FILM_CURVE_TOE_LIFT,
                       shoulder_start=FILM_CURVE_SHOULDER_START,
                       white_point=FILM_CURVE_WHITE_POINT)


def load_image_linear(path, resize_to):
    bgr = cv2.imread(path)
    if bgr is None:
        raise FileNotFoundError(path)
    bgr = cv2.resize(bgr, (resize_to[1], resize_to[0]), interpolation=cv2.INTER_AREA)
    rgb = bgr[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def mean_delta_e(rgb_linear_a, rgb_linear_b):
    from skimage.color import rgb2lab, deltaE_ciede2000
    a = colour.cctf_encoding(np.clip(rgb_linear_a, 0.0, 1.0), function="sRGB")
    b = colour.cctf_encoding(np.clip(rgb_linear_b, 0.0, 1.0), function="sRGB")
    return float(np.mean(deltaE_ciede2000(rgb2lab(a), rgb2lab(b))))


def compute_blend_weight_rb(as_shot_neutral, rb_min, rb_max):
    r_over_b = as_shot_neutral[0] / as_shot_neutral[2]
    if rb_max <= rb_min:
        return 0.5
    return (r_over_b - rb_min) / (rb_max - rb_min)


_PAIR_CACHE = {}
_BASELINE_CACHE = {}
_GRID_CACHE = {}


def load_pairs():
    """tools.calibrate.collect_local_pairs() (dedup 적용됨, 2026-08) - 챠트 프레임
    제외, AsShotNeutral 못 읽는 페어 제외. 공식 13쌍은 별도 raw_calib_cache
    구조라 이 로더 범위 밖 - 기여 365쌍만으로도 이전 94쌍의 약 4배."""
    pairs = []
    for p in collect_local_pairs():
        if p["scene_type"] == "chart":
            continue
        if os.path.basename(p["raw_path"]) in _KNOWN_BAD_RAW_FILES:
            continue
        asn = read_as_shot_neutral(p["raw_path"])
        if asn is None:
            continue
        pairs.append(dict(name=p["filename"], model=p["generation"], raw_path=p["raw_path"],
                           target_path=p["jpeg_path"], as_shot_neutral=asn,
                           cluster=classify_illuminant_cluster(asn), r_over_b=asn[0] / asn[2]))
    return pairs


def pair_data(p):
    if p["name"] not in _PAIR_CACHE:
        wb_rgb = decode_and_white_balance(p["raw_path"])
        target = load_image_linear(p["target_path"], wb_rgb.shape[:2])
        _PAIR_CACHE[p["name"]] = (wb_rgb, target)
    return _PAIR_CACHE[p["name"]]


def pair_grid_data(p):
    if p["name"] not in _GRID_CACHE:
        wb_rgb = decode_and_white_balance(p["raw_path"], max_dim=GRID_DOWNSAMPLE_MAX_DIM)
        target = load_image_linear(p["target_path"], wb_rgb.shape[:2])
        _GRID_CACHE[p["name"]] = (wb_rgb, target)
    return _GRID_CACHE[p["name"]]


def baseline_data(p):
    if p["name"] not in _BASELINE_CACHE:
        baseline = decode_raw_libraw(p["raw_path"])
        target = load_image_linear(p["target_path"], baseline.shape[:2])
        _BASELINE_CACHE[p["name"]] = (baseline, target)
    return _BASELINE_CACHE[p["name"]]


def apply_hncs_delta_e(p):
    baseline, target = baseline_data(p)
    encoded = colour.cctf_encoding(np.clip(baseline, 0.0, 1.0), function="sRGB")
    u8_bgr = (np.clip(encoded, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)[:, :, ::-1]
    result_bgr = apply_hncs(u8_bgr)
    result_linear = colour.cctf_decoding(result_bgr[:, :, ::-1].astype(np.float64) / 255.0, function="sRGB")
    return mean_delta_e(result_linear, target)


def fit_matrices(train_pairs):
    by_cluster = {}
    for cluster in ("cluster_a", "cluster_b"):
        cp = [p for p in train_pairs if p["cluster"] == cluster]
        if not cp:
            continue
        sources = [pair_data(p)[0] for p in cp]
        targets = [pair_data(p)[1] for p in cp]
        by_cluster[cluster] = fit_color_matrix(sources, targets, ridge=1.0)
    return by_cluster


def fit_chroma_lut_grid(train_pairs, matrices):
    by_cluster = {}
    for cluster, matrix in matrices.items():
        cp = [p for p in train_pairs if p["cluster"] == cluster]
        if not cp:
            continue
        matrixed_hsv, targets = [], []
        for p in cp:
            wb_rgb, target = pair_grid_data(p)
            matrixed = apply_color_matrix(wb_rgb, matrix)
            clipped = np.clip(matrixed, 0.0, 1.0).astype(np.float32)
            hsv = cv2.cvtColor(clipped, cv2.COLOR_RGB2HSV)
            matrixed_hsv.append(hsv)
            targets.append(target)

        best_params, best_de = (1.0, 0.0), float("inf")
        for sat_mult, hue_shift_deg in CHROMA_COMBOS:
            des = []
            for hsv, target in zip(matrixed_hsv, targets):
                hsv2 = hsv.copy()
                hsv2[..., 0] = (hsv2[..., 0] + hue_shift_deg) % 360.0
                hsv2[..., 1] = np.clip(hsv2[..., 1] * sat_mult, 0.0, 1.0)
                rgb = cv2.cvtColor(hsv2, cv2.COLOR_HSV2RGB)
                chroma_applied = np.clip(rgb, 0.0, 1.0).astype(np.float64)
                result = shared_film_curve(chroma_applied)
                des.append(mean_delta_e(result, target))
            mean_de = float(np.mean(des))
            if mean_de < best_de:
                best_de, best_params = mean_de, (float(sat_mult), float(hue_shift_deg))
        by_cluster[cluster] = best_params
    return by_cluster


def structural_hard_delta_e(test_pair, matrices, chroma_params):
    wb_rgb, target = pair_data(test_pair)
    cluster = test_pair["cluster"]
    if cluster not in matrices:
        cluster = "cluster_a" if "cluster_a" in matrices else "cluster_b"
    matrixed = apply_color_matrix(wb_rgb, matrices[cluster])
    sat_mult, hue_shift_deg = chroma_params[cluster]
    chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
    result = shared_film_curve(chroma_applied)
    return mean_delta_e(result, target)


def structural_blend_delta_e(test_pair, matrix_a, matrix_b, chroma_a, chroma_b, rb_min, rb_max):
    wb_rgb, target = pair_data(test_pair)
    weight = compute_blend_weight_rb(test_pair["as_shot_neutral"], rb_min, rb_max)
    blended_matrix = (1.0 - weight) * matrix_a + weight * matrix_b
    matrixed = apply_color_matrix(wb_rgb, blended_matrix)
    sat_a, hue_a = chroma_a
    sat_b, hue_b = chroma_b
    sat_mult = (1.0 - weight) * sat_a + weight * sat_b
    hue_shift_deg = (1.0 - weight) * hue_a + weight * hue_b
    chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
    result = shared_film_curve(chroma_applied)
    return mean_delta_e(result, target)


def make_folds(pairs, n_folds, seed=0):
    rng = np.random.RandomState(seed)
    idx = np.arange(len(pairs))
    rng.shuffle(idx)
    return np.array_split(idx, n_folds)


def run_kfold():
    pairs = load_pairs()
    from collections import Counter
    print(f"페어 {len(pairs)}개, 클러스터 분포: {Counter(p['cluster'] for p in pairs)}", flush=True)
    print(f"세대 분포: {Counter(p['model'] for p in pairs)}", flush=True)
    print(f"chroma 그리드: {len(CHROMA_COMBOS)}콤보, {N_FOLDS}-fold CV", flush=True)

    folds = make_folds(pairs, N_FOLDS)
    per_fold_hard, per_fold_blend, per_fold_hncs = [], [], []
    t0 = time.time()

    for fi, test_idx in enumerate(folds):
        train_idx = np.concatenate([folds[j] for j in range(N_FOLDS) if j != fi])
        train = [pairs[i] for i in train_idx]
        test = [pairs[i] for i in test_idx]

        matrices = fit_matrices(train)
        chroma_params = fit_chroma_lut_grid(train, matrices)

        matrix_a = matrices.get("cluster_a", matrices.get("cluster_b"))
        matrix_b = matrices.get("cluster_b", matrices.get("cluster_a"))
        chroma_a = chroma_params.get("cluster_a", chroma_params.get("cluster_b"))
        chroma_b = chroma_params.get("cluster_b", chroma_params.get("cluster_a"))
        train_rb = [p["r_over_b"] for p in train]
        rb_min, rb_max = min(train_rb), max(train_rb)

        for p in test:
            de_hard = structural_hard_delta_e(p, matrices, chroma_params)
            de_blend = structural_blend_delta_e(p, matrix_a, matrix_b, chroma_a, chroma_b, rb_min, rb_max)
            de_hncs = apply_hncs_delta_e(p)
            per_fold_hard.append((p["name"], p["cluster"], de_hard))
            per_fold_blend.append((p["name"], p["cluster"], de_blend))
            per_fold_hncs.append((p["name"], p["cluster"], de_hncs))

        elapsed = time.time() - t0
        print(f"  fold {fi+1}/{N_FOLDS} 완료 (test n={len(test)}, train n={len(train)}, "
              f"{elapsed:.0f}s경과)", flush=True)

    return per_fold_hard, per_fold_blend, per_fold_hncs


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def summarize(hncs_des, other_des, label, n_bootstrap=20000, seed=0):
    hncs = np.array(hncs_des)
    other = np.array(other_des)
    diff = hncs - other
    n = len(diff)
    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())
    mean_hncs, mean_other = float(hncs.mean()), float(other.mean())
    improvement_pct = (mean_hncs - mean_other) / mean_hncs * 100.0

    rng = np.random.RandomState(seed)
    boot = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        idx = rng.randint(0, n, n)
        boot[i] = diff[idx].mean()
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])

    p = _sign_test_p(wins, losses)
    inconclusive = ci_lo <= 0 <= ci_hi
    print(f"\n=== {label} vs apply_hncs (n={n}) ===")
    print(f"평균 apply_hncs ΔE00={mean_hncs:.3f}  평균 {label} ΔE00={mean_other:.3f}  "
          f"개선폭={improvement_pct:+.2f}%")
    print(f"승/패={wins}/{losses}  부호검정 p={p:.4f}")
    print(f"부트스트랩 95% CI(평균차)=[{ci_lo:+.3f}, {ci_hi:+.3f}]")
    print("판정: 보류 (CI가 0 포함)" if inconclusive else
          f"판정: {'구조실험 우세' if improvement_pct > 0 else 'apply_hncs 우세'}")


def main():
    per_fold_hard, per_fold_blend, per_fold_hncs = run_kfold()

    hncs_des = [row[2] for row in per_fold_hncs]
    hard_des = [row[2] for row in per_fold_hard]
    blend_des = [row[2] for row in per_fold_blend]

    print("\n=== 표본별 상세 ===")
    for i in range(len(hncs_des)):
        print(f"  {per_fold_hncs[i][0]:30s} ({per_fold_hncs[i][1]:10s})  "
              f"hncs={hncs_des[i]:6.3f}  hard={hard_des[i]:6.3f}  blend={blend_des[i]:6.3f}")

    summarize(hncs_des, hard_des, "하드클러스터")
    summarize(hncs_des, blend_des, "블렌딩")
    summarize(hard_des, blend_des, "블렌딩(vs 하드클러스터)")


if __name__ == "__main__":
    main()
