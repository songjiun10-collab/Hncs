"""
apply_hncs_x2dii - Experimental. X2D II 100C 전용 `apply_hncs()`
(brands/hasselblad.py) 변형. exposure_gamma 하나만 0.8->0.7로 바꾼다 -
호출부가 카메라 모델을 판별해 X2D II일 때만 이 함수를 쓰는 걸 전제로
한다(이 함수 자체엔 모델 판별 로직 없음, apply_hncs_learned/
apply_hasselblad_day·night와 같은 패턴).

**경위**: docs/measurements.md "exposure_gamma 세대별 직접 맞대결"
절에서, exposure_gamma=0.8(main)과 0.7(candidate, 별도 브랜치였다가
폐기됨)을 X2D II 41장 실사진 포함 dpreview 95쌍에 직접 맞대결시켰더니
CFV/X2D는 0.8이(p<0.001), X2D II는 0.7이(p<0.001) 통계적으로 확실히
이겼다 - 두 값 다 사전에 존재하던 고정 상수라 이 비교엔 표본 부족으로
인한 과적합 위험이 없다.

**의도적으로 안 가져온 것**:
- shoulder_start=0.82/toe_lift=0.02/white_point=0.95(X2D II 41쌍 자체
  그리드서치 결과) - LOO 부호검정 p=0.060, 학습셋을 5-fold로 줄이면
  p=0.349로 유의성 소실(같은 문서 "X2D II 전용 파라미터 LOO/5-fold"
  절). 41쌍·441콤보 그리드라 과적합 위험이 실제로 있다고 판단해 제외
  - shoulder_start/white_point는 main과 동일하게 유지
- 3x3 컬러 매트릭스 단계 - X2D II 41쌍 자체로 새로 피팅해도
  apply_hncs(main) 톤커브 단독보다 유의하게 나쁨(-13.9%, CI가 0
  안 낀 채 음수, `tools/evaluate_x2dii_color_matrix.py`) - 매트릭스
  경로는 시도했으나 기각

즉 이 함수가 담는 건 "여러 독립 신호(8가설 조사, main-vs-candidate,
LOO)가 공통으로 가리키는 방향 중, **표본 크기에 안정적으로 버티는
부분만**"이다 - 41쌍 전용 그리드서치 최적값 전체를 그대로 옮기지
않았다. `apply_hncs()`(main) 자체는 이 실험으로 바뀌지 않는다.

재현: `python3 -m tools.evaluate_exposure_gamma_x2dii` (95쌍, X2D II
세대만 골라 읽으면 이 함수의 exposure_gamma=0.7 쪽 결과).
"""
import cv2
import numpy as np

from core.curve import film_curve


def apply_hncs_x2dii(img_bgr, toe_lift=0.0, shoulder_start=0.5,
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
