"""
`hybrid_engine`의 챠트 기반 파이프라인(`chart_baseline.detect_and_sample()`
+ `raw_baseline.fit_color_matrix()`)이 하셀블라드 전용으로 우연히 맞는
게 아니라 진짜 일반화되는지, 완전히 다른 카메라+RAW포맷+실측 다중조명
데이터로 검증한다(2026-09-02, 사용자가 직접 링크 준 리드
"vision.middlebury.edu/color/data" 등 조사 중 York University의
raw_2_raw 데이터셋 발견 - `yorkucvil.github.io/projects/public_html/raw_2_raw/`).

**중요한 한계**: Sony A57은 2012년식 바디라 이 프로젝트가 지금 배포하는
현행 Sony 바디(a1 II 등)와 센서 세대가 완전히 다르다 - 이 스크립트는
**배포된 프로필을 개선하는 게 아니라 파이프라인 자체의 방법론 검증**
용도다. 실제 배포 매트릭스로 쓰지 않는다.

데이터: `Colorchart_1/SonyA57/`(York raw_2_raw 캘리브레이션 세트,
Sync.com `https://ln.sync.com/dl/293c43970/...`에서 261MB
`Colorchart_1.zip` 전체를 받아 SonyA57 폴더만 남김 - Canon
1Ds Mark III/Nikon D40 부분은 삭제). X-Rite ColorChecker
Color Rendition(24패치, 좌측)과 Digital ColorChecker SG(140패치,
우측)가 한 프레임에 같이 찍혀있고(24+140=164, `.mat` 파일의
raw-RGB 164행과 일치), 5개 실제 조명(FL_CL/FL_WL/IN_E/IN_F/LE) x
ARW+JPG+MAT. 이 스크립트는 `.mat`은 안 쓰고 ARW를 직접
`decode_raw_native()`로 디코드해서 우리 `detect_and_sample()`
(MCC24, 표준 24패치 왼쪽 챠트만 타깃)로 검출한다 - 파이프라인 전체를
실제로 돌리는 게 목적이라 사전 추출된 값을 재사용하지 않는다.

방법론: 조명 5개 중 하나씩 held-out(leave-one-illuminant-out), 나머지
4개로 매트릭스 피팅해서 held-out 조명에 적용 - 하셀블라드 챠트
작업과 같은 논리를 조명 축으로 확장한 것.

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


def _mean_de(samples_xyz, reference):
    return float(np.mean(chart_baseline.patch_delta_e_xyz_d50(samples_xyz, reference)))


_RAW_EXTS = ("ARW", "CR2", "NEF", "RAF", "ORF", "RW2", "3FR", "DNG")


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
    for raw_path in raw_paths:
        name = os.path.basename(raw_path)
        print(f"디코드+검출 중: {name}", flush=True)
        native = decode_raw_native(raw_path)
        samples = chart_baseline.detect_and_sample(native)
        if samples is None:
            print(f"  검출 실패, 제외")
            continue
        per_image[name] = samples
    names = sorted(per_image.keys())
    n = len(names)
    print(f"\n검출 성공 {n}/{len(raw_paths)}장")
    if n < 3:
        print("표본 부족, 종료")
        return

    no_corr = {nm: _mean_de(per_image[nm], reference) for nm in names}
    print("\n무보정(매트릭스 없음) 조명별 ΔE00:")
    for nm in names:
        print(f"  {nm}: {no_corr[nm]:.3f}")
    no_corr_mean = float(np.mean(list(no_corr.values())))
    print(f"평균: {no_corr_mean:.3f}")

    loo = {}
    for held_out in names:
        train_names = [nm for nm in names if nm != held_out]
        train_sources = [per_image[nm] for nm in train_names]
        train_targets = [reference for _ in train_sources]
        m = raw_baseline.fit_color_matrix(train_sources, train_targets, ridge=0.1)
        pred = raw_baseline.apply_color_matrix(per_image[held_out], m)
        loo[held_out] = _mean_de(pred, reference)
    print("\n매트릭스 LOO(조명별 홀드아웃) ΔE00:")
    for nm in names:
        print(f"  {nm}: {loo[nm]:.3f}")
    loo_mean = float(np.mean(list(loo.values())))
    print(f"평균: {loo_mean:.3f}")
    print(f"개선폭: {(no_corr_mean - loo_mean) / no_corr_mean * 100:+.2f}%")


if __name__ == "__main__":
    main()
