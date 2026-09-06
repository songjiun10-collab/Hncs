"""
HNCS 실제 4단계 구조(조명별 3x3 매트릭스 -> 조명별 chroma LUT -> 공유
필름커브)를 미러링한 연구 실험 - apply_hncs()(brands/hasselblad.py)와
비교. origin 저장소(GitHub songjiun10-collab/Hncs)의
hybrid_engine/research/hncs_structural.py + tools/evaluate_hncs_structural.py
설계를 이 로컬 체크아웃(hybrid_engine 없음)에 맞게 독립 스크립트로
재현한다. 원본은 13쌍(X1D 전용) + 7x7=49 chroma 그리드 + 13-fold LOO,
그 다음 버전은 dpreview 클린 95쌍(4세대) + 32x32=1024 chroma 그리드 +
5-fold CV였다.

**2026-09-02 재실행**: 그 95쌍 버전이 읽던 RAW_DIR
("/Users/songjiun/Documents/raw pair")이 이 머신엔 없어서(실행 확인)
이 스크립트는 이번 세션 전까지 아예 못 돌아가는 상태였다. 공식
13쌍(`raw_calib_cache/`) + `datasets/hasselblad/contributed/*/manifest.csv`
전체(디스크에 실제 존재하는 파일만, `tools.calibrate.collect_local_pairs()`)로
데이터 소스를 바꿔서 총 390쌍(실행 확인)으로 확장했다 - 사용자 지시
"데이터도 커졌는데 구조데로 해보면 안됨?" -> "ㅇㅇ". 동시에 하드
클러스터를 2개(기존)뿐 아니라 **4개**로도 돌린다 - 외부 조사
(`docs/hncs_external_sources_analysis.md` 1-2절, 포럼 스레드)가
말하는 "실제 최소 4개 조명"에 표본이 이제 도달했는지 보려는 것.
4클러스터 경계는 각 폴드의 train 데이터 R/B 비율 25/50/75 분위수로
리키지 없이 계산(블렌딩의 rb_min/rb_max와 같은 원칙).

3가지 방식 다 실행:
  - 하드 클러스터 2개(원본과 동일, AsShotNeutral R/B 비율 임계값 0.9)
  - 하드 클러스터 4개(신규, train 분위수 기반 경계)
  - 연속 블렌딩(원본의 apply_hncs_structural_blend - R/B를 fold의
    train 데이터 관측 범위로 정규화한 가중치로 두 앵커를 블렌딩)

필름커브 단계는 원본과 같은 이유로 피팅하지 않고 apply_hncs()의 현재
기본값(v13: toe_lift=0.005, shoulder_start=0.5, white_point=1.0)으로
고정 - 톤 단계를 통제변수로 묶어 매트릭스/chroma LUT 단계만 비교한다.
apply_hncs()는 이 실험에서 아무것도 수정하지 않는다(항상 보호 대상).

  python3 -m tools.evaluate_hncs_structural
"""
import concurrent.futures
import csv
import glob
import itertools
import math
import os
import sys
import time

import colour
import cv2
import numpy as np
import rawpy
import subprocess
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.hasselblad import apply_hncs
from core.curve import film_curve

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFFICIAL_CSV = os.path.join(_ROOT, "datasets", "hasselblad", "hasselblad_raw_jpeg_pairs.csv")
OFFICIAL_CACHE_DIR = os.path.join(_ROOT, "raw_calib_cache")

CLUSTER_THRESHOLD_R_OVER_B = 0.9
DOWNSAMPLE_MAX_DIM = 512
GRID_DOWNSAMPLE_MAX_DIM = 160  # chroma 그리드서치 전용 - 1024콤보 x 폴드라 더 작게

SAT_MULT_GRID = np.linspace(0.80, 1.20, 32)
HUE_SHIFT_GRID = np.linspace(-8.0, 8.0, 32)
CHROMA_COMBOS = list(itertools.product(SAT_MULT_GRID, HUE_SHIFT_GRID))  # 1024개

FILM_CURVE_TOE_LIFT = 0.005
FILM_CURVE_SHOULDER_START = 0.5
FILM_CURVE_WHITE_POINT = 1.0

N_FOLDS = 5
# 폴드 단위 프로세스풀 병렬화(2026-09-02, 390쌍 확장 후 추가) -
# evaluate_hncs_blend.py의 74쌍 LOO(148폴드, 3워커 4h22m 실측)와 같은
# 이유: 단일 스레드로는 폴드당 훈련쌍이 74->311로 늘어난 만큼 그리드서치가
# 몇 시간대로 늘어난다(첫 실행에서 확인 후 병렬화 추가).
#
# 워커 5개로 처음 돌렸다가 스왑이 6->8GB로 늘면서 93.6%(7.67/8.19GB)까지
# 찬 걸 실측하고 죽였다 - 워커당 pair_data 캐시(311쌍 x 512px x
# float64 ~= 1.6GB, evaluate_hncs_blend.py가 74쌍 LOO 때 "워커당
# ~1.3GB라 3워커로 캡"이라고 적어둔 것과 같은 원인)가 5배로 쌓인
# 탓이다. 같은 이유로 evaluate_hncs_blend.py도 3으로 캡했던 전례를
# 그대로 따른다 - 폴드가 5개라 5워커가 이상적이지만 이 머신에서는
# 메모리가 먼저 한계에 부딪힌다.
N_WORKERS = max(1, min(3, (os.cpu_count() or 2) - 2))


# ============================================================
# 원본 hybrid_engine 모듈들의 독립 재구현 (self-contained)
# ============================================================
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
    """WB/컬러매트릭스 둘 다 우회 - 카메라 네이티브 linear RGB."""
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
    """apply_hncs() 공정비교용 baseline - camera_wb + libraw 자체
    매트릭스(sRGB) 적용, pure linear."""
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


def classify_cluster_k(r_over_b, boundaries):
    """boundaries(오름차순 컷포인트 k-1개)로 r_over_b를 "cluster0".."k-1"로
    분류. 4클러스터 실험(2026-09-02)에서 fold별 train 데이터 R/B
    25/50/75 분위수를 boundaries로 넘겨 씀 - 리키지 없이 폴드마다
    다시 계산."""
    idx = 0
    for b in boundaries:
        if r_over_b >= b:
            idx += 1
        else:
            break
    return f"cluster{idx}"


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


# ============================================================
# 데이터 로드 + 캐시
# ============================================================
_PAIR_CACHE = {}
_BASELINE_CACHE = {}
_GRID_CACHE = {}


# 이 세션의 다른 여러 실험에서도 반복 확인된 손상 파일 - raw.postprocess()가
# "Input/output error"로 죽는다(EXIF는 읽히지만 픽셀 언팩이 실패).
_KNOWN_BAD_RAW_FILES = {"4589763049.3fr"}


def _load_official_pairs():
    """evaluate_hncs_blend.py의 load_pairs()와 같은 관례(evaluate_*.py는
    형제 스크립트를 import 안 하는 컨벤션이라 복붙, tools/CLAUDE.md) -
    공식 13쌍을 raw_calib_cache/에서 읽는다."""
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
    """공식 13쌍 + datasets/hasselblad/contributed/*/manifest.csv 전체
    (디스크에 실제 존재하는 파일만, tools.calibrate.collect_local_pairs()가
    파일 존재 확인까지 함) - 총 390쌍(2026-09-02 실행 확인). 이전
    버전이 읽던 MANIFEST/RAW_DIR는 이 머신에 데이터가 없어서 이
    스크립트를 아예 못 돌리는 상태였다(위 헤더 docstring 참고)."""
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
    """chroma 그리드서치 전용 초저해상도 캐시 (1024콤보 x 5폴드라 512px는 너무 느림)."""
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


# ============================================================
# 하드 클러스터 방식
# ============================================================
def fit_matrices(train_pairs, cluster_key="cluster", cluster_labels=("cluster_a", "cluster_b")):
    """cluster_key/cluster_labels 기본값은 기존 2클러스터 호출부와
    동일하게 동작 - 4클러스터 실험(2026-09-02)이 cluster_key="cluster4",
    cluster_labels=["cluster0".."cluster3"]로 같은 함수를 재사용한다."""
    by_cluster = {}
    for cluster in cluster_labels:
        cp = [p for p in train_pairs if p[cluster_key] == cluster]
        if not cp:
            continue
        sources = [pair_data(p)[0] for p in cp]
        targets = [pair_data(p)[1] for p in cp]
        by_cluster[cluster] = fit_color_matrix(sources, targets, ridge=1.0)
    return by_cluster


def fit_chroma_lut_grid(train_pairs, matrices, cluster_key="cluster"):
    """1024콤보 그리드서치 - 초저해상도 캐시로 매트릭스 적용 후 벡터화
    가능한 부분(HSV 변환)은 페어당 1회만, sat/hue 조합 루프만 반복."""
    by_cluster = {}
    for cluster, matrix in matrices.items():
        cp = [p for p in train_pairs if p[cluster_key] == cluster]
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


def structural_hard_delta_e(test_pair, matrices, chroma_params, cluster_key="cluster"):
    wb_rgb, target = pair_data(test_pair)
    cluster = test_pair[cluster_key]
    if cluster not in matrices:
        cluster = next(iter(matrices))
    matrixed = apply_color_matrix(wb_rgb, matrices[cluster])
    sat_mult, hue_shift_deg = chroma_params[cluster]
    chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
    result = shared_film_curve(chroma_applied)
    return mean_delta_e(result, target)


# ============================================================
# 블렌딩 방식
# ============================================================
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


# ============================================================
# K-fold 실행
# ============================================================
def make_folds(pairs, n_folds, seed=0):
    rng = np.random.RandomState(seed)
    idx = np.arange(len(pairs))
    rng.shuffle(idx)
    folds = np.array_split(idx, n_folds)
    return folds


def _run_one_fold(fi, pairs, train_idx, test_idx):
    """폴드 하나(훈련+테스트)를 통째로 처리 - 프로세스풀 워커 하나가 이
    함수 전체를 담당하므로 모듈 최상위 함수여야 pickle된다(spawn 방식,
    macOS 기본). 각 워커는 독립 프로세스라 _PAIR_CACHE 등 전역 캐시를
    공유하지 않는다 - 폴드끼리 훈련쌍이 78% 겹치는데도 재디코드가
    생기지만, 디코드 자체가 싸서(개당 <1초) 그리드서치 병렬화 이득이
    훨씬 크다."""
    train = [pairs[i] for i in train_idx]
    test = [pairs[i] for i in test_idx]

    matrices = fit_matrices(train)
    chroma_params = fit_chroma_lut_grid(train, matrices)

    # 4클러스터: train R/B 25/50/75 분위수를 경계로 - 리키지 없이
    # 폴드마다 새로 계산(블렌딩의 rb_min/rb_max와 같은 원칙).
    train_rb_all = [p["r_over_b"] for p in train]
    boundaries4 = np.percentile(train_rb_all, [25, 50, 75]).tolist()
    cluster4_labels = [f"cluster{i}" for i in range(4)]
    for p in train + test:
        p["cluster4"] = classify_cluster_k(p["r_over_b"], boundaries4)
    matrices4 = fit_matrices(train, cluster_key="cluster4", cluster_labels=cluster4_labels)
    chroma_params4 = fit_chroma_lut_grid(train, matrices4, cluster_key="cluster4")

    # 블렌딩용 앵커: 각 클러스터의 매트릭스/chroma를 그대로 앵커로 사용
    matrix_a = matrices.get("cluster_a", matrices.get("cluster_b"))
    matrix_b = matrices.get("cluster_b", matrices.get("cluster_a"))
    chroma_a = chroma_params.get("cluster_a", chroma_params.get("cluster_b"))
    chroma_b = chroma_params.get("cluster_b", chroma_params.get("cluster_a"))
    rb_min, rb_max = min(train_rb_all), max(train_rb_all)

    hard, hard4, blend, hncs = [], [], [], []
    for p in test:
        de_hard = structural_hard_delta_e(p, matrices, chroma_params)
        de_hard4 = structural_hard_delta_e(p, matrices4, chroma_params4, cluster_key="cluster4")
        de_blend = structural_blend_delta_e(p, matrix_a, matrix_b, chroma_a, chroma_b, rb_min, rb_max)
        de_hncs = apply_hncs_delta_e(p)
        hard.append((p["name"], p["cluster"], de_hard))
        hard4.append((p["name"], p["cluster4"], de_hard4))
        blend.append((p["name"], p["cluster"], de_blend))
        hncs.append((p["name"], p["cluster"], de_hncs))
    return fi, len(train), len(test), hard, hard4, blend, hncs


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
            fi, n_train, n_test, hard, hard4, blend, hncs = fut.result()
            fold_results[fi] = (hard, hard4, blend, hncs)
            elapsed = time.time() - t0
            print(f"  fold {fi+1}/{N_FOLDS} 완료 (test n={n_test}, train n={n_train}, "
                  f"{elapsed:.0f}s경과)", flush=True)

    per_fold_hard, per_fold_hard4, per_fold_blend, per_fold_hncs = [], [], [], []
    for fi in range(N_FOLDS):
        hard, hard4, blend, hncs = fold_results[fi]
        per_fold_hard.extend(hard)
        per_fold_hard4.extend(hard4)
        per_fold_blend.extend(blend)
        per_fold_hncs.extend(hncs)

    return per_fold_hard, per_fold_hard4, per_fold_blend, per_fold_hncs


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def summarize(hncs_des, other_des, label, n_bootstrap=20000, seed=0, baseline_label="apply_hncs"):
    """baseline_label 기본값은 원래 동작(항상 "apply_hncs") 그대로 -
    2026-09-02 4클러스터 실험에서 hard_des를 baseline으로 쓰는 두 호출
    (4클러스터 vs 2클러스터, 블렌딩 vs 2클러스터하드)이 출력에 여전히
    "vs apply_hncs"라고 찍던 라벨 버그를 고치려고 추가(계산 자체는
    항상 맞았음, 표시만 틀렸었다)."""
    hncs = np.array(hncs_des)
    other = np.array(other_des)
    diff = hncs - other  # 양수 = other(구조실험)가 더 좋음
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
    per_fold_hard, per_fold_hard4, per_fold_blend, per_fold_hncs = run_kfold()

    hncs_des = [row[2] for row in per_fold_hncs]
    hard_des = [row[2] for row in per_fold_hard]
    hard4_des = [row[2] for row in per_fold_hard4]
    blend_des = [row[2] for row in per_fold_blend]

    print("\n=== 표본별 상세 ===")
    for i in range(len(hncs_des)):
        print(f"  {per_fold_hncs[i][0]:20s} ({per_fold_hncs[i][1]:10s}/{per_fold_hard4[i][1]:9s})  "
              f"hncs={hncs_des[i]:6.3f}  hard2={hard_des[i]:6.3f}  hard4={hard4_des[i]:6.3f}  "
              f"blend={blend_des[i]:6.3f}")

    summarize(hncs_des, hard_des, "2클러스터하드")
    summarize(hncs_des, hard4_des, "4클러스터하드")
    summarize(hncs_des, blend_des, "블렌딩")
    summarize(hard_des, hard4_des, "4클러스터", baseline_label="2클러스터하드")
    summarize(hard_des, blend_des, "블렌딩", baseline_label="2클러스터하드")


if __name__ == "__main__":
    main()
