"""X2D II 100C combined 챠트 데이터(kmichels 9 + dpreview 16 = 25장)가
단일 조명이 아니라는 게 `tools/analyze_x2dii_combined_lighting_split.py`
분석으로 확인됐다(무채색 6패치 실측 native R/G가 3그룹으로 뚜렷이
갈림: dpreview 저R/G≈0.33(daylight성, n=9), dpreview 고R/G≈0.64
(tungsten성, n=7), kmichels≈0.41(그 사이, n=9) - 이 셋을 하나의 3x3
매트릭스로 합쳐 피팅하면 5-fold CV 12.69로, 각 그룹 단독 피팅
(2.72~5.81)보다 훨씬 나쁘다). 사용자 승인(구현 진행) 받아 DNG의
dual-illuminant 메커니즘(`ColorMatrix1`+`ColorMatrix2`+
`CalibrationIlluminant1/2` - `core/dcp_export.py`에 이번에 추가)으로
풀어본다.

**설계**: 두 극단 클러스터(dpreview 저R/G=daylight성, 고R/G=tungsten성)
로 각각 `ColorMatrix1`/`ColorMatrix2`를 피팅한다(같은 방법론 - 무채색
6패치 대비 유채색 18패치 4x 가중 최소자승, ridge=0.0). kmichels(중간
조명, n=9)는 두 매트릭스 어디에도 쓰지 않고 **완전한 홀드아웃**으로
남겨서 "Adobe가 이 둘을 보간하면 한 번도 본 적 없는 세 번째 조명도
맞힐 수 있는가"를 검증하는 데 쓴다.

CalibrationIlluminant enum은 정확한 CCT 측정값이 없어서(EXIF에 없음)
관측된 R/G 극성(저R/G=차가움, 고R/G=따뜻함)에 맞는 표준 EXIF LightSource
값으로 근사한다: 저R/G -> 21(D65, 대표적 daylight), 고R/G -> 17
(Standard Light A, 대표적 tungsten/incandescent ~2856K). 실제 촬영
조명의 정확한 색온도가 아니라 "둘 중 어느 쪽에 더 가까운 성질인가"의
방향성 근사다고 EVALUATION.md에 명시한다.

**보간 검증**: Adobe DNG SDK의 실제 보간 알고리즘은 이 프로젝트가
재현한 게 아니다(문서화된 스펙이 있지만 정확한 재현은 실기기에서만
검증 가능 - 기존 파일 docstring의 "미검증" 패턴과 동일). 대신 이
스크립트는 **단순화한 근사**(측정한 native R/G를 두 기준 클러스터의
평균 R/G 사이에서 선형 보간해 가중치를 만들고, 그 가중치로 두 매트릭스를
선형 블렌드)로 "두 매트릭스를 이렇게 섞으면 홀드아웃(kmichels)이
좋아지는가"만 확인한다 - Lightroom이 실제로 같은 보간을 하는지는
별개 문제(실기기 미검증으로 남긴다).

  python3 -m tools.refit_x2dii_dual_illuminant
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
OUT_REPORT = os.path.join(DPREVIEW_DIR, "dual_illuminant_report.json")

UNIQUE_CAMERA_MODEL = "Hasselblad 100-22-Coated6"
PROFILE_NAME = "HNCS X2D II Chart Colorimetric (dual-illuminant)"
ILLUMINANT_1_ENUM = 21  # D65 근사 - 저R/G(daylight성) 클러스터
ILLUMINANT_2_ENUM = 17  # Standard Light A 근사 - 고R/G(tungsten성) 클러스터

CHROMA_WEIGHT = 4.0
NEUTRAL_PATCH_INDICES = set(range(18, 24))
RG_SPLIT = 0.5  # analyze_x2dii_combined_lighting_split.py에서 확인된 자연 경계


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


def _neutral_ratio(samples):
    vals = []
    for idx in sorted(NEUTRAL_PATCH_INDICES):
        rgb = np.asarray(samples[idx], dtype=np.float64)
        if rgb[1] <= 0:
            continue
        vals.append(rgb / rgb[1])
    m = np.mean(vals, axis=0)
    return m / m[1]


def _mean_de(samples_xyz, reference):
    return float(np.mean(chart_baseline.patch_delta_e_xyz_d50(samples_xyz, reference)))


def _fit_group_cv(per_image, weights, reference, seed=0):
    names = sorted(per_image.keys())
    n = len(names)
    k = min(n, 5)
    rng = np.random.RandomState(seed)
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
    return {"n": n, "k": k, "cv_mean": float(cv_de.mean())}


def main():
    reference = chart_baseline.reference_patches_xyz_d50()
    weights = np.array([1.0 if i in NEUTRAL_PATCH_INDICES else CHROMA_WEIGHT
                         for i in range(24)])

    print("kmichels(홀드아웃) 디코드+검출:")
    kmichels = _load_samples(os.path.join(KMICHELS_DIR, "raw"), "*.3FR")
    print(f"  {len(kmichels)}장")
    print("dpreview 디코드+검출:")
    dpreview = _load_samples(os.path.join(DPREVIEW_DIR, "raw"), "*.3fr")
    print(f"  {len(dpreview)}장")

    dp_neutral = {nm: _neutral_ratio(s) for nm, s in dpreview.items()}
    group1 = {nm: s for nm, s in dpreview.items() if dp_neutral[nm][0] < RG_SPLIT}   # daylight성
    group2 = {nm: s for nm, s in dpreview.items() if dp_neutral[nm][0] >= RG_SPLIT}  # tungsten성
    print(f"\ngroup1(daylight성, R/G<{RG_SPLIT}) n={len(group1)}, "
          f"group2(tungsten성, R/G>={RG_SPLIT}) n={len(group2)}, "
          f"kmichels(홀드아웃) n={len(kmichels)}")

    print("\n=== group1 단독 5-fold CV ===")
    g1_cv = _fit_group_cv(group1, weights, reference)
    print(json.dumps(g1_cv, indent=2))
    print("\n=== group2 단독 5-fold CV ===")
    g2_cv = _fit_group_cv(group2, weights, reference)
    print(json.dumps(g2_cv, indent=2))

    names1 = sorted(group1.keys())
    matrix_1 = raw_baseline.fit_color_matrix(
        [group1[nm] for nm in names1], [reference] * len(names1),
        weights=[weights for _ in names1])
    names2 = sorted(group2.keys())
    matrix_2 = raw_baseline.fit_color_matrix(
        [group2[nm] for nm in names2], [reference] * len(names2),
        weights=[weights for _ in names2])

    g1_in_sample = float(np.mean([_mean_de(raw_baseline.apply_color_matrix(group1[nm], matrix_1), reference)
                                   for nm in names1]))
    g2_in_sample = float(np.mean([_mean_de(raw_baseline.apply_color_matrix(group2[nm], matrix_2), reference)
                                   for nm in names2]))
    print(f"\ngroup1 pooled in-sample ΔE00 = {g1_in_sample:.4f}")
    print(f"group2 pooled in-sample ΔE00 = {g2_in_sample:.4f}")

    rg1 = np.mean([dp_neutral[nm][0] for nm in names1])
    rg2 = np.mean([dp_neutral[nm][0] for nm in names2])
    print(f"\ngroup1 평균 R/G = {rg1:.4f} (illuminant1={ILLUMINANT_1_ENUM})")
    print(f"group2 평균 R/G = {rg2:.4f} (illuminant2={ILLUMINANT_2_ENUM})")

    neutral_g1 = np.mean([dp_neutral[nm] for nm in names1], axis=0)
    neutral_g1 = (neutral_g1 / neutral_g1[1]).tolist()
    neutral_g2 = np.mean([dp_neutral[nm] for nm in names2], axis=0)
    neutral_g2 = (neutral_g2 / neutral_g2[1]).tolist()

    # --- 홀드아웃(kmichels) 검증: 단일매트릭스 vs 보간 근사 ---
    km_names = sorted(kmichels.keys())
    km_rg = {nm: _neutral_ratio(kmichels[nm])[0] for nm in km_names}

    de_matrix1_only = [_mean_de(raw_baseline.apply_color_matrix(kmichels[nm], matrix_1), reference)
                        for nm in km_names]
    de_matrix2_only = [_mean_de(raw_baseline.apply_color_matrix(kmichels[nm], matrix_2), reference)
                        for nm in km_names]

    de_interp = []
    for nm in km_names:
        g = (km_rg[nm] - rg2) / (rg1 - rg2)  # rg1<rg2이므로 g in [0,1] 근처, 밖이면 clip
        g = float(np.clip(g, 0.0, 1.0))
        blended = g * matrix_1 + (1 - g) * matrix_2
        pred = raw_baseline.apply_color_matrix(kmichels[nm], blended)
        de_interp.append(_mean_de(pred, reference))

    print(f"\n=== kmichels 홀드아웃(n={len(km_names)}) 검증 ===")
    print(f"matrix1(daylight)만 적용: {np.mean(de_matrix1_only):.4f}")
    print(f"matrix2(tungsten)만 적용: {np.mean(de_matrix2_only):.4f}")
    print(f"R/G 선형보간 블렌드 적용: {np.mean(de_interp):.4f}")
    old_global_cv = 12.6865  # tools/refit_x2dii_chart_combined.py 5-fold CV(재현값)
    print(f"(참고) 기존 global 단일매트릭스 25장 5-fold CV = {old_global_cv}")

    # --- 25장 전체 공정 비교: global 5-fold CV(이미지별) vs
    # dual-illuminant(그룹별 자기 5-fold CV + kmichels는 위 보간 홀드아웃) ---
    combined = {**kmichels, **dpreview}
    names_all = sorted(combined.keys())
    k_all = min(len(names_all), 5)
    rng_all = np.random.RandomState(0)
    folds_all = np.array_split(rng_all.permutation(len(names_all)), k_all)
    de_global_per_image = {}
    for test_idx in folds_all:
        train_idx = [i for i in range(len(names_all)) if i not in set(test_idx.tolist())]
        train_names = [names_all[i] for i in train_idx]
        m = raw_baseline.fit_color_matrix(
            [combined[nm] for nm in train_names], [reference] * len(train_names),
            weights=[weights for _ in train_names])
        for i in test_idx:
            pred = raw_baseline.apply_color_matrix(combined[names_all[i]], m)
            de_global_per_image[names_all[i]] = _mean_de(pred, reference)

    def _group_cv_per_image(group, seed=0):
        gn = sorted(group.keys())
        gk = min(len(gn), 5)
        grng = np.random.RandomState(seed)
        gfolds = np.array_split(grng.permutation(len(gn)), gk)
        out = {}
        for test_idx in gfolds:
            train_idx = [i for i in range(len(gn)) if i not in set(test_idx.tolist())]
            tn = [gn[i] for i in train_idx]
            gm = raw_baseline.fit_color_matrix(
                [group[nm] for nm in tn], [reference] * len(tn),
                weights=[weights for _ in tn])
            for i in test_idx:
                pred = raw_baseline.apply_color_matrix(group[gn[i]], gm)
                out[gn[i]] = _mean_de(pred, reference)
        return out

    de_dual_per_image = {}
    de_dual_per_image.update(_group_cv_per_image(group1))
    de_dual_per_image.update(_group_cv_per_image(group2))
    for nm, de in zip(km_names, de_interp):
        de_dual_per_image[nm] = de

    de_global_arr = np.array([de_global_per_image[nm] for nm in names_all])
    de_dual_arr = np.array([de_dual_per_image[nm] for nm in names_all])
    diff_all = de_global_arr - de_dual_arr
    rng_boot = np.random.RandomState(1)
    boot_all = np.array([diff_all[rng_boot.randint(0, len(names_all), len(names_all))].mean()
                          for _ in range(20000)])
    ci_lo_all, ci_hi_all = np.percentile(boot_all, [2.5, 97.5])
    full25_comparison = {
        "n": len(names_all),
        "global_5fold_cv_mean": float(de_global_arr.mean()),
        "dual_illuminant_mean": float(de_dual_arr.mean()),
        "paired_diff_mean": float(diff_all.mean()),
        "bootstrap_ci95": [float(ci_lo_all), float(ci_hi_all)],
        "wins": int((diff_all > 0).sum()), "losses": int((diff_all < 0).sum()),
        "improvement_pct": float((de_global_arr.mean() - de_dual_arr.mean())
                                  / de_global_arr.mean() * 100),
        "note": "global은 25장 5-fold CV(이미지별). dual은 group1/group2 각자 5-fold CV "
                "+ kmichels는 두 매트릭스 어디에도 없던 순수 홀드아웃(R/G 선형보간 적용) - "
                "셋 다 out-of-sample이라 공정 비교.",
    }
    print(f"\n=== 25장 전체 공정 비교(global 5-fold CV vs dual-illuminant) ===")
    print(json.dumps(full25_comparison, indent=2))

    report = {
        "camera_model": "Hasselblad X2D II 100C",
        "methodology": "R/G 클러스터 2분할(daylight성/tungsten성) - 무채색 6패치 대비 "
                        "유채색 18패치 4x 가중 최소자승, ridge=0.0. kmichels는 홀드아웃.",
        "group1_daylight_like": {
            "n": len(names1), "images": names1, "mean_rg": float(rg1),
            "cv_5fold": g1_cv, "in_sample": g1_in_sample,
            "calibration_illuminant": ILLUMINANT_1_ENUM,
            "measured_native_neutral_g_normalized": neutral_g1,
        },
        "group2_tungsten_like": {
            "n": len(names2), "images": names2, "mean_rg": float(rg2),
            "cv_5fold": g2_cv, "in_sample": g2_in_sample,
            "calibration_illuminant": ILLUMINANT_2_ENUM,
            "measured_native_neutral_g_normalized": neutral_g2,
        },
        "kmichels_holdout_validation": {
            "n": len(km_names),
            "delta_e00_matrix1_only_mean": float(np.mean(de_matrix1_only)),
            "delta_e00_matrix2_only_mean": float(np.mean(de_matrix2_only)),
            "delta_e00_rg_interpolated_mean": float(np.mean(de_interp)),
            "note": "R/G 선형 보간은 이 프로젝트가 만든 근사 - Adobe DNG SDK의 실제 "
                    "보간 알고리즘 재현이 아님(실기기 미검증).",
        },
        "old_global_single_matrix_25img_5fold_cv": old_global_cv,
        "full25_fair_comparison": full25_comparison,
        "color_matrix_1": matrix_1.tolist(),
        "color_matrix_2": matrix_2.tolist(),
        "dcp_color_matrix_1": np.linalg.inv(matrix_1).T.tolist(),
        "dcp_color_matrix_2": np.linalg.inv(matrix_2).T.tolist(),
    }
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n저장: {OUT_REPORT}")

    # 배포 판정: 25장 전체 공정 비교의 부트스트랩 95% CI가 0을 안 걸침
    # (개선 방향으로 완전히 양수) -> 배포. 아니면 dry-run으로 끝낸다.
    if full25_comparison["bootstrap_ci95"][0] <= 0:
        print("\nCI가 0을 걸침 - 배포 안 함(dry-run으로 종료).")
        return

    write_dcp(OUT_DCP, camera_model=UNIQUE_CAMERA_MODEL, profile_name=PROFILE_NAME,
              color_matrix_1=report["dcp_color_matrix_1"],
              calibration_illuminant_1=ILLUMINANT_1_ENUM,
              color_matrix_2=report["dcp_color_matrix_2"],
              calibration_illuminant_2=ILLUMINANT_2_ENUM)
    tags = read_dcp(OUT_DCP)
    print(f"\nDCP 재발급(dual-illuminant): {OUT_DCP}")
    print(f"  UniqueCameraModel = {tags[50708]!r}")
    print(f"  CalibrationIlluminant1 = {tags[50778]}, CalibrationIlluminant2 = {tags[50779]}")
    print(f"  ProfileEmbedPolicy present = {TAG_PROFILE_EMBED_POLICY in tags}")


if __name__ == "__main__":
    main()
