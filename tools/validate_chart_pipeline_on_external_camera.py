"""
`hybrid_engine`의 챠트 기반 파이프라인(`chart_baseline.detect_and_sample()`
+ `raw_baseline.fit_color_matrix()`)이 하셀블라드 전용으로 우연히 맞는
게 아니라 진짜 일반화되는지, 완전히 다른 카메라+RAW포맷+실측 다중조명/
다중장면 데이터로 검증한다(2026-09-02, 사용자가 직접 링크 준 리드
"vision.middlebury.edu/color/data" 등 조사 중 York University의
raw_2_raw/illuminant 데이터셋 발견 -
`yorkucvil.github.io/projects/public_html/raw_2_raw/`,
`yorkucvil.github.io/projects/public_html/illuminant/illuminant.html`).

**중요한 한계**: 이 스크립트가 검증하는 카메라(Sony A57/Canon 1Ds Mark
III/Nikon D40)는 전부 2012~2013년식 바디라 이 프로젝트가 지금
배포하는 현행 바디와 센서 세대가 완전히 다르다 - **배포된 프로필을
개선하는 게 아니라 파이프라인 자체의 방법론 검증**용도다. 실제 배포
매트릭스로 쓰지 않는다.

방법론: k=min(n,5)-fold 교차검증(표본이 5개뿐이면 사실상
leave-one-out과 같아짐) - 하셀블라드 챠트 작업과 같은 논리를 확장한
것. ΔE00(patch_delta_e_xyz_d50, 지각 가중)과 패치별 XYZ RMSE(가중
없음) 둘 다 낸다 - Nikon D40 n=5 검증(raw_2_raw)에서 ΔE00은
개선됐는데 RMSE는 거의 안 줄어드는 괴리가 있었고, 같은 카메라를
n=117(illuminant 데이터셋)로 재검증하니 그 괴리가 표본 크기 문제였다는
게 드러났다(`hybrid_engine/EVALUATION.md` 참고) - 그래서 두 지표를
항상 같이 낸다. 부트스트랩 95% CI(paired diff, 20000회)도 표본
크기와 무관하게 항상 계산한다 - n이 작으면 넓은 CI로 그 자체가
신호가 약하다는 걸 보여준다(과거 이 프로젝트가 "n=5라 CI 불가능"이라고
잘못 기록했던 적이 있음 - 계산 자체는 항상 된다).

  python3 -m tools.validate_chart_pipeline_on_external_camera <데이터_디렉토리> [확장자]
  예: python3 -m tools.validate_chart_pipeline_on_external_camera \
      /path/to/Colorchart_1/SonyA57
  확장자 생략 시 ARW/CR2/NEF/RAF/ORF/RW2/3FR/DNG 순으로 찾아서 첫 매치 사용."""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.io import decode_raw_native

_RAW_EXTS = ("ARW", "CR2", "NEF", "RAF", "ORF", "RW2", "3FR", "DNG")
_MAX_FOLDS = 5


def _mean_de(samples_xyz, reference):
    return float(np.mean(chart_baseline.patch_delta_e_xyz_d50(samples_xyz, reference)))


def _rmse_xyz(samples_xyz, reference):
    return float(np.sqrt(np.mean((samples_xyz - reference) ** 2)))


def main():
    data_dir = sys.argv[1]
    ext = sys.argv[2] if len(sys.argv) > 2 else None
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
        native = decode_raw_native(raw_path)
        samples = chart_baseline.detect_and_sample(native)
        if samples is None:
            fail += 1
            continue
        per_image[name] = samples
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(raw_paths)} (실패 {fail})", flush=True)
    names = sorted(per_image.keys())
    n = len(names)
    print(f"\n검출 성공 {n}/{len(raw_paths)}장 (실패 {fail})")
    if n < 3:
        print("표본 부족, 종료")
        return

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
        m = raw_baseline.fit_color_matrix([per_image[nm] for nm in train_names],
                                           [reference] * len(train_names), ridge=0.1)
        for i in test_idx:
            pred = raw_baseline.apply_color_matrix(per_image[names[i]], m)
            cv_de[i] = _mean_de(pred, reference)
            cv_rmse[i] = _rmse_xyz(pred, reference)
        print(f"  fold {fi+1}/{k} 완료", flush=True)

    diff = no_corr - cv_de
    boot = np.array([diff[rng.randint(0, n, n)].mean() for _ in range(20000)])
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())

    no_corr_mean = float(no_corr.mean())
    cv_mean = float(cv_de.mean())
    no_corr_rmse_mean = float(no_corr_rmse.mean())
    cv_rmse_mean = float(cv_rmse.mean())

    print(f"\n=== 결과(n={n}, {k}-fold CV) ===")
    print(f"ΔE00 무보정 평균={no_corr_mean:.3f}  CV 평균={cv_mean:.3f}  "
          f"개선폭={(no_corr_mean - cv_mean) / no_corr_mean * 100:+.2f}%")
    print(f"부트스트랩 95% CI(paired diff, n={n}, 20000회)=[{ci_lo:+.3f},{ci_hi:+.3f}]  "
          f"승/패={wins}/{losses}")
    print(f"RMSE(XYZ) 무보정 평균={no_corr_rmse_mean:.4f}  CV 평균={cv_rmse_mean:.4f}  "
          f"개선폭={(no_corr_rmse_mean - cv_rmse_mean) / no_corr_rmse_mean * 100:+.2f}%")


if __name__ == "__main__":
    main()
