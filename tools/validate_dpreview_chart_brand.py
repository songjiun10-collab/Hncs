"""
dpreview 스튜디오씬 공용 챠트 데이터베이스(`hybrid_engine/EVALUATION.md`
"dpreview 스튜디오씬 비교위젯" 절 참고)에서 받은 브랜드별 실챠트 RAW로
챠트 기반 컬러매트릭스 검증만 한다(DCP/ICC는 발급하지 않음 - 그건
`tools/fit_leica_sl3p_studio_chart.py`류의 별도 스크립트+사용자 승인이
필요한 단계).

방법론은 Leica SL3-P 챠트 작업(`tools/fit_leica_sl3p_studio_chart.py`)과
동일: 무채색 6패치(인덱스 18-23) 대비 유채색 18패치 3x 가중 최소자승
(`raw_baseline.fit_color_matrix(weights=...)`), k=min(n,5)-fold
교차검증. `tools/validate_chart_pipeline_on_external_camera.py`처럼
ΔE00과 패치별 XYZ RMSE를 항상 같이 내고, 부트스트랩 95% CI(paired diff,
20000회, 고정시드)도 표본 크기와 무관하게 항상 계산한다
(`hybrid_engine/CLAUDE.md` 통계 규칙).

  python3 -m tools.validate_dpreview_chart_brand <RAW 폴더> <brand> <camera 표시명> [확장자]
  예: python3 -m tools.validate_dpreview_chart_brand \
      datasets/sony/contributed/dpreview-a7v-studio-chart-2026-09/raw \
      sony "Sony a7 V" ARW

결과는 <RAW 폴더>/../chart_validation_report.json 에 저장된다(DCP/ICC 없음).
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.io import decode_raw_native

_RAW_EXTS = ("ARW", "CR2", "NEF", "RAF", "ORF", "RW2", "3FR", "DNG")
_MAX_FOLDS = 5
CHROMA_WEIGHT = 3.0


def _mean_de(samples_xyz, reference):
    return float(np.mean(chart_baseline.patch_delta_e_xyz_d50(samples_xyz, reference)))


def _rmse_xyz(samples_xyz, reference):
    return float(np.sqrt(np.mean((samples_xyz - reference) ** 2)))


def main():
    data_dir = sys.argv[1]
    brand = sys.argv[2]
    camera = sys.argv[3]
    ext = sys.argv[4] if len(sys.argv) > 4 else None
    reference = chart_baseline.reference_patches_xyz_d50()

    exts_to_try = [ext] if ext else list(_RAW_EXTS)
    raw_paths = []
    for e in exts_to_try:
        raw_paths = sorted(glob.glob(os.path.join(data_dir, f"*.{e}")))
        if raw_paths:
            break
    if not raw_paths:
        print(f"{data_dir}에 지원 RAW 확장자({', '.join(exts_to_try)}) 없음")
        return

    per_image = {}
    fail = 0
    for i, raw_path in enumerate(raw_paths):
        name = os.path.basename(raw_path)
        try:
            native = decode_raw_native(raw_path)
            samples = chart_baseline.detect_and_sample(native)
        except Exception as e:
            # cv2.mcc가 특정 프레임(shape/노출값 조합으로 추정, 원인 미조사 -
            # Panasonic S1II 챠트 검증 때도 2/20장에서 같은 assertion 발생)
            # 에서 None 대신 cv2.error assertion을 던지는 걸 이 실행 확인 -
            # 검출 실패로 취급하고 계속 진행
            fail += 1
            print(f"  검출 실패(예외 {type(e).__name__}), 제외: {name}")
            continue
        if samples is None:
            fail += 1
            print(f"  검출 실패, 제외: {name}")
            continue
        per_image[name] = samples
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(raw_paths)} (실패 {fail})", flush=True)
    names = sorted(per_image.keys())
    n = len(names)
    print(f"\n검출 성공 {n}/{len(raw_paths)}장 (실패 {fail})")
    if n < 3:
        print("표본 부족, 종료")
        return

    weights = np.array([1.0 if i in range(18, 24) else CHROMA_WEIGHT for i in range(24)])

    no_corr = np.array([_mean_de(per_image[nm], reference) for nm in names])
    no_corr_rmse = np.array([_rmse_xyz(per_image[nm], reference) for nm in names])

    k = min(n, _MAX_FOLDS)
    rng = np.random.RandomState(0)
    folds = np.array_split(rng.permutation(n), k)
    cv_de = np.zeros(n)
    cv_rmse = np.zeros(n)
    for fi, test_idx in enumerate(folds):
        train_idx = [i for i in range(n) if i not in set(test_idx.tolist())]
        train_names = [names[i] for i in train_idx]
        m = raw_baseline.fit_color_matrix(
            [per_image[nm] for nm in train_names],
            [reference] * len(train_names),
            weights=[weights for _ in train_names],
            ridge=0.1,
        )
        for i in test_idx:
            pred = raw_baseline.apply_color_matrix(per_image[names[i]], m)
            cv_de[i] = _mean_de(pred, reference)
            cv_rmse[i] = _rmse_xyz(pred, reference)
        print(f"  fold {fi + 1}/{k} 완료", flush=True)

    diff = no_corr - cv_de
    boot = np.array([diff[rng.randint(0, n, n)].mean() for _ in range(20000)])
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())

    no_corr_mean = float(no_corr.mean())
    cv_mean = float(cv_de.mean())
    no_corr_rmse_mean = float(no_corr_rmse.mean())
    cv_rmse_mean = float(cv_rmse.mean())
    pct = (no_corr_mean - cv_mean) / no_corr_mean * 100
    rmse_pct = (no_corr_rmse_mean - cv_rmse_mean) / no_corr_rmse_mean * 100

    print(f"\n=== {camera} 결과(n={n}, {k}-fold CV, 유채색18패치 {CHROMA_WEIGHT}x 가중) ===")
    print(f"ΔE00 무보정 평균={no_corr_mean:.3f}  CV 평균={cv_mean:.3f}  개선폭={pct:+.2f}%")
    print(f"부트스트랩 95% CI(paired diff, n={n}, 20000회)=[{ci_lo:+.3f},{ci_hi:+.3f}]  "
          f"승/패={wins}/{losses}")
    print(f"RMSE(XYZ) 무보정 평균={no_corr_rmse_mean:.4f}  CV 평균={cv_rmse_mean:.4f}  "
          f"개선폭={rmse_pct:+.2f}%")

    report = {
        "brand": brand,
        "camera": camera,
        "n_images": n,
        "n_failed_detect": fail,
        "images": names,
        "chroma_patch_weight": CHROMA_WEIGHT,
        "k_folds": k,
        "delta_e00_no_correction_mean": no_corr_mean,
        "delta_e00_cv_mean": cv_mean,
        "delta_e00_improvement_pct": pct,
        "delta_e00_bootstrap_ci95": [float(ci_lo), float(ci_hi)],
        "wins": wins,
        "losses": losses,
        "rmse_xyz_no_correction_mean": no_corr_rmse_mean,
        "rmse_xyz_cv_mean": cv_rmse_mean,
        "rmse_xyz_improvement_pct": rmse_pct,
    }
    out_path = os.path.join(os.path.dirname(data_dir.rstrip("/")), "chart_validation_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main()
