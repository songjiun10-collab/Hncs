"""
apply_canon_r1_raw_look - Canon EOS R1 전용 매트릭스+톤+채도.
`apply_canon_raw_look()`(brands/canon.py, R6 Mark III 99 + R1 44 풀링
143쌍으로 피팅)의 바디별 분해 - `brands/canon_r6iii_raw.py`와 같은
조사(2026-09-02)의 R1 쪽 결과. 배경/방법론은 그 파일 docstring 참고.

**R1(n=44)**: 풀링 apply_canon_raw_look() ΔE00=13.693 대비 바디전용
LOO ΔE00=12.530, **+8.49%**, 33승11패, 부호검정 p=0.0013, 부트스트랩
95% CI [+0.542,+1.806](0 미포함) - R6 Mark III(+1.96%)보다 훨씬 큰
개선폭.

전체 표본(홀드아웃 없이) 최종 재피팅: in-sample ΔE00=12.472(LOO
12.530과 큰 차이 없어 과적합 아님).

재현: `python3 -m tools.breakdown_canon_by_camera_body`(바디별 분해),
`python3 -m tools.fit_canon_body_split_pipeline "Canon EOS R1"`(LOO)."""
import colour
import cv2
import numpy as np

from core.curve import film_curve
from core.lut import ensure_uint8

_MATRIX = np.array([
    [3.210831334694452, 0.5870805964265602, 0.9156735883866578],
    [-0.9147002424159167, 1.7759874712600467, -0.1857833825690216],
    [0.026497985192973448, -0.13085767308072366, 1.2256574019532263],
])
_SAT_MULT = 1.2000
_HUE_SHIFT = 1.4286
_TONE_TOE_LIFT = 0.0
_TONE_SHOULDER_START = 0.74
_TONE_WHITE_POINT = 1.0
_TONE_CLAHE_CLIP = 3.0


def apply_canon_r1_raw_look(img_bgr):
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
