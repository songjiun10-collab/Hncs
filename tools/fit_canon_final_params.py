"""
/goal - fit_body_matrix_plus_tone_de00.py(--chroma)의 LOO 검증이 이미
통계적으로 견고한 개선(23.11->17.24, +13.64%~+25%대 조합의 부분 결과들
포함해서 종합 p<0.001 수준)을 확인했지만 그동안 "측정만" 하고 실제
apply_canon_look() 대신 쓸 배포용 함수로 만들지 않았다. 이 스크립트는
전체 139쌍(LOO 폴드 분할 없이)으로 최종 매트릭스+톤+채도 파라미터를
한 번 피팅해서 brands/canon.py에 새 함수로 박아넣을 값을 낸다 - 이미
LOO로 일반화 성능은 검증됐으니(위 스크립트), 이건 "그 검증된 파라미터
계열을 실제 배포용 상수로 확정"하는 마지막 단계일 뿐 새로운 통계
주장이 아니다.

  python3 -m tools.fit_canon_final_params

**정정(2026-08-31) - 잘못된 입력 공간, 배포에 쓰지 말 것**: 위 매트릭스는
`fit_body_matrix_plus_tone_de00.py`의 `_decode_one()`을 그대로 갖다 써서
raw 네이티브 순수 선형(AsShotNeutral 수동 화이트밸런스, libraw 컬러매트릭스
미적용) 공간에 피팅됐다. 그런데 실제 `apply_canon_look()`/
`apply_canon_raw_look()`이 받는 입력은 `load_neutral_render()`가 만드는
다른 공간(libraw `use_camera_wb=True`, `gamma=(2.222,4.5)`, 8비트
sRGB 감마 BGR - libraw 자체 컬러매트릭스가 이미 적용된 값)이다. 이
스크립트가 낸 매트릭스는 그 입력 공간과 안 맞아 배포에 쓸 수 없다 -
실제 배포된 `apply_canon_raw_look()`은 `tools/fit_canon_deployable_pipeline.py`
(같은 방법론, 입력 디코드만 `load_neutral_render()`로 교체)로 다시
피팅한 값이다. 이 스크립트는 삭제하지 않고 "잘못된 시도"로 남겨둔다
(프로젝트 관례 - 실패한 시도도 기록). 배포용 재현은
`python3 -m tools.fit_canon_deployable_pipeline --loo`."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.fit_body_matrix_plus_tone_de00 import (
    collect_contributed_pairs, _decode_one, fit_color_matrix, mean_delta_e,
    apply_tone_stage, apply_chroma_lut, TONE_TOE_LIFT, TONE_SHOULDER_START,
    TONE_WHITE_POINT, TONE_CLAHE_CLIP, SAT_MULT_GRID, HUE_SHIFT_GRID,
)
import multiprocessing
import numpy as np


def main():
    rows = collect_contributed_pairs("canon", None)
    print(f"canon: manifest {len(rows)}개", flush=True)
    pairs = []
    with multiprocessing.Pool(3) as pool:
        for name, wb_rgb, target, err in pool.imap_unordered(_decode_one, rows):
            if err:
                continue
            pairs.append(dict(name=name, wb_rgb=wb_rgb, target=target))
    n = len(pairs)
    print(f"디코드 완료: {n}개", flush=True)

    matrix = fit_color_matrix([p['wb_rgb'] for p in pairs], [p['target'] for p in pairs], ridge=1.0)
    print("최종 매트릭스(전체 표본 피팅):")
    print(matrix.tolist())

    toned = [apply_tone_stage(np.clip(p['wb_rgb'] @ matrix, 0.0, None)) for p in pairs]

    best_de, best_params = float("inf"), (1.0, 0.0)
    for sm in SAT_MULT_GRID:
        for hs in HUE_SHIFT_GRID:
            des = [mean_delta_e(apply_chroma_lut(t, sm, hs), p['target']) for t, p in zip(toned, pairs)]
            mde = float(np.mean(des))
            if mde < best_de:
                best_de, best_params = mde, (sm, hs)

    print(f"\n최종 채도/색조: sat_mult={best_params[0]:.3f}, hue_shift={best_params[1]:+.2f}")
    print(f"전체 표본(in-sample) ΔE00={best_de:.3f}")
    print(f"\n톤 파라미터(고정): toe_lift={TONE_TOE_LIFT}, shoulder_start={TONE_SHOULDER_START}, "
          f"white_point={TONE_WHITE_POINT}, clahe_clip={TONE_CLAHE_CLIP}")


if __name__ == "__main__":
    main()
