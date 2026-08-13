"""[research] 후지 raw+jpeg 페어로 hybrid_engine 캘리브레이션 - 지금까지
해셀블라드 전용이던 `calibrate_profile.py`의 범용 적합 함수
(`_find_matrix_and_recalibrate`/`coordinate_descent`)를 그대로 재사용하되,
데이터 소스만 `datasets/leica/contributed/*/manifest.csv`로 바꾼다.

`calibrate_profile.py`처럼 프로필 json에 아무것도 쓰지 않는다 - 이 스크립트는
측정만 한다. 실제로 "출시"하려면(후지용 leica.json을 hybrid_engine
프로필로 등록하는 것) 별도의, 사용자가 명시적으로 승인하는 결정이다
(hybrid_engine/CLAUDE.md: "Never touch" 대상은 아니지만, 루트 CLAUDE.md의
"실험 결과를 자동으로 출시하지 않는다" 원칙은 새 브랜드 프로필에도 그대로
적용).

  python3 -m hybrid_engine.calibrate_profile_fuji
"""
import csv
import glob
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.calibrate_profile import (
    _DEFAULT_PARAMS,
    _find_matrix_and_recalibrate,
    _mean_loss,
    _resize_max_dim,
    learn_hue_lut,
)
from hybrid_engine.core import color_matrix
from hybrid_engine.utils.io import decode_raw, load_image_linear

CALIB_MAX_DIM = 500
_FUJI_CONTRIBUTED_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datasets", "fuji", "contributed")
# 해셀블라드의 assets/luts/hasselblad_hue_learned.npy와 절대 안 겹치는
# 별도 경로 - run_hue_mode()를 그대로 부르면 그 경로에 덮어쓰므로 재사용
# 안 하고 이 파일만의 경로를 씀 (research/scratch, 커밋 대상 아님).
_FUJI_HUE_LUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "assets", "luts", "fuji_hue_learned_scratch.npy")


def _find_pairs():
    pairs = []
    for manifest_path in sorted(glob.glob(os.path.join(_FUJI_CONTRIBUTED_ROOT, "*", "manifest.csv"))):
        set_dir = os.path.dirname(manifest_path)
        with open(manifest_path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                raw_path = os.path.join(set_dir, "raw", row["filename_raw"])
                jpeg_path = os.path.join(set_dir, "jpeg", row["filename_jpeg"])
                if os.path.exists(raw_path) and os.path.exists(jpeg_path):
                    pairs.append((raw_path, jpeg_path))
    return pairs


def _load_calib_set():
    dataset = []
    pairs = _find_pairs()
    for i, (raw_path, target_path) in enumerate(pairs):
        print(f"  [{i + 1}/{len(pairs)}] 로드 중: {os.path.basename(raw_path)}", flush=True)
        try:
            linear = decode_raw(raw_path)
        except Exception as e:
            print(f"    디코드 실패, 스킵: {e}")
            continue
        linear_small = _resize_max_dim(linear, CALIB_MAX_DIM)
        camera_wb = color_matrix.extract_camera_metadata(raw_path)["camera_whitebalance"]
        target_small = load_image_linear(target_path, resize_to=linear_small.shape[:2])
        dataset.append((linear_small, camera_wb, target_small))
    return dataset


def _paired_cv_losses(dataset, fixed_overrides, n_folds=4, seed=0, n_passes=1):
    """페어별(폴드 평균 아님) ΔE00 배열 - nested CV(폴드마다 매트릭스+톤/색
    재학습, held-out은 그 폴드에서 한 번도 학습에 안 씀). summarize()의
    페어드 비교 입력으로 쓴다. dataset과 같은 순서로 반환."""
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(dataset))
    folds = np.array_split(order, n_folds)
    per_pair = np.empty(len(dataset))
    for fold_idx in folds:
        fold_idx_set = set(fold_idx.tolist())
        train_set = [d for i, d in enumerate(dataset) if i not in fold_idx_set]
        fold_params, _ = _find_matrix_and_recalibrate(
            train_set, n_passes=n_passes, fixed_overrides=fixed_overrides)
        for i in fold_idx:
            per_pair[i] = _mean_loss(fold_params, [dataset[i]])
    return per_pair


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def summarize(label_a, des_a, label_b, des_b, n_bootstrap=20000, seed=0):
    """페어드 비교 - des_b가 des_a보다 작으면(=더 좋으면) 양수 improvement.
    tools/evaluate_wb_pipeline_variants.py의 summarize()와 같은 통계
    (부트스트랩 CI, 부호검정) - evaluate_*.py는 형제 스크립트를 import하지
    않는 컨벤션이라 복붙 (hybrid_engine/CLAUDE.md)."""
    a = np.asarray(des_a, dtype=np.float64)
    b = np.asarray(des_b, dtype=np.float64)
    n = len(a)
    diff = a - b
    mean_a, mean_b = float(a.mean()), float(b.mean())
    improvement_pct = (mean_a - mean_b) / mean_a * 100.0 if mean_a else float("nan")
    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())

    rng = np.random.default_rng(seed)
    boot = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        idx = rng.integers(0, n, n)
        boot[i] = diff[idx].mean()
    ci_lo, ci_hi = (float(v) for v in np.percentile(boot, [2.5, 97.5]))
    p_value = _sign_test_p(wins, losses)
    inconclusive = ci_lo <= 0.0 <= ci_hi

    print(f"\n=== {label_a} vs {label_b} (n={n}) ===")
    print(f"평균 {label_a} ΔE00={mean_a:.3f}  평균 {label_b} ΔE00={mean_b:.3f}  "
          f"{label_b} 개선폭={improvement_pct:+.2f}%")
    print(f"승({label_b} 더 좋음)/패={wins}/{losses}  부호검정 p={p_value:.4f}")
    print(f"부트스트랩 95% CI(평균차)=[{ci_lo:+.3f}, {ci_hi:+.3f}]")
    if inconclusive:
        print("판정: 보류 (CI가 0 포함)")
    elif improvement_pct > 0:
        print(f"판정: {label_b} 우세")
    else:
        print(f"판정: {label_a} 우세")
    return dict(mean_a=mean_a, mean_b=mean_b, improvement_pct=improvement_pct,
                wins=wins, losses=losses, p_value=p_value, ci=(ci_lo, ci_hi),
                inconclusive=inconclusive)


def _hue_lut_paired_cv_losses(dataset, base_profile, n_folds=4, seed=0):
    """base_profile(이미 매트릭스+톤/색+gray_edge까지 재학습된 프로필) 위에
    hue LUT을 얹었을 때/안 얹었을 때 페어별 ΔE - k-fold nested CV(폴드마다
    학습 데이터로만 hue LUT을 새로 학습)."""
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(dataset))
    folds = np.array_split(order, n_folds)
    without_lut = np.empty(len(dataset))
    with_lut = np.empty(len(dataset))
    for fold_idx in folds:
        fold_idx_set = set(fold_idx.tolist())
        train_set = [d for i, d in enumerate(dataset) if i not in fold_idx_set]
        lut = learn_hue_lut(train_set, base_profile)
        np.save(_FUJI_HUE_LUT_PATH, lut)
        hue_profile = dict(base_profile, learned_hue_lut=_FUJI_HUE_LUT_PATH)
        for i in fold_idx:
            without_lut[i] = _mean_loss(base_profile, [dataset[i]])
            with_lut[i] = _mean_loss(hue_profile, [dataset[i]])
    return without_lut, with_lut


def run(n_folds=4, seed=0, n_passes=1):
    print("후지 raw+jpeg 페어 로드 중 (캘리브레이션용 축소 해상도)...")
    dataset = _load_calib_set()
    print(f"총 {len(dataset)}쌍 로드 완료\n")
    if not dataset:
        print("페어를 못 찾음 - datasets/leica/contributed/*/manifest.csv 확인 필요")
        return

    baseline_loss = _mean_loss(_DEFAULT_PARAMS, dataset)
    print(f"베이스라인 ΔE (V0.1 기본 파라미터, 후지용 시드 없음): {baseline_loss:.3f}")

    new_params, in_sample_loss = _find_matrix_and_recalibrate(dataset, n_passes=n_passes)
    in_sample_improvement = (baseline_loss - in_sample_loss) / baseline_loss * 100
    print(f"\n신규 파이프라인 ΔE (in-sample, 매트릭스+톤/색 재학습): "
          f"{in_sample_loss:.3f} ({in_sample_improvement:+.1f}%)")

    cv_loss = None
    if len(dataset) >= n_folds:
        rng = np.random.default_rng(seed)
        order = rng.permutation(len(dataset))
        folds = np.array_split(order, n_folds)
        fold_losses = []
        for fi, fold_idx in enumerate(folds):
            fold_idx_set = set(fold_idx.tolist())
            train_set = [d for i, d in enumerate(dataset) if i not in fold_idx_set]
            held_out = [dataset[i] for i in fold_idx]
            fold_params, _ = _find_matrix_and_recalibrate(train_set, n_passes=n_passes)
            fold_loss = _mean_loss(fold_params, held_out)
            fold_losses.append(fold_loss)
            print(f"  fold {fi + 1}/{n_folds} ΔE={fold_loss:.3f}", flush=True)
        cv_loss = float(np.mean(fold_losses))
        cv_improvement = (baseline_loss - cv_loss) / baseline_loss * 100
        print(f"\n신규 파이프라인 ΔE ({n_folds}-fold 교차검증): {cv_loss:.3f} "
              f"({cv_improvement:+.1f}%)")

    print(f"\n판정: {'목표(ΔE00<=5) 도달' if (cv_loss or in_sample_loss) <= 5 else '목표(ΔE00<=5) 미달'}")

    print("\n" + "=" * 60)
    print("Gray World(기본) vs Gray Edge - 페어드 nested CV")
    gray_world_pairwise = _paired_cv_losses(dataset, fixed_overrides=None, n_folds=n_folds, seed=seed)
    gray_edge_pairwise = _paired_cv_losses(
        dataset, fixed_overrides={"color_cast_algorithm": "gray_edge", "gray_edge_p": 1.0},
        n_folds=n_folds, seed=seed)
    summarize("gray_world", gray_world_pairwise, "gray_edge", gray_edge_pairwise)

    print("\n" + "=" * 60)
    print("hue LUT 추가 - gray_edge 기반 프로필 위에")
    gray_edge_full_params, _ = _find_matrix_and_recalibrate(
        dataset, n_passes=n_passes,
        fixed_overrides={"color_cast_algorithm": "gray_edge", "gray_edge_p": 1.0})
    without_lut, with_lut = _hue_lut_paired_cv_losses(dataset, gray_edge_full_params, n_folds=n_folds, seed=seed)
    summarize("no_hue_lut", without_lut, "hue_lut", with_lut)

    return baseline_loss, in_sample_loss, cv_loss, new_params


if __name__ == "__main__":
    run()
