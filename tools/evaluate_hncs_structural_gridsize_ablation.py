"""`tools/evaluate_hncs_structural.py`(2026-09-03, n=389, 32x32=1024
chroma 그리드)의 하드클러스터 vs 블렌딩 직접 페어드 비교가 "판정
보류"(-0.14%, CI[-0.039,+0.009])였는데, 같은 데이터를 `_full_pool.py`
(364쌍, 16x16=256 그리드)로 돌렸을 땐 하드클러스터가 유의하게 우세
(-0.50%, CI[-0.078,-0.036], p<0.0001)했다 - 두 실행이 그리드 크기
말고도 표본 수(389 vs 364)가 달라서 원인이 그리드인지 표본인지
가려지지 않았다(`docs/hncs_structural_research.md` "재검증 4" 참고).

이 스크립트는 그 변수를 하나만 바꿔서 격리한다: 로더/폴드 분할
(`load_pairs()`/`make_folds(seed=0)`, evaluate_hncs_structural.py와
100% 동일 코드 - tools/CLAUDE.md 관례상 import 대신 복붙)는 그대로
두고 CHROMA_COMBOS만 `_full_pool.py`와 같은 16x16=256으로 낮춘다.
4클러스터 변형은 이 질문과 무관해서 아예 뺐다(계산량 절감 - 원래
스크립트는 폴드당 하드(2클러스터)+4클러스터 총 6번의 콤보서치를
했는데 이건 2번만 한다).

  python3 -m tools.evaluate_hncs_structural_gridsize_ablation
"""
import concurrent.futures
import csv
import glob
import itertools
import math
import os
import sys
import time
import subprocess
import json

import colour
import cv2
import numpy as np
import rawpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.hasselblad import apply_hncs
from core.curve import film_curve

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFFICIAL_CSV = os.path.join(_ROOT, "datasets", "hasselblad", "hasselblad_raw_jpeg_pairs.csv")
OFFICIAL_CACHE_DIR = os.path.join(_ROOT, "raw_calib_cache")

CLUSTER_THRESHOLD_R_OVER_B = 0.9
DOWNSAMPLE_MAX_DIM = 512
GRID_DOWNSAMPLE_MAX_DIM = 160

# 유일한 변수: 32x32=1024 -> 16x16=256 (evaluate_hncs_structural_full_pool.py와 동일)
SAT_MULT_GRID = np.linspace(0.80, 1.20, 16)
HUE_SHIFT_GRID = np.linspace(-8.0, 8.0, 16)
CHROMA_COMBOS = list(itertools.product(SAT_MULT_GRID, HUE_SHIFT_GRID))  # 256개

FILM_CURVE_TOE_LIFT = 0.005
FILM_CURVE_SHOULDER_START = 0.5
FILM_CURVE_WHITE_POINT = 1.0

N_FOLDS = 5
N_WORKERS = max(1, min(3, (os.cpu_count() or 2) - 2))


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
    lab_a = rgb2lab(a)
    lab_b = rgb2lab(b)
    return float(np.mean(deltaE_ciede2000(lab_a, lab_b)))


def compute_blend_weight_rb(as_shot_neutral, rb_min, rb_max):
    r_over_b = as_shot_neutral[0] / as_shot_neutral[2]
    if rb_max <= rb_min:
        return 0.5
    return (r_over_b - rb_min) / (rb_max - rb_min)


_PAIR_CACHE = {}
_BASELINE_CACHE = {}
_GRID_CACHE = {}

_KNOWN_BAD_RAW_FILES = {"4589763049.3fr"}


def _load_official_pairs():
    pairs = []
    with open(OFFICIAL_CSV, newline="") as f:
        for row in csv.DictReader(f):
            name = os.path.basename(row["jpeg_url"])
            matches = [m for m in glob.glob(os.path.join(OFFICIAL_CACHE_DIR, name + ".*"))
                       if not m.endswith(".target.jpg")]
            if len(matches) != 1:
                raise FileNotFoundError(f"raw for {name}: expected 1 match, got {matches}")
            pairs.append({"name": name, "raw_path": matches[0],
                           "target_path": os.path.join(OFFICIAL_CACHE_DIR, name + ".target.jpg")})
    return pairs


def load_pairs():
    """evaluate_hncs_structural.py의 load_pairs()와 100% 동일 - 이
    스크립트가 격리하려는 유일한 변수는 CHROMA_COMBOS 크기이므로,
    페어 풀/순서/폴드분할이 정확히 같아야 그리드 크기만의 효과를
    볼 수 있다."""
    from tools.calibrate import collect_local_pairs
    raw_pairs = _load_official_pairs()
    for p in collect_local_pairs():
        raw_pairs.append({"name": p["filename"], "raw_path": p["raw_path"], "target_path": p["jpeg_path"]})

    pairs = []
    n_decode_fail = 0
    for p in raw_pairs:
        if os.path.basename(p["raw_path"]) in _KNOWN_BAD_RAW_FILES:
            continue
        asn = read_as_shot_neutral(p["raw_path"])
        if asn is None:
            continue
        try:
            decode_raw_native(p["raw_path"], max_dim=GRID_DOWNSAMPLE_MAX_DIM)
        except Exception as e:
            n_decode_fail += 1
            print(f"  프리플라이트 디코드 실패, 제외: {os.path.basename(p['raw_path'])} ({e})", flush=True)
            continue
        pairs.append(dict(name=p["name"], model=None, raw_path=p["raw_path"],
                           target_path=p["target_path"],
                           as_shot_neutral=asn, cluster=classify_illuminant_cluster(asn),
                           r_over_b=asn[0] / asn[2]))
    if n_decode_fail:
        print(f"프리플라이트에서 디코드 실패로 제외된 페어: {n_decode_fail}개", flush=True)
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
        matrixed_hsv = []
        targets = []
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
        cluster = next(iter(matrices))
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
    folds = np.array_split(idx, n_folds)
    return folds


def _run_one_fold(fi, pairs, train_idx, test_idx):
    train = [pairs[i] for i in train_idx]
    test = [pairs[i] for i in test_idx]

    matrices = fit_matrices(train)
    chroma_params = fit_chroma_lut_grid(train, matrices)

    matrix_a = matrices.get("cluster_a", matrices.get("cluster_b"))
    matrix_b = matrices.get("cluster_b", matrices.get("cluster_a"))
    chroma_a = chroma_params.get("cluster_a", chroma_params.get("cluster_b"))
    chroma_b = chroma_params.get("cluster_b", chroma_params.get("cluster_a"))
    train_rb_all = [p["r_over_b"] for p in train]
    rb_min, rb_max = min(train_rb_all), max(train_rb_all)

    hard, blend, hncs = [], [], []
    for p in test:
        de_hard = structural_hard_delta_e(p, matrices, chroma_params)
        de_blend = structural_blend_delta_e(p, matrix_a, matrix_b, chroma_a, chroma_b, rb_min, rb_max)
        de_hncs = apply_hncs_delta_e(p)
        hard.append((p["name"], p["cluster"], de_hard))
        blend.append((p["name"], p["cluster"], de_blend))
        hncs.append((p["name"], p["cluster"], de_hncs))
    return fi, len(train), len(test), hard, blend, hncs


def run_kfold():
    pairs = load_pairs()
    from collections import Counter
    print(f"페어 {len(pairs)}개, 클러스터 분포: {Counter(p['cluster'] for p in pairs)}", flush=True)
    print(f"chroma 그리드: {len(CHROMA_COMBOS)}콤보, {N_FOLDS}-fold CV, {N_WORKERS}워커", flush=True)

    folds = make_folds(pairs, N_FOLDS)
    t0 = time.time()

    fold_results = {}
    with concurrent.futures.ProcessPoolExecutor(max_workers=N_WORKERS) as ex:
        futures = []
        for fi, test_idx in enumerate(folds):
            train_idx = np.concatenate([folds[j] for j in range(N_FOLDS) if j != fi])
            futures.append(ex.submit(_run_one_fold, fi, pairs, train_idx, test_idx))
        for fut in concurrent.futures.as_completed(futures):
            fi, n_train, n_test, hard, blend, hncs = fut.result()
            fold_results[fi] = (hard, blend, hncs)
            elapsed = time.time() - t0
            print(f"  fold {fi+1}/{N_FOLDS} 완료 (test n={n_test}, train n={n_train}, "
                  f"{elapsed:.0f}s경과)", flush=True)

    per_fold_hard, per_fold_blend, per_fold_hncs = [], [], []
    for fi in range(N_FOLDS):
        hard, blend, hncs = fold_results[fi]
        per_fold_hard.extend(hard)
        per_fold_blend.extend(blend)
        per_fold_hncs.extend(hncs)

    return per_fold_hard, per_fold_blend, per_fold_hncs


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def summarize(hncs_des, other_des, label, n_bootstrap=20000, seed=0, baseline_label="apply_hncs"):
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
    print(f"\n=== {label} vs {baseline_label} (n={n}) ===")
    print(f"평균 {baseline_label} ΔE00={mean_hncs:.3f}  평균 {label} ΔE00={mean_other:.3f}  "
          f"개선폭={improvement_pct:+.2f}%")
    print(f"승/패={wins}/{losses}  부호검정 p={p:.4f}")
    print(f"부트스트랩 95% CI(평균차)=[{ci_lo:+.3f}, {ci_hi:+.3f}]")
    print("판정: 보류 (CI가 0 포함)" if inconclusive else
          f"판정: {label + ' 우세' if improvement_pct > 0 else baseline_label + ' 우세'}")


def main():
    per_fold_hard, per_fold_blend, per_fold_hncs = run_kfold()

    hncs_des = [row[2] for row in per_fold_hncs]
    hard_des = [row[2] for row in per_fold_hard]
    blend_des = [row[2] for row in per_fold_blend]

    print("\n=== 표본별 상세 ===")
    for i in range(len(hncs_des)):
        print(f"  {per_fold_hncs[i][0]:20s} ({per_fold_hncs[i][1]:10s})  "
              f"hncs={hncs_des[i]:6.3f}  hard2={hard_des[i]:6.3f}  blend={blend_des[i]:6.3f}")

    summarize(hncs_des, hard_des, "2클러스터하드")
    summarize(hncs_des, blend_des, "블렌딩")
    summarize(hard_des, blend_des, "블렌딩", baseline_label="2클러스터하드")


if __name__ == "__main__":
    main()
