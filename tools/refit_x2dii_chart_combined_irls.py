"""`tools/refit_x2dii_chart_combined.py`(kmichels 9장 + dpreview 16장,
n=25, 무채색-4x 가중 최소자승만)에 Huber IRLS를 마저 적용한다 - 사용자가
그 결과를 보고 명시적으로 승인("Irls ㄱㄱ").

IRLS 구현은 새로 안 만들고 `tools/evaluate_dcp_irls_weighted.py`의
`_irls_fit()`을 그대로 가져다 쓴다(`refit_dcp_irls_final.py`가 kmichels
단독일 때 썼던 것과 같은 재사용 패턴) - 무채색-4x 초기값에서 시작.

  python3 -m tools.refit_x2dii_chart_combined_irls
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
from tools.evaluate_dcp_irls_weighted import _irls_fit

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
CALIBRATION_ILLUMINANT_ENUM = 23


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
    chroma_init = np.array([1.0 if i in range(18, 24) else 4.0 for i in range(24)])

    print("kmichels (n=9) 디코드+검출:")
    kmichels = _load_samples(os.path.join(KMICHELS_DIR, "raw"), "*.3FR")
    print(f"  {len(kmichels)}장 성공")
    print("dpreview (n=17) 디코드+검출:")
    dpreview = _load_samples(os.path.join(DPREVIEW_DIR, "raw"), "*.3fr")
    print(f"  {len(dpreview)}장 성공")

    combined = {**kmichels, **dpreview}
    names = sorted(combined.keys())
    n = len(names)
    print(f"\n합계 {n}장")

    # 5-fold CV (evaluate_dcp_irls_weighted.py의 LOO를 25장 규모에 맞춰
    # 확장 - refit_x2dii_chart_combined.py와 같은 fold 분할로 직접 비교
    # 가능하게 함)
    k = min(n, 5)
    rng = np.random.RandomState(0)
    folds = np.array_split(rng.permutation(n), k)
    no_corr = np.array([_mean_de(combined[nm], reference) for nm in names])
    cv_de = np.zeros(n)
    for fi, test_idx in enumerate(folds):
        train_idx = [i for i in range(n) if i not in set(test_idx.tolist())]
        train_names = [names[i] for i in train_idx]
        train_sources = [combined[nm] for nm in train_names]
        train_targets = [reference for _ in train_sources]
        _, m = _irls_fit(train_sources, train_targets, chroma_init)
        for i in test_idx:
            pred = raw_baseline.apply_color_matrix(combined[names[i]], m)
            cv_de[i] = _mean_de(pred, reference)
        print(f"  fold {fi + 1}/{k} 완료", flush=True)
    cv_mean = float(cv_de.mean())
    diff = no_corr - cv_de
    boot = np.array([diff[rng.randint(0, n, n)].mean() for _ in range(20000)])
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())
    no_corr_mean = float(no_corr.mean())
    pct = (no_corr_mean - cv_mean) / no_corr_mean * 100

    print(f"\n=== IRLS 5-fold CV(n={n}) ===")
    print(f"무보정 평균={no_corr_mean:.3f}  CV 평균={cv_mean:.3f}  개선폭={pct:+.2f}%")
    print(f"부트스트랩 95% CI(paired diff, 20000회)=[{ci_lo:+.3f},{ci_hi:+.3f}]  "
          f"승/패={wins}/{losses}")

    # 최종 배포용: 25장 전체로 IRLS 수렴
    sources = [combined[nm] for nm in names]
    targets = [reference for _ in names]
    final_weights, chart_m = _irls_fit(sources, targets, chroma_init)
    in_sample = float(np.mean([_mean_de(raw_baseline.apply_color_matrix(combined[nm], chart_m),
                                         reference) for nm in names]))
    print(f"\nIRLS 수렴 가중치: {np.round(final_weights, 3).tolist()}")
    print(f"전체 {n}장 pooled in-sample ΔE00 = {in_sample:.4f}")

    dcp_color_matrix_1 = np.linalg.inv(chart_m).T

    with open(OUT_REPORT, encoding="utf-8") as f:
        report = json.load(f)
    report["combined_weighted_irls_cv"] = {
        "n": n, "k": k,
        "no_corr_mean": no_corr_mean,
        "cv_mean": cv_mean,
        "improvement_pct": pct,
        "ci95": [float(ci_lo), float(ci_hi)],
        "wins": wins, "losses": losses,
    }
    report["chart_matrix_in_sample_irls"] = chart_m.tolist()
    report["dcp_color_matrix_1_irls"] = dcp_color_matrix_1.tolist()
    report["chart_matrix_in_sample_delta_e_mean_irls"] = in_sample
    report["irls_final_weights"] = final_weights.tolist()
    report["_comment_irls"] = (
        "2026-09-03: 사용자 승인(\"Irls ㄱㄱ\")으로 combined 25장(kmichels 9 "
        "+ dpreview 16)에 Huber IRLS 적용 - 무채색-4x 초기값에서 시작, "
        "tools/evaluate_dcp_irls_weighted.py의 _irls_fit() 재사용. "
        "combined_weighted_irls_cv가 이 필드의 5-fold CV 근거(non-IRLS "
        "combined_weighted_loo_cv와 같은 fold 분할)."
    )
    # 실제 배포 매트릭스를 IRLS 버전으로 교체
    report["dcp_color_matrix_1"] = dcp_color_matrix_1.tolist()
    report["chart_matrix_in_sample"] = chart_m.tolist()
    report["chart_matrix_in_sample_delta_e_mean"] = in_sample

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
