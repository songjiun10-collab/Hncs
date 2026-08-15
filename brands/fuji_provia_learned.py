"""
apply_provia_learned - Experimental. `apply_provia`(brands/fuji.py)와 같은
목표를 raw+jpeg 페어에서 픽셀 단위로 직접 학습한 256bin LUT으로
근사한다(GFX100RF/X-T30 III/GFX50S II 3바디 통합 파라메트릭 채택값) - `hasselblad_learned.py`(파라메트릭 vs 학습 LUT)와
같은 패턴.

**경위(2026-08)**: `tools/evaluate_empirical_tone_curve.py`로 실제 카메라
톤 매핑을 raw+jpeg 페어에서 직접 뽑아 채택된 파라메트릭
`toe_lift/shoulder_start/white_point` 값과 비교했더니, 이 바디는 RMSE=26.31로
실제 곡선과 잘 안 맞음 - 파라메트릭 3파라미터 모양 자체가 실제 곡선과 안 맞는다는
뜻이라, `tools/evaluate_learned_lut.py`로 학습 LUT을 직접 LOO
교차검증했다(exposure_gamma(있으면)->CLAHE까지는 기존과 동일, 그 뒤
`film_curve` 대신 256bin LUT).

개선폭 +20.42%, 52승15패, 부호검정 p=0.0000, 부트스트랩
95% CI [+1.959, +3.365] - 학습 LUT 우세. 최종 LUT은 홀드아웃 없이
전체 67쌍으로 재학습(`tools/fit_final_lut.py`).

`apply_provia()`은 이 실험으로 바뀌지 않는다(브랜드 룩 정본 유지) - 둘
다 나란히 둔다. 재현: `python3 -m tools.evaluate_learned_lut --label
"Fuji Provia 3바디 통합" --manifest datasets/fuji/fuji_new_pairs.csv --raw-dir "/Users/songjiun/local-work" --model "GFX100RF" --model "X-T30 III" --model "GFX50S II" --film-mode "F0/Standard (Provia)" --clahe-clip 1.25
--toe-lift 0.0 --shoulder-start 0.82 --white-point 1.0`.
"""
import numpy as np

from core.engine import apply_learned_lut_look

_LEARNED_LUT = np.array([
    9, 9, 2, 10, 9, 12, 14, 20, 24, 24, 26, 30, 30, 32, 33, 37,
    37, 41, 42, 45, 46, 48, 49, 51, 52, 54, 55, 55, 57, 59, 60, 61,
    63, 64, 66, 66, 67, 69, 69, 70, 71, 72, 73, 74, 76, 77, 78, 79,
    81, 82, 84, 85, 87, 87, 89, 89, 91, 91, 92, 93, 94, 95, 97, 98,
    100, 100, 102, 103, 105, 105, 106, 108, 108, 110, 111, 112, 113, 114, 116, 116,
    118, 119, 120, 121, 123, 124, 124, 126, 127, 127, 129, 130, 132, 131, 133, 134,
    135, 136, 137, 137, 139, 140, 141, 141, 144, 143, 145, 146, 146, 147, 148, 148,
    149, 149, 150, 150, 152, 152, 154, 154, 155, 156, 158, 157, 158, 158, 158, 160,
    161, 162, 163, 164, 165, 165, 167, 166, 167, 168, 168, 168, 169, 169, 170, 169,
    170, 172, 173, 173, 172, 173, 175, 176, 176, 175, 177, 179, 179, 181, 181, 183,
    182, 183, 182, 184, 185, 185, 186, 187, 185, 189, 189, 190, 190, 190, 190, 192,
    191, 192, 192, 192, 193, 192, 195, 190, 192, 190, 192, 194, 195, 196, 196, 197,
    199, 202, 204, 207, 208, 209, 210, 210, 213, 215, 217, 216, 217, 216, 220, 219,
    220, 219, 220, 222, 225, 225, 228, 225, 228, 230, 227, 227, 227, 224, 229, 231,
    229, 232, 232, 230, 228, 232, 231, 232, 228, 229, 230, 232, 231, 230, 233, 227,
    227, 231, 229, 224, 229, 230, 227, 230, 233, 235, 236, 234, 238, 241, 236, 228,
], dtype=np.uint8)


def apply_provia_learned(img_bgr, clahe_clip=1.25):
    return apply_learned_lut_look(img_bgr, _LEARNED_LUT, clahe_clip)
