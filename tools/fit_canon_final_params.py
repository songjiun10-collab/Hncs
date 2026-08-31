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
"""
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
