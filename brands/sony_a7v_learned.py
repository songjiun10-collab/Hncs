"""
apply_sony_a7v_learned - Experimental. `apply_sony_a7v_look`(brands/sony_a7v.py)와 같은
목표를 raw+jpeg 페어에서 픽셀 단위로 직접 학습한 256bin LUT으로
근사한다(raw+jpeg 기반 파라메트릭 채택값) - `hasselblad_learned.py`(파라메트릭 vs 학습 LUT)와
같은 패턴.

**경위(2026-08)**: `tools/evaluate_empirical_tone_curve.py`로 실제 카메라
톤 매핑을 raw+jpeg 페어에서 직접 뽑아 채택된 파라메트릭
`toe_lift/shoulder_start/white_point` 값과 비교했더니, 이 바디는 RMSE=26.42로
실제 곡선과 잘 안 맞음 - 파라메트릭 3파라미터 모양 자체가 실제 곡선과 안 맞는다는
뜻이라, `tools/evaluate_learned_lut.py`로 학습 LUT을 직접 LOO
교차검증했다(exposure_gamma(있으면)->CLAHE까지는 기존과 동일, 그 뒤
`film_curve` 대신 256bin LUT).

개선폭 +11.10%, 45승16패, 부호검정 p=0.0003, 부트스트랩
95% CI [+1.188, +2.312] - 학습 LUT 우세. 최종 LUT은 홀드아웃 없이
전체 61쌍으로 재학습(`tools/fit_final_lut.py`).

`apply_sony_a7v_look()`은 이 실험으로 바뀌지 않는다(브랜드 룩 정본 유지) - 둘
다 나란히 둔다. 재현: `python3 -m tools.evaluate_learned_lut --label
"Sony a7V" --manifest datasets/sony/sony_new_pairs.csv --raw-dir "/Users/songjiun/local-work" --model "ILCE-7M5" --clahe-clip 1.25
--toe-lift 0.06 --shoulder-start 0.82 --white-point 1.0`.
"""
import cv2
import numpy as np

_LEARNED_LUT = np.array([
    99, 99, 82, 24, 24, 27, 25, 35, 35, 38, 35, 37, 41, 41, 42, 44,
    46, 49, 51, 53, 54, 54, 56, 57, 60, 60, 60, 61, 61, 63, 64, 65,
    65, 67, 67, 69, 71, 72, 73, 73, 74, 73, 73, 74, 75, 75, 77, 78,
    79, 80, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 89, 90, 90, 92,
    93, 94, 95, 97, 97, 98, 99, 99, 100, 102, 102, 104, 104, 105, 105, 107,
    108, 109, 110, 111, 112, 112, 113, 114, 115, 117, 117, 118, 119, 120, 121, 121,
    122, 123, 125, 124, 126, 127, 127, 128, 129, 127, 129, 130, 131, 132, 132, 134,
    135, 136, 136, 136, 137, 138, 138, 138, 139, 139, 141, 141, 142, 143, 144, 145,
    145, 146, 149, 147, 150, 149, 150, 150, 151, 151, 152, 153, 153, 153, 155, 156,
    156, 156, 157, 157, 157, 156, 157, 157, 154, 156, 156, 159, 160, 159, 161, 160,
    162, 160, 163, 161, 164, 163, 168, 168, 168, 172, 172, 170, 174, 173, 174, 174,
    174, 176, 173, 174, 171, 172, 174, 175, 177, 177, 176, 180, 178, 179, 178, 180,
    180, 176, 179, 181, 177, 178, 177, 178, 181, 180, 179, 181, 181, 178, 187, 182,
    182, 181, 184, 180, 187, 179, 188, 189, 191, 188, 190, 186, 192, 188, 198, 194,
    201, 198, 196, 195, 198, 199, 201, 201, 204, 203, 198, 204, 201, 199, 196, 200,
    196, 195, 192, 194, 188, 188, 196, 200, 207, 210, 194, 196, 197, 202, 204, 231,
], dtype=np.uint8)


def apply_sony_a7v_learned(img_bgr, clahe_clip=1.25):
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    l = cv2.LUT(l, _LEARNED_LUT)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
