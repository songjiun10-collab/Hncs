"""
apply_sigma_raw_matrix_look - `apply_sigma_raw_look()`(brands/sigma_raw.py,
톤커브 4파라미터만, 매트릭스 없음)에 Canon/Sony와 같은 방법론으로 3x3
컬러매트릭스+채도/색조 LUT을 얹은 버전. `brands/sony_raw_matrix.py`와
같은 조사(2026-09-02, 사용자 지시 "소니같은거도 다 매트릭스 만들어").

`tools/fit_brand_matrix_chroma_pipeline.py sigma --loo`로 Sigma raw+jpeg
83쌍(디코드 성공) - 톤커브는 `apply_sigma_raw_look()`이 이미 확정한 값
(toe=0.02/ss=0.82/wp=1.0/clip=3.0, `brands/sigma_raw.py` 참고) 그대로
두고 매트릭스+채도/색조만 새로 5-fold LOO 피팅해서 **실제 배포된
`apply_sigma_raw_look()`과 직접 맞대결**했다.

**결과**: 기존(톤커브만) ΔE00=14.647 대비 매트릭스+채도 LOO
ΔE00=13.305, **+9.16%**, 60승23패, 부호검정 p=0.0001, 부트스트랩 95%
CI [+0.760,+1.888](0 미포함) - Sony(+9.11%)와 거의 같은 개선폭. 전체
표본(홀드아웃 없이) 최종 재피팅: in-sample ΔE00=13.102(LOO 13.305와
큰 차이 없어 과적합 아님), sat_mult=1.20, hue_shift=0.0.

재현: `python3 -m tools.fit_brand_matrix_chroma_pipeline sigma --loo`."""
import colour
import cv2
import numpy as np

from core.curve import film_curve
from core.lut import ensure_uint8

_MATRIX = np.array([
    [1.948871515027226, 0.7979243173094206, 0.7240622106069871],
    [-0.38148846610463455, 0.4008746325398964, -0.6896331769464288],
    [0.24758038402294644, 0.5974966855870354, 1.7473831512064615],
])
_SAT_MULT = 1.2000
_HUE_SHIFT = 0.0000
_TONE_TOE_LIFT = 0.02
_TONE_SHOULDER_START = 0.82
_TONE_WHITE_POINT = 1.0
_TONE_CLAHE_CLIP = 3.0


def apply_sigma_raw_matrix_look(img_bgr):
    img = ensure_uint8(img_bgr)
    linear = colour.cctf_decoding(img[:, :, ::-1].astype(np.float64) / 255.0, function="sRGB")
    matrixed = np.clip(linear @ _MATRIX, 0.0, None)

    srgb = colour.cctf_encoding(np.clip(matrixed, 0.0, 1.0), function="sRGB")
    u8_bgr = (srgb * 255.0 + 0.5).astype(np.uint8)[:, :, ::-1]
    lab = cv2.cvtColor(u8_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=_TONE_CLAHE_CLIP, tileGridSize=(8, 8))
    l = clahe.apply(l)
    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift=_TONE_TOE_LIFT, shoulder_start=_TONE_SHOULDER_START,
                              white_point=_TONE_WHITE_POINT) * 255, 0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)
    toned_bgr = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    toned_linear = colour.cctf_decoding(toned_bgr[:, :, ::-1].astype(np.float64) / 255.0, function="sRGB")

    clipped = np.clip(toned_linear, 0.0, 1.0).astype(np.float32)
    hsv = cv2.cvtColor(clipped, cv2.COLOR_RGB2HSV)
    hsv[..., 0] = (hsv[..., 0] + _HUE_SHIFT) % 360.0
    hsv[..., 1] = np.clip(hsv[..., 1] * _SAT_MULT, 0.0, 1.0)
    chroma_rgb = np.clip(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB), 0.0, 1.0)

    final_srgb = colour.cctf_encoding(chroma_rgb, function="sRGB")
    return (final_srgb * 255.0 + 0.5).astype(np.uint8)[:, :, ::-1]
