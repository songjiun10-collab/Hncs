"""
apply_hncs_x1d50c - Experimental. Hasselblad X1D-50c 전용 `apply_hncs()`
(brands/hasselblad.py) 변형 - apply_hncs_x2dii와 같은 패턴(호출부가 카메라
모델을 판별해 X1D-50c일 때만 이 함수를 쓰는 걸 전제, 이 함수 자체엔 모델
판별 로직 없음).

**경위(2026-08)**: 로컬 raw+jpeg 라이브러리에 X1D-50c 페어 20장이 처음
추가돼서(EXIF Software가 펌웨어 버전 문자열만 있고 Adobe 서명 없음 -
편집 오염 없음 확인), ΔE00을 직접 목적함수로 그리드서치+LOO를 X2D II와
동일한 방식으로 돌렸다(`tools/evaluate_hasselblad_body_de00_grid.py`,
저해상도(200px) 폴드별 콤보 선택 -> 400px 확정, 이어서
`tools/evaluate_native_pixel_confirm.py`로 원본 해상도(max_dim=3000)
재확인) - `apply_hncs()`(main) 대비:

| 검증 단계 | 개선폭 | 승/패 | 부호검정 p | 부트스트랩 95% CI |
|---|---|---|---|---|
| LOO(200px 선택/400px 평가) | +6.69% | 17/3 | 0.0026 | [+0.301, +0.972] |
| 원본 픽셀(max_dim=3000) | +5.96% | 17/3 | 0.0026 | [+0.309, +0.906] |

두 단계가 다운샘플 왜곡 없이 거의 일치 - 20/20 폴드가 만장일치로 같은
조합을 선택했다: **`exposure_gamma=0.7, toe_lift=0.0, shoulder_start=0.82,
white_point=1.0`**. X2D II(exposure_gamma=0.6)보다 노출 리프트가 약간
약하고, shoulder_start=0.82는 X2D II(0.58)보다 하이라이트 롤오프가
main(0.5)보다도 훨씬 길다 - 별개 센서/펌웨어 세대라 X2D II 값을 그대로
가져오지 않고 이 20장으로 독립적으로 다시 찾은 값.

표본이 20장으로 X2D II(70장)보다 작아 통계적 견고함이 상대적으로
약하다는 점은 유의 - 이후 X1D-50c 페어가 더 추가되면 재검증 권장. 재현:
`python3 -m tools.evaluate_hasselblad_body_de00_grid --label
"Hasselblad X1D-50c" --manifest datasets/hasselblad/hasselblad_new_pairs.csv
--raw-dir "/Users/songjiun/local-work/raw pair" --model "Hasselblad X1D-50c"`
"""
import cv2
import numpy as np

from core.curve import film_curve


def apply_hncs_x1d50c(img_bgr, toe_lift=0.0, shoulder_start=0.82,
                       white_point=1.0, clahe_clip=1.25, exposure_gamma=0.7):
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    if exposure_gamma != 1.0:
        x = np.arange(256, dtype=np.float32) / 255.0
        exp_lut = np.clip((x ** exposure_gamma) * 255, 0, 255).astype(np.uint8)
        l = cv2.LUT(l, exp_lut)

    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
