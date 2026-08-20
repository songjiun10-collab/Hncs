"""
hybrid_engine v1.2가 실제로 어디서 틀리는지 픽셀 단위로 진단.
`evaluation/fidelity.py`는 페어당 평균/p95/max/구간별 ΔE만 낸다 - 그 숫자
뒤에 있는 "어느 픽셀이, 어떤 밝기/색상에서" 틀리는지는 안 보여준다.

이 스크립트는:
1. 13쌍 전체를 돌려서 픽셀별 ΔE00을 pooling, L(밝기)/hue(색상각) 구간별
   평균 오차 표로 낸다 - 어떤 색상대가 가장 심하게 틀리는지 확인.
2. ΔE가 가장 큰/가장 작은/중간값 페어 3장을 골라서 공간 히트맵을 만든다
   (matplotlib 없이 cv2.applyColorMap - 이 프로젝트의 최소 의존성 원칙).

1패스에서 13쌍 전부의 (result, target, de_map) 전체 배열을 동시에 들고
있다가 메모리 7GB+ 로 치솟는 걸 실측으로 확인해서(raw 파일 자체는
100MB급이라 크지 않은데도), 페어별로 다운샘플된 pooled 통계만 남기고
바로 버리는 구조로 바꿨다 - 히트맵이 필요한 3장(최악/중간/최선)은
결과가 정해진 뒤 2패스에서 그 3장만 다시 디코드한다.

  python3 -m tools.analyze_pixel_errors
"""
import gc
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import colour

from hybrid_engine.calibrate_profile import _find_pairs, _resize_max_dim
from hybrid_engine.core import color_matrix
from hybrid_engine.pipeline.engine import HybridCameraEngine
from hybrid_engine.utils.io import decode_raw, load_image_linear
from hybrid_engine.evaluation.fidelity import _load_profile, EVAL_MAX_DIM

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "eval_reports", "pixel_analysis")
_SRGB = colour.RGB_COLOURSPACES["sRGB"]

L_BINS = [(0, 20), (20, 33), (33, 50), (50, 66), (66, 80), (80, 101)]
HUE_BINS = [(i * 30, (i + 1) * 30) for i in range(12)]
HUE_LABELS = ["red", "orange", "yellow-orange", "yellow", "yellow-green", "green",
              "cyan-green", "cyan", "blue", "blue-violet", "violet", "magenta"]


def _to_lab(rgb_linear):
    xyz = colour.RGB_to_XYZ(rgb_linear, _SRGB, apply_cctf_decoding=False)
    return colour.XYZ_to_Lab(xyz)


def _process_pair(engine, raw_path, target_path):
    """(engine 결과 linear RGB, target linear RGB, de_map(H,W), lab_target(H,W,3))."""
    linear = _resize_max_dim(decode_raw(raw_path), EVAL_MAX_DIM)
    camera_wb = color_matrix.extract_camera_metadata(raw_path)["camera_whitebalance"]
    target = load_image_linear(target_path)
    if target.shape != linear.shape:
        target = cv2.resize(target, (linear.shape[1], linear.shape[0]), interpolation=cv2.INTER_AREA)

    result = engine.process(linear, camera_whitebalance=camera_wb)
    lab_result = _to_lab(result)
    lab_target = _to_lab(target)
    de_map = np.asarray(colour.delta_E(lab_result.reshape(-1, 3), lab_target.reshape(-1, 3),
                                        method="CIE 2000")).reshape(result.shape[:2])
    return result, target, de_map, lab_target


def _heatmap(delta_e_map, vmax=30.0):
    """(H, W) ΔE00 맵 -> JET 컬러맵 BGR uint8 이미지."""
    norm = np.clip(delta_e_map / vmax, 0.0, 1.0)
    u8 = (norm * 255).astype(np.uint8)
    return cv2.applyColorMap(u8, cv2.COLORMAP_JET)


def _side_by_side(engine_bgr, target_bgr, heatmap_bgr, label):
    bar_h = 40
    panels = [engine_bgr, target_bgr, heatmap_bgr]
    titles = ["hybrid_engine v1.2", "actual camera JPEG", "|Delta E00| heatmap (0-30)"]
    out_panels = []
    for panel, title in zip(panels, titles):
        bar = np.zeros((bar_h, panel.shape[1], 3), dtype=np.uint8)
        cv2.putText(bar, title, (10, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        out_panels.append(np.vstack([bar, panel]))
    combined = np.hstack(out_panels)
    cv2.putText(combined, label, (10, combined.shape[0] - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    return combined


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    # _load_profile(None)은 assets/profiles/hasselblad.json이 아니라 엔진의
    # 튜닝 전 하드코딩된 _DEFAULT_PARAMS(raw_baseline_matrix 없음, sat_gain
    # 0.15 등)를 쓰게 만든다 - 배포된 v1.2를 진단하려는 게 목적이라 반드시
    # 명시적으로 로드해야 한다.
    engine = HybridCameraEngine(profile=_load_profile("hasselblad"))
    pairs = _find_pairs()

    per_pair_mean = []
    pooled_de, pooled_L, pooled_hue = [], [], []

    print(f"=== 1패스: {len(pairs)}쌍 요약 통계 ===", flush=True)
    for raw_path, target_path in pairs:
        name = os.path.basename(raw_path)
        print(f"  처리 중: {name}", flush=True)
        result, target, de_map, lab_target = _process_pair(engine, raw_path, target_path)

        per_pair_mean.append({"name": name, "raw_path": raw_path, "target_path": target_path,
                               "mean_de": float(de_map.mean())})

        # 메모리 절약 - 4픽셀당 1개만 pooled 통계에 사용, 원본 배열은 즉시 버림
        pooled_de.append(de_map.ravel()[::4].copy())
        pooled_L.append(lab_target[:, :, 0].ravel()[::4].copy())
        pooled_hue.append((np.degrees(np.arctan2(lab_target[:, :, 2], lab_target[:, :, 1])) % 360)
                           .ravel()[::4].copy())

        del result, target, de_map, lab_target
        gc.collect()

    pooled_de = np.concatenate(pooled_de)
    pooled_L = np.concatenate(pooled_L)
    pooled_hue = np.concatenate(pooled_hue)

    print(f"\n=== 밝기(L) 구간별 평균 ΔE00 (전체 {len(pooled_de)}픽셀 pooled) ===")
    l_table = []
    for lo, hi in L_BINS:
        mask = (pooled_L >= lo) & (pooled_L < hi)
        if mask.sum() == 0:
            continue
        row = {"L_range": f"{lo}-{hi}", "mean_de": float(pooled_de[mask].mean()), "n": int(mask.sum())}
        l_table.append(row)
        print(f"  L {lo:3d}-{hi:3d}: ΔE00 평균 {row['mean_de']:6.2f}  (n={row['n']:,})")

    print("\n=== 색상(hue) 구간별 평균 ΔE00 ===")
    hue_table = []
    for (lo, hi), label in zip(HUE_BINS, HUE_LABELS):
        mask = (pooled_hue >= lo) & (pooled_hue < hi)
        if mask.sum() == 0:
            continue
        row = {"hue_range": f"{lo}-{hi}", "label": label, "mean_de": float(pooled_de[mask].mean()),
               "n": int(mask.sum())}
        hue_table.append(row)
        print(f"  hue {lo:3d}-{hi:3d}deg ({label:15s}): ΔE00 평균 {row['mean_de']:6.2f}  (n={row['n']:,})")

    del pooled_de, pooled_L, pooled_hue
    gc.collect()

    per_pair_sorted = sorted(per_pair_mean, key=lambda p: p["mean_de"])
    worst = per_pair_sorted[-1]
    best = per_pair_sorted[0]
    median = per_pair_sorted[len(per_pair_sorted) // 2]

    print(f"\n최악: {worst['name']} (ΔE00 {worst['mean_de']:.2f})")
    print(f"중간: {median['name']} (ΔE00 {median['mean_de']:.2f})")
    print(f"최선: {best['name']} (ΔE00 {best['mean_de']:.2f})")

    print("\n=== 2패스: 대표 3쌍 재디코드 + 히트맵 생성 ===", flush=True)
    saved_heatmaps = []
    for tag, pair in (("worst", worst), ("median", median), ("best", best)):
        print(f"  재처리 중: {pair['name']}", flush=True)
        result, target, de_map, _ = _process_pair(engine, pair["raw_path"], pair["target_path"])

        result_srgb = colour.cctf_encoding(np.clip(result, 0, 1), function="sRGB")
        target_srgb = colour.cctf_encoding(np.clip(target, 0, 1), function="sRGB")
        result_bgr = (result_srgb * 255).astype(np.uint8)[:, :, ::-1]
        target_bgr = (target_srgb * 255).astype(np.uint8)[:, :, ::-1]
        heat_bgr = _heatmap(de_map)
        combined = _side_by_side(result_bgr, target_bgr, heat_bgr,
                                  f"{tag}: {pair['name']}  mean dE00={pair['mean_de']:.2f}")
        out_path = os.path.join(OUT_DIR, f"{tag}_{pair['name'].replace('.', '_')}.jpg")
        cv2.imwrite(out_path, combined, [cv2.IMWRITE_JPEG_QUALITY, 92])
        saved_heatmaps.append(out_path)
        print(f"저장: {out_path}")

        del result, target, de_map, result_srgb, target_srgb, result_bgr, target_bgr, heat_bgr, combined
        gc.collect()

    report = {
        "per_pair": [{"name": p["name"], "mean_de": p["mean_de"]} for p in per_pair_mean],
        "l_bins": l_table,
        "hue_bins": hue_table,
        "heatmaps": saved_heatmaps,
    }
    report_path = os.path.join(OUT_DIR, "report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n리포트 저장: {report_path}")


if __name__ == "__main__":
    main()
