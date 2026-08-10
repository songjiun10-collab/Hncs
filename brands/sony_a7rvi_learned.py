"""
apply_sony_a7rvi_learned - Experimental. `apply_sony_a7rvi_look`(brands/sony_a7rvi.py)와 같은
목표를 raw+jpeg 페어에서 픽셀 단위로 직접 학습한 256bin LUT으로
근사한다(raw+jpeg 기반 파라메트릭 채택값) - `hasselblad_learned.py`(파라메트릭 vs 학습 LUT)와
같은 패턴.

**경위(2026-08)**: `tools/evaluate_empirical_tone_curve.py`로 실제 카메라
톤 매핑을 raw+jpeg 페어에서 직접 뽑아 채택된 파라메트릭
`toe_lift/shoulder_start/white_point` 값과 비교했더니, 이 바디는 RMSE=34.72로
실제 곡선과 잘 안 맞음 - 파라메트릭 3파라미터 모양 자체가 실제 곡선과 안 맞는다는
뜻이라, `tools/evaluate_learned_lut.py`로 학습 LUT을 직접 LOO
교차검증했다(exposure_gamma(있으면)->CLAHE까지는 기존과 동일, 그 뒤
`film_curve` 대신 256bin LUT).

개선폭 +9.12%, 26승14패, 부호검정 p=0.0807, 부트스트랩
95% CI [+0.689, +2.341] - 학습 LUT 우세. 최종 LUT은 홀드아웃 없이
전체 40쌍으로 재학습(`tools/fit_final_lut.py`).

`apply_sony_a7rvi_look()`은 이 실험으로 바뀌지 않는다(브랜드 룩 정본 유지) - 둘
다 나란히 둔다. 재현: `python3 -m tools.evaluate_learned_lut --label
"Sony a7R VI" --manifest datasets/sony/sony_new_pairs.csv --raw-dir "/Users/songjiun/local-work" --model "ILCE-7RM6" --clahe-clip 1.25
--toe-lift 0.09 --shoulder-start 0.7 --white-point 0.85`.
"""
import cv2
import numpy as np

_LEARNED_LUT = np.array([
    93, 93, 75, 20, 26, 25, 28, 23, 37, 31, 37, 41, 39, 45, 44, 50,
    46, 49, 50, 51, 53, 53, 56, 57, 58, 58, 61, 62, 60, 62, 62, 65,
    65, 67, 69, 70, 72, 71, 72, 73, 73, 74, 74, 75, 75, 76, 77, 79,
    80, 82, 83, 84, 85, 86, 87, 89, 90, 89, 90, 93, 93, 93, 94, 95,
    98, 98, 98, 99, 100, 101, 101, 102, 103, 104, 104, 104, 106, 105, 106, 108,
    108, 109, 110, 112, 112, 113, 114, 115, 116, 116, 116, 118, 118, 119, 121, 122,
    121, 123, 122, 122, 125, 125, 126, 126, 128, 127, 128, 128, 129, 128, 130, 130,
    132, 132, 134, 133, 134, 135, 136, 136, 138, 139, 143, 151, 154, 150, 152, 156,
    154, 147, 141, 139, 141, 138, 138, 139, 140, 141, 142, 140, 144, 143, 148, 148,
    145, 146, 144, 147, 146, 147, 148, 147, 150, 150, 147, 150, 148, 148, 150, 151,
    148, 149, 152, 150, 152, 153, 150, 152, 154, 154, 155, 154, 155, 155, 154, 160,
    156, 159, 157, 161, 158, 157, 156, 152, 159, 156, 158, 155, 160, 154, 156, 158,
    155, 153, 160, 160, 157, 161, 157, 154, 156, 150, 148, 150, 151, 147, 155, 155,
    153, 163, 156, 157, 159, 160, 156, 167, 152, 144, 149, 141, 161, 151, 157, 147,
    151, 149, 155, 140, 154, 148, 147, 154, 132, 143, 128, 129, 131, 113, 128, 142,
    129, 138, 154, 155, 157, 164, 148, 134, 121, 144, 130, 131, 125, 143, 148, 155,
], dtype=np.uint8)


def apply_sony_a7rvi_learned(img_bgr, clahe_clip=1.25):
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    l = cv2.LUT(l, _LEARNED_LUT)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
