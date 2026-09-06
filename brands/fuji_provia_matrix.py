"""
apply_fuji_provia_matrix_look - `apply_provia()`(brands/fuji.py, 톤커브
4파라미터만, 매트릭스 없음)에 Sony/Sigma/Leica와 같은 방법론으로 3x3
컬러매트릭스+채도/색조 LUT을 얹은 버전. `brands/sony_raw_matrix.py`와
같은 조사(2026-09-02, 사용자 지시 "소니같은거도 다 매트릭스 만들어") -
Fuji는 필름모드가 여러 개라 Provia/Standard(EXIF FilmMode="F0/Standard
(Provia)")로 한정해서 비교했다(`apply_provia()` 자체가 그 필름모드로
검증됐던 것과 동일 스코프).

`tools/fit_brand_matrix_chroma_pipeline.py fuji --loo`로 Fuji Provia
raw+jpeg 119쌍(GFX100RF 89 + X-T30 III 20 + GFX50S II 10) - 톤커브는
`apply_provia()`가 이미 확정한 값(toe=0.0/ss=0.82/wp=1.0/clip=3.0,
`brands/fuji.py` 참고) 그대로 두고 매트릭스+채도/색조만 새로 5-fold
LOO 피팅해서 **실제 배포된 `apply_provia()`와 직접 맞대결**했다.

**결과**: 기존(톤커브만) ΔE00=12.929 대비 매트릭스+채도 LOO
ΔE00=12.390, **+4.17%**, 74승45패, 부호검정 p=0.0100, 부트스트랩 95%
CI [+0.225,+0.848](0 미포함) - Sony(+9.11%)/Sigma(+9.16%)/Leica(+8.13%)
보다 개선폭이 작다(승패 비율도 74/45로 덜 압도적) - Fuji 119쌍이 3바디
풀링이라 표본이 상대적으로 이질적인 게 원인일 수 있음(추정, 확인
안 됨). 그래도 CI가 0을 벗어나 통계적으로는 실재. 전체 표본(홀드아웃
없이) 최종 재피팅: in-sample ΔE00=12.362(LOO 12.390과 큰 차이 없어
과적합 아님), sat_mult=1.30, hue_shift=-2.86.

재현: `python3 -m tools.fit_brand_matrix_chroma_pipeline fuji --loo`."""
import colour
import cv2
import numpy as np

from core.curve import film_curve
from core.lut import ensure_uint8

_MATRIX = np.array([
    [2.7449879177674656, 0.8483914013435374, 0.7463160011811841],
    [-1.5312179829578052, 0.3064624447307009, -1.5059195744036642],
    [0.5713465147519522, 0.5883018929907207, 2.431347336576944],
])
_SAT_MULT = 1.3000
_HUE_SHIFT = -2.8571
_TONE_TOE_LIFT = 0.0
_TONE_SHOULDER_START = 0.82
_TONE_WHITE_POINT = 1.0
_TONE_CLAHE_CLIP = 3.0


def apply_fuji_provia_matrix_look(img_bgr):
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
