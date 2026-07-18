"""
[Phase 1.6] 3D 잔차 LUT - L/a/b 세 축을 결합(joint)으로 입력받아 보정한다.
tone_core(L만)/color_core(a,b 채도만)/hue_core(hue만)가 각자 독립적으로
축 하나씩만 고치는 것과 근본적으로 다른 접근이다.

배경: 톤 학습 LUT(+4.9%)과 hue 학습 LUT(+2.1%) 둘 다 개별 축을 따로
고치는 방식으로는 5% 미만에서 막혔다(hybrid_engine/assets/luts/README.md).
잔차가 채널별로 분해되지 않는(joint) 형태라는 진단에 대한 직접적인
다음 시도가 이 모듈 - "이 L, 이 a, 이 b 조합일 때"를 통째로 보고 보정한다.

삼중선형 보간은 직접 구현하지 않고 colour-science의 LUT3D를 그대로
쓴다(이미 requirements.txt에 있는 의존성 재사용, core/log_pipeline.py의
apply_cube_lut()도 같은 클래스를 씀).
"""
import numpy as np
import colour


def apply_lab3d_lut(L, a, b, table, domain):
    """table: (size, size, size, 3) - 격자점별 보정된 (L, a, b) 출력값.
    domain: [[Lmin, amin, bmin], [Lmax, amax, bmax]] - table 격자가 커버하는
    범위. 범위 밖 입력은 clip 후 적용(외삽 대신 가장자리 값으로 고정) -
    학습 때 본 적 없는 영역을 잘못 추정해서 왜곡시키지 않기 위함."""
    lut = colour.LUT3D(table=table, domain=np.asarray(domain, dtype=np.float64))
    lab = np.stack([L, a, b], axis=-1)
    clipped = np.clip(lab, domain[0], domain[1])
    out = lut.apply(clipped)
    return out[..., 0], out[..., 1], out[..., 2]
