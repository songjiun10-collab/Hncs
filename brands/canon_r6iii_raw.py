"""
apply_canon_r6iii_raw_look - Canon EOS R6 Mark III 전용 매트릭스+톤+채도.
`apply_canon_raw_look()`(brands/canon.py, R6 Mark III 99 + R1 44 풀링
143쌍으로 피팅)의 바디별 분해 - `tools/breakdown_sony_by_camera_body.py`가
Sony a1 II에서 찾은 것과 같은 질문을 Canon에도 물어본 결과
(2026-09-02).

`tools/breakdown_canon_by_camera_body.py`(500px)로 풀링
`apply_canon_raw_look()`을 두 바디에 각각 돌려보니 R1 평균
ΔE00=13.914 vs R6 Mark III 16.969로 유의미하게 갈렸다(부트스트랩 95%
CI [-4.733,-1.317], 0 미포함, n=44/99). Sony a1 II 때는 이 격차가
톤커브 4파라미터로는 안 좁혀졌지만, Canon은 애초에 매트릭스까지 쓰는
함수라 매트릭스/채도/색조를 바디 전용으로 재피팅하면 다른 결과가
나오는지 `tools/fit_canon_body_split_pipeline.py`로 확인했다(5-fold
LOO, 400px, 매 폴드 매트릭스+채도/색조 재피팅, **진짜 baseline인
풀링 apply_canon_raw_look()과 직접 맞대결** - Sony 조사 때 구버전과
비교하다 놓쳤던 실수를 반복하지 않기 위해 이번엔 처음부터 정확한
baseline으로 비교).

**R6 Mark III(n=95, 4쌍 디코드 실패 제외)**: 풀링 ΔE00=17.069 대비
바디전용 LOO ΔE00=16.734, **+1.96%**, 66승29패, 부호검정 p=0.0002,
부트스트랩 95% CI [+0.195,+0.487](0 미포함 - 작지만 통계적으로 실재).

전체 표본(홀드아웃 없이) 최종 재피팅: in-sample ΔE00=16.531(LOO
16.734와 큰 차이 없어 과적합 아님).

재현: `python3 -m tools.breakdown_canon_by_camera_body`(바디별 분해),
`python3 -m tools.fit_canon_body_split_pipeline "Canon EOS R6 Mark III"`
(LOO)."""
import colour
import cv2
import numpy as np

from core.curve import film_curve
from core.lut import ensure_uint8

_MATRIX = np.array([
    [0.5540727233783858, -0.011829210384509467, -0.2747367205256144],
    [1.50016261912698, 1.9448208643477929, 1.976506503993236],
    [-0.27320174314988166, 0.040716429690382465, 0.2904981356603643],
])
_SAT_MULT = 0.7000
_HUE_SHIFT = 0.0000
_TONE_TOE_LIFT = 0.0
_TONE_SHOULDER_START = 0.74
_TONE_WHITE_POINT = 1.0
_TONE_CLAHE_CLIP = 3.0


def apply_canon_r6iii_raw_look(img_bgr):
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
