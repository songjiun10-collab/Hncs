"""
[Phase 2.5] Hue 보정 - LAB a/b의 색상각(hue)만 회전시키고 채도(chroma)는
그대로 둔다. color_core.py(가변 채도 부스팅)와 축을 분리한 이유: 채도는
"얼마나 진하게", hue는 "어느 방향으로"라는 서로 다른 문제라 각자
독립적으로 조정 가능해야 한다.

evaluation/fidelity.py 실측(평균 |Δhue| 34.29도, delta_e_by_zone에서
미드톤이 그림자/하이라이트보다 나쁨)이 이 모듈이 메우려는 병목이다 -
V0.1은 톤/채도 커브만 있고 hue를 건드리는 단계가 아예 없었다.

V0.1엔 파라메트릭 모델이 없다 - 어느 hue를 어느 방향으로 얼마나 돌려야
하는지는 브랜드마다 다르고 손으로 짤 근거가 없어서, calibrate_profile.py
--mode hue로 raw+jpeg 페어에서 직접 학습한 1D 순환(circular) LUT만
지원한다. LUT이 없으면 이 모듈은 완전히 bypass(hue 변경 없음) -
tone_core의 학습 LUT 모드와 같은 원리를 hue 축에 적용한 것.
"""
import numpy as np


def apply_hue_lut(a, b, hue_lut):
    """hue_lut: calibrate_profile.learn_hue_lut()이 만든 (n_bins,) 배열 -
    입력 hue(0~360도, bin 중심 기준)별로 학습된 보정량(도 단위, 순환).
    chroma(sqrt(a^2+b^2))는 그대로 보존하고 hue만 회전시킨다."""
    n_bins = len(hue_lut)
    chroma = np.hypot(a, b)
    hue_in = np.degrees(np.arctan2(b, a)) % 360.0

    bin_width = 360.0 / n_bins
    centers = (np.arange(n_bins) + 0.5) * bin_width
    # 0/360도 경계에서 보간이 끊기지 않도록 앞뒤로 한 바퀴씩 이어붙임
    domain = np.concatenate([centers - 360.0, centers, centers + 360.0])
    values = np.tile(hue_lut, 3)
    delta_deg = np.interp(hue_in.ravel(), domain, values).reshape(hue_in.shape)

    hue_out = np.radians(hue_in + delta_deg)
    return chroma * np.cos(hue_out), chroma * np.sin(hue_out)
