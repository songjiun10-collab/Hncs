"""
apply_sigma_fpl_learned - Experimental. `apply_sigma_fpl_look`(brands/sigma_fpl.py)와 같은
목표를 raw+jpeg 페어에서 픽셀 단위로 직접 학습한 256bin LUT으로
근사한다(raw+jpeg 기반 파라메트릭 채택값) - `hasselblad_learned.py`(파라메트릭 vs 학습 LUT)와
같은 패턴.

**경위(2026-08)**: `tools/evaluate_empirical_tone_curve.py`로 실제 카메라
톤 매핑을 raw+jpeg 페어에서 직접 뽑아 채택된 파라메트릭
`toe_lift/shoulder_start/white_point` 값과 비교했더니, 이 바디는 RMSE=25.77로
실제 곡선과 잘 안 맞음 - 파라메트릭 3파라미터 모양 자체가 실제 곡선과 안 맞는다는
뜻이라, `tools/evaluate_learned_lut.py`로 학습 LUT을 직접 LOO
교차검증했다(exposure_gamma(있으면)->CLAHE까지는 기존과 동일, 그 뒤
`film_curve` 대신 256bin LUT).

개선폭 +17.01%, 26승6패, 부호검정 p=0.0005, 부트스트랩
95% CI [+1.386, +2.813] - 학습 LUT 우세. 최종 LUT은 홀드아웃 없이
전체 32쌍으로 재학습(`tools/fit_final_lut.py`).

`apply_sigma_fpl_look()`은 이 실험으로 바뀌지 않는다(브랜드 룩 정본 유지) - 둘
다 나란히 둔다. 재현: `python3 -m tools.evaluate_learned_lut --label
"Sigma fp L" --manifest datasets/sigma/sigma_new_pairs.csv --raw-dir "/Users/songjiun/local-work" --model "SIGMA fp L" --clahe-clip 1.25
--toe-lift 0.02 --shoulder-start 0.82 --white-point 1.0`.
"""
import numpy as np

from core.engine import apply_learned_lut_look

_LEARNED_LUT = np.array([
    6, 6, 8, 8, 8, 11, 13, 18, 19, 20, 23, 25, 28, 28, 31, 33,
    35, 36, 38, 40, 41, 43, 44, 45, 48, 49, 50, 51, 52, 53, 55, 56,
    59, 58, 61, 61, 62, 63, 64, 64, 65, 67, 67, 68, 69, 71, 71, 72,
    73, 74, 75, 77, 78, 78, 80, 81, 82, 83, 84, 85, 86, 88, 88, 89,
    89, 91, 92, 94, 95, 95, 96, 98, 99, 100, 101, 102, 103, 105, 107, 107,
    108, 109, 110, 111, 112, 114, 114, 116, 117, 119, 119, 121, 121, 124, 125, 125,
    128, 128, 128, 129, 130, 132, 132, 133, 134, 135, 137, 138, 138, 139, 140, 141,
    143, 145, 146, 147, 149, 150, 152, 150, 151, 151, 152, 153, 154, 156, 158, 159,
    159, 161, 162, 161, 164, 165, 167, 166, 168, 169, 170, 171, 172, 173, 175, 175,
    178, 179, 179, 181, 181, 181, 182, 182, 183, 186, 185, 184, 185, 188, 189, 188,
    190, 190, 194, 193, 194, 195, 195, 198, 198, 199, 199, 200, 201, 202, 201, 201,
    204, 202, 204, 203, 205, 204, 207, 205, 206, 207, 209, 209, 211, 212, 212, 212,
    213, 214, 214, 215, 215, 216, 217, 219, 219, 220, 221, 222, 223, 222, 222, 224,
    226, 226, 228, 227, 229, 231, 228, 228, 231, 232, 232, 233, 235, 234, 238, 236,
    240, 238, 238, 239, 240, 238, 238, 239, 237, 239, 238, 236, 236, 238, 236, 238,
    236, 238, 235, 237, 237, 240, 239, 240, 239, 244, 246, 248, 246, 244, 239, 247,
], dtype=np.uint8)


def apply_sigma_fpl_learned(img_bgr, clahe_clip=1.25):
    return apply_learned_lut_look(img_bgr, _LEARNED_LUT, clahe_clip)
