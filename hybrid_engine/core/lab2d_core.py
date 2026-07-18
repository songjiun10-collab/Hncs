"""
[Phase 2.55] 2D 잔차 LUT - a/b(채도·hue를 함께 결정하는 두 축)만 결합으로
보정한다. L은 건드리지 않는다 - hue_core(hue만)/color_core(채도만)가
각자 1D로 따로 고치던 걸 하나의 2D 격자로 합친 것.

배경: 톤(L) 1D LUT +4.9%, hue 1D LUT +2.1% 둘 다 개별 축으로는 5%
미만에서 막혔고, L/a/b 3축을 전부 결합한 3D LUT(9^3=729격자)은
in-sample으로는 +11.1%였지만 leave-one-out 교차검증에서 -5.7%로
뒤집혀 순수 암기였음이 드러났다(hybrid_engine/assets/luts/README.md).
2D(a,b만, 9^2=81격자)는 3D보다 격자점이 훨씬 적어서 과적합 위험이
낮으면서도, hue LUT이 못 담던 "채도에 따라 다른 hue 보정"(memory
color별 보정)은 여전히 표현할 수 있는 중간 지점이다.

삼중선형 보간을 쓰는 lab3d_core(colour.LUT3D)와 달리 2D는 colour-science에
대응 클래스가 없어서 표준 이중선형(bilinear) 보간을 직접 구현했다 -
hue_core의 1D 순환보간과 같은 수준의 간단한 수학이라 새 의존성 없이 충분.
"""
import numpy as np


def apply_lab2d_lut(a, b, table, domain):
    """table: (size_a, size_b, 2) - 격자점별 보정된 (a, b) 출력값. 두 축의
    격자점 개수가 달라도 되지만(calibrate_profile.py는 항상 정사각형으로
    생성) 일반적으로 처리한다. domain: [[amin, bmin], [amax, bmax]]. 범위
    밖 입력은 clip 후 적용(외삽 대신 가장자리 값으로 고정)."""
    size_a, size_b = table.shape[0], table.shape[1]
    domain = np.asarray(domain, dtype=np.float64)
    lo, hi = domain[0], domain[1]
    span = np.clip(hi - lo, 1e-9, None)

    ab = np.stack([a, b], axis=-1)
    clipped = np.clip(ab, lo, hi)
    fx = (clipped[..., 0] - lo[0]) / span[0] * (size_a - 1)
    fy = (clipped[..., 1] - lo[1]) / span[1] * (size_b - 1)

    x0 = np.clip(np.floor(fx).astype(int), 0, max(size_a - 2, 0))
    y0 = np.clip(np.floor(fy).astype(int), 0, max(size_b - 2, 0))
    x1 = np.minimum(x0 + 1, size_a - 1)
    y1 = np.minimum(y0 + 1, size_b - 1)
    tx = np.clip(fx - x0, 0.0, 1.0)[..., None]
    ty = np.clip(fy - y0, 0.0, 1.0)[..., None]

    v00, v10 = table[x0, y0], table[x1, y0]
    v01, v11 = table[x0, y1], table[x1, y1]
    out = (v00 * (1 - tx) * (1 - ty) + v10 * tx * (1 - ty) +
           v01 * (1 - tx) * ty + v11 * tx * ty)
    return out[..., 0], out[..., 1]
