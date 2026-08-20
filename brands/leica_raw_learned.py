"""
apply_leica_raw_learned - Experimental. `apply_leica_raw_look`(brands/leica_raw.py)와 같은
목표를 raw+jpeg 페어에서 픽셀 단위로 직접 학습한 256bin LUT으로
근사한다(SL3-P/Q3 43/SL2/M10/SL2-S 5바디 통합 파라메트릭 채택값) - `hasselblad_learned.py`(파라메트릭 vs 학습 LUT)와
같은 패턴.

**경위(2026-08)**: `tools/evaluate_empirical_tone_curve.py`로 실제 카메라
톤 매핑을 raw+jpeg 페어에서 직접 뽑아 채택된 파라메트릭
`toe_lift/shoulder_start/white_point` 값과 비교했더니, 이 바디는 RMSE=14.59로
비교적 잘 맞는 편 - 파라메트릭 3파라미터 모양 자체가 실제 곡선과 안 맞는다는
뜻이라, `tools/evaluate_learned_lut.py`로 학습 LUT을 직접 LOO
교차검증했다(exposure_gamma(있으면)->CLAHE까지는 기존과 동일, 그 뒤
`film_curve` 대신 256bin LUT).

개선폭 +12.56%, 153승63패, 부호검정 p=0.0000, 부트스트랩
95% CI [+0.868, +1.333] - 학습 LUT 우세. 최종 LUT은 홀드아웃 없이
전체 216쌍으로 재학습(`tools/fit_final_lut.py`).

`apply_leica_raw_look()`은 이 실험으로 바뀌지 않는다(브랜드 룩 정본 유지) - 둘
다 나란히 둔다. 재현: `python3 -m tools.evaluate_learned_lut --label
"Leica 5바디 통합" --manifest datasets/leica/leica_new_pairs.csv --raw-dir "/Users/songjiun/local-work" --model "LEICA SL3-P" --model "LEICA Q3 43" --model "LEICA SL2" --model "LEICA M10" --model "LEICA SL2-S" --clahe-clip 1.25
--toe-lift 0.0 --shoulder-start 0.82 --white-point 1.0`.
"""
import numpy as np

from core.engine import apply_learned_lut_look

_LEARNED_LUT = np.array([
    11, 11, 4, 5, 6, 5, 7, 8, 11, 11, 11, 13, 14, 14, 16, 18,
    19, 19, 21, 22, 24, 26, 27, 28, 30, 31, 32, 33, 35, 36, 37, 39,
    40, 42, 43, 44, 45, 47, 48, 50, 51, 52, 53, 54, 55, 57, 58, 59,
    61, 62, 64, 65, 67, 68, 69, 70, 71, 72, 74, 74, 76, 77, 79, 79,
    81, 82, 84, 84, 86, 87, 88, 89, 91, 93, 94, 95, 96, 97, 99, 100,
    101, 102, 103, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 116,
    118, 119, 119, 120, 121, 122, 124, 124, 125, 126, 127, 128, 129, 130, 131, 132,
    133, 134, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 143, 144, 145, 147,
    147, 148, 149, 150, 151, 151, 152, 153, 154, 155, 156, 156, 158, 158, 159, 160,
    160, 161, 162, 163, 164, 164, 165, 165, 166, 167, 168, 168, 169, 169, 170, 171,
    172, 173, 173, 174, 174, 175, 176, 176, 177, 178, 178, 178, 179, 179, 180, 180,
    181, 183, 183, 184, 185, 186, 187, 188, 188, 189, 189, 191, 191, 193, 193, 195,
    195, 196, 197, 197, 198, 199, 200, 201, 201, 202, 203, 205, 205, 205, 206, 207,
    208, 209, 209, 210, 211, 212, 213, 214, 215, 216, 217, 217, 218, 220, 221, 221,
    222, 223, 224, 223, 225, 225, 226, 227, 228, 227, 230, 230, 232, 229, 232, 233,
    234, 234, 234, 236, 236, 236, 238, 240, 239, 243, 242, 246, 243, 249, 243, 251,
], dtype=np.uint8)


def apply_leica_raw_learned(img_bgr, clahe_clip=1.25):
    return apply_learned_lut_look(img_bgr, _LEARNED_LUT, clahe_clip)
