"""X2D II 100C 챠트 매트릭스를 kmichels 단일-조명 번스트(9장, 2026-07)
+ dpreview 스튜디오씬 Daylight/Lowlight(16장, 2026-09)로 합쳐서 다시
피팅한다 - 사용자가 두 데이터셋의 조명 조건이 실제로 다르다는 걸
직접 확인시킨 뒤("우리꺼하고 다른줄 알고 시킴") 명시적으로 승인한
작업("이제 하셀은 보정 ㄱㄱ dcp").

방법론은 이미 승인·배포된 "_weighted" 단계(무채색 6패치 대비 유채색
18패치 4x 가중 최소자승, ridge=0.0 - camera_native_matrix_report.json의
_comment_weighted 참고)를 그대로 쓴다. 그 다음 IRLS/patch-17-cyan
재조정 단계는 **이번엔 재적용하지 않는다** - 그 두 단계는 전부 n=9
kmichels 단독 데이터의 특정 잔차 패턴(특히 cyan 패치)에 맞춰 손튜닝된
것이라(리포트 자체가 "n=9 표본 과적합" 위험을 명시) 25장으로 늘어난
합친 데이터에 그대로 전이된다는 보장이 없다 - 재적용하려면 그 자체로
새 검증이 필요한 별도 작업이라 여기서는 범위 밖으로 둔다.

  python3 -m tools.refit_x2dii_chart_combined
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.io import decode_raw_native
from core.dcp_export import write_dcp, read_dcp, TAG_PROFILE_EMBED_POLICY

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KMICHELS_DIR = os.path.join(BASE, "datasets", "hasselblad", "contributed",
                             "kmichels-x2dii-2026-07")
DPREVIEW_DIR = os.path.join(BASE, "datasets", "hasselblad", "contributed",
                             "dpreview-x2dii100c-studio-chart-2026-09")
OUT_DCP = os.path.join(BASE, "hybrid_engine", "assets", "profiles",
                        "hasselblad_x2dii_chart.dcp")
OUT_REPORT = os.path.join(DPREVIEW_DIR, "combined_chart_matrix_report.json")

UNIQUE_CAMERA_MODEL = "Hasselblad 100-22-Coated6"
PROFILE_NAME = "HNCS X2D II Chart Colorimetric"
CALIBRATION_ILLUMINANT_ENUM = 23  # D50 - camera_native_matrix_report.json과 동일 근거

CHROMA_WEIGHT = 4.0  # 기존 배포 매트릭스의 _weighted 단계와 동일값
NEUTRAL_PATCH_INDICES = set(range(18, 24))


def _mean_de(samples_xyz, reference):
    return float(np.mean(chart_baseline.patch_delta_e_xyz_d50(samples_xyz, reference)))


def _load_samples(raw_dir, pattern):
    per_image = {}
    for raw_path in sorted(glob.glob(os.path.join(raw_dir, pattern))):
        name = os.path.basename(raw_path)
        try:
            native = decode_raw_native(raw_path)
            samples = chart_baseline.detect_and_sample(native)
        except Exception as e:
            print(f"    검출 실패(예외 {type(e).__name__}), 제외: {name}")
            continue
        if samples is None:
            print(f"    검출 실패, 제외: {name}")
            continue
        per_image[name] = samples
    return per_image


def main():
    reference = chart_baseline.reference_patches_xyz_d50()
    weights = np.array([1.0 if i in NEUTRAL_PATCH_INDICES else CHROMA_WEIGHT
                         for i in range(24)])

    print("kmichels (n=9, 단일 조명, 2026-07) 디코드+검출:")
    kmichels = _load_samples(os.path.join(KMICHELS_DIR, "raw"), "*.3FR")
    print(f"  {len(kmichels)}장 성공")

    print("dpreview (Daylight/Lowlight, 2026-09) 디코드+검출:")
    dpreview = _load_samples(os.path.join(DPREVIEW_DIR, "raw"), "*.3fr")
    print(f"  {len(dpreview)}장 성공")

    combined = {**kmichels, **dpreview}
    print(f"\n합계 {len(combined)}장 (kmichels {len(kmichels)} + dpreview {len(dpreview)})")

    def _weighted_loo_cv(per_image):
        names = sorted(per_image.keys())
        n = len(names)
        no_corr = np.array([_mean_de(per_image[nm], reference) for nm in names])
        k = min(n, 5)
        rng = np.random.RandomState(0)
        folds = np.array_split(rng.permutation(n), k)
        cv_de = np.zeros(n)
        for test_idx in folds:
            train_idx = [i for i in range(n) if i not in set(test_idx.tolist())]
            train_names = [names[i] for i in train_idx]
            m = raw_baseline.fit_color_matrix(
                [per_image[nm] for nm in train_names],
                [reference] * len(train_names),
                weights=[weights for _ in train_names])
            for i in test_idx:
                pred = raw_baseline.apply_color_matrix(per_image[names[i]], m)
                cv_de[i] = _mean_de(pred, reference)
        diff = no_corr - cv_de
        rng2 = np.random.RandomState(1)
        boot = np.array([diff[rng2.randint(0, n, n)].mean() for _ in range(20000)])
        ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
        return {
            "n": n, "k": k,
            "no_corr_mean": float(no_corr.mean()),
            "cv_mean": float(cv_de.mean()),
            "improvement_pct": float((no_corr.mean() - cv_de.mean()) / no_corr.mean() * 100),
            "ci95": [float(ci_lo), float(ci_hi)],
            "wins": int((diff > 0).sum()), "losses": int((diff < 0).sum()),
        }

    print("\n=== kmichels 단독 재현 (기존 배포 매트릭스의 _weighted 단계와 같은 프로토콜) ===")
    kmichels_result = _weighted_loo_cv(kmichels)
    print(json.dumps(kmichels_result, indent=2))

    print("\n=== 합친 데이터(kmichels + dpreview) ===")
    combined_result = _weighted_loo_cv(combined)
    print(json.dumps(combined_result, indent=2))

    names = sorted(combined.keys())
    all_sources = [combined[nm] for nm in names]
    all_targets = [reference for _ in names]
    all_weights = [weights for _ in names]
    final_matrix = raw_baseline.fit_color_matrix(all_sources, all_targets, weights=all_weights)
    in_sample = float(np.mean([_mean_de(raw_baseline.apply_color_matrix(combined[nm], final_matrix),
                                         reference) for nm in names]))
    print(f"\n전체 {len(names)}장 pooled in-sample ΔE00 = {in_sample:.4f}")

    dcp_color_matrix_1 = np.linalg.inv(final_matrix).T

    neutral_per_patch = {}
    for idx in sorted(NEUTRAL_PATCH_INDICES):
        vals = []
        for samples in combined.values():
            rgb = np.asarray(samples[idx], dtype=np.float64)
            if rgb[1] <= 0:
                continue
            vals.append(rgb / rgb[1])
        if vals:
            neutral_per_patch[chart_baseline.PATCH_NAMES[idx]] = np.mean(vals, axis=0)
    measured_native_neutral = np.mean(list(neutral_per_patch.values()), axis=0)
    measured_native_neutral = measured_native_neutral / measured_native_neutral[1]

    report = {
        "camera_model": "Hasselblad X2D II 100C",
        "sources": {
            "kmichels-x2dii-2026-07": sorted(kmichels.keys()),
            "dpreview-x2dii100c-studio-chart-2026-09": sorted(dpreview.keys()),
        },
        "chroma_patch_weight": CHROMA_WEIGHT,
        "methodology": "무채색 6패치 대비 유채색 18패치 4x 가중 최소자승, ridge=0.0 - "
                        "IRLS/patch-17-cyan 재조정 단계는 재적용 안 함(스크립트 docstring 참고)",
        "kmichels_only_weighted_loo_cv": kmichels_result,
        "combined_weighted_loo_cv": combined_result,
        "n_images_combined": len(names),
        "chart_matrix_in_sample": final_matrix.tolist(),
        "chart_matrix_in_sample_delta_e_mean": in_sample,
        "dcp_color_matrix_1": dcp_color_matrix_1.tolist(),
        "measured_native_neutral_g_normalized": measured_native_neutral.tolist(),
        "measured_native_neutral_per_patch":
            {k: v.tolist() for k, v in neutral_per_patch.items()},
        "calibration_illuminant": {
            "chosen_enum": CALIBRATION_ILLUMINANT_ENUM,
            "chosen_enum_name": "D50",
        },
    }
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n저장: {OUT_REPORT}")

    write_dcp(OUT_DCP, camera_model=UNIQUE_CAMERA_MODEL, profile_name=PROFILE_NAME,
              color_matrix_1=dcp_color_matrix_1, calibration_illuminant_1=CALIBRATION_ILLUMINANT_ENUM)
    tags = read_dcp(OUT_DCP)
    print(f"\nDCP 재발급: {OUT_DCP}")
    print(f"  UniqueCameraModel = {tags[50708]!r}")
    print(f"  ProfileEmbedPolicy present = {TAG_PROFILE_EMBED_POLICY in tags}")


if __name__ == "__main__":
    main()
