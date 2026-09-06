"""
apply_leica_raw_matrix_look - `apply_leica_raw_look()`(brands/leica_raw.py,
톤커브 4파라미터만, 매트릭스 없음)에 Canon/Sony/Sigma와 같은 방법론으로
3x3 컬러매트릭스+채도/색조 LUT을 얹은 버전. `brands/sony_raw_matrix.py`/
`sigma_raw_matrix.py`와 같은 조사(2026-09-02, 사용자 지시 "소니같은거도
다 매트릭스 만들어").

`tools/fit_brand_matrix_chroma_pipeline.py leica --loo`로 Leica raw+jpeg
244쌍(디코드 성공, SL2/Q3 43/SL2-S/SL3-P/M10/CL 통합 풀) - 톤커브는
`apply_leica_raw_look()`이 이미 확정한 값(toe=0.0/ss=0.82/wp=1.0/
clip=1.25, `brands/leica_raw.py` 참고) 그대로 두고 매트릭스+채도/색조만
새로 5-fold LOO 피팅해서 **실제 배포된 `apply_leica_raw_look()`과 직접
맞대결**했다.

**결과**: 기존(톤커브만) ΔE00=9.634 대비 매트릭스+채도 LOO ΔE00=8.850,
**+8.13%**, 183승61패, 부호검정 p<0.0001, 부트스트랩 95% CI
[+0.632,+0.936](0 미포함) - Sony(+9.11%)/Sigma(+9.16%)와 비슷한
개선폭. 전체 표본(홀드아웃 없이) 최종 재피팅: in-sample ΔE00=8.832
(LOO 8.850과 거의 차이 없어 과적합 아님), sat_mult=1.10, hue_shift=-1.43.

**참고**: `apply_leica_raw_look()`은 이미 ΔE00<10(9.634)이었는데, 이
버전은 8.832까지 더 내려간다 - Canon이 매트릭스+톤+채도를 다 써도
`/goal "다른 브랜드 ΔE00<10"`을 구조적으로 못 채웠던 것과 대비된다
(`brands/canon.py`의 `apply_canon_raw_look` docstring 참고).

재현: `python3 -m tools.fit_brand_matrix_chroma_pipeline leica --loo`."""
import colour
import cv2
import numpy as np

from core.curve import film_curve
from core.lut import ensure_uint8

_MATRIX = np.array([
    [1.4809218487033136, 0.3181787950809252, 0.2802076292878065],
    [-0.4465972540435079, 0.7749064270898477, -0.31869172326744366],
    [0.3463435774440557, 0.28164238987520596, 1.3618900229721693],
])
_SAT_MULT = 1.1000
_HUE_SHIFT = -1.4286
_TONE_TOE_LIFT = 0.0
_TONE_SHOULDER_START = 0.82
_TONE_WHITE_POINT = 1.0
_TONE_CLAHE_CLIP = 1.25


def apply_leica_raw_matrix_look(img_bgr):
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
