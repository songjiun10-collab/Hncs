"""
톤커브 수학 헬퍼 - brands/*.py 전체가 공유.

film_curve는 원래 hasselblad_hncs.py에 있던 "toe + 리니어미드 + smoothstep
shoulder" 필름형 커브. s_curve/apply_highlight_rolloff/shadow_lift는 원래
film_sim_presets.py(후지 프리셋)에 있던 헬퍼들로, 둘 다 여러 브랜드
모듈에서 재사용되길래 여기로 옮겼다.
"""
import numpy as np


def film_curve(x, toe_lift=0.001, shoulder_start=0.78, white_point=0.90):
    """Film Curve: toe(완만 진입+미세 리프트) + 리니어 미드 + smoothstep shoulder"""
    y = x.copy()
    toe_mask = x < 0.1
    # toe는 [0,0.1] -> [toe_lift,0.1]로 선형보간하는 구간이라 toe_lift가
    # 0.1 이상이면 기울기(0.1-toe_lift)가 음수가 돼서 어두운 픽셀이 밝은
    # 픽셀보다 더 밝게 나오는 반전이 생김 - 0.1 미만으로 clamp해서 방지.
    toe_lift = min(toe_lift, 0.099)
    t = x[toe_mask] / 0.1
    y[toe_mask] = toe_lift + t * (0.1 - toe_lift)   # [0,0.1] -> [lift,0.1]
    sh_mask = x > shoulder_start
    t2 = (x[sh_mask] - shoulder_start) / (1 - shoulder_start)
    y[sh_mask] = shoulder_start + (t2 * t2 * (3 - 2 * t2)) * (white_point - shoulder_start)
    return np.clip(y, 0, 1)


def s_curve(x, n=2.0):
    """
    대칭 S자 커브. x^n / (x^n + (1-x)^n) 형태.
    항상 y(0)=0, y(1)=1을 보장하므로 사인 기반 커브에서 발생하던
    "끝단이 0/1에 안 닿는" 문제가 원천적으로 없음.
    n=1: 직선(변화 없음) / n>1: 콘트라스트 강조 S자 / n<1: 대비 완화
    """
    x_safe = np.clip(x, 1e-6, 1 - 1e-6)
    return (x_safe ** n) / (x_safe ** n + (1 - x_safe) ** n)


def apply_highlight_rolloff(x, y, start=0.8):
    """
    y 배열(이미 다른 커브가 적용된 상태)에 이어서 하이라이트만 부드럽게 압축.
    연속성 보장: rolloff 시작값을 커브에서 실제로 보간해서 가져오므로
    "롤오프 시작점에서 값이 뚝 떨어지는" 불연속 문제가 없음.
    """
    mask = x > start
    if not np.any(mask):
        return y
    y_start = np.interp(start, x, y)
    headroom = 1.0 - y_start
    t = (x[mask] - start) / (1 - start)
    smooth_t = t * t * (3 - 2 * t)
    y[mask] = y_start + smooth_t * headroom
    return y


def shadow_lift(x, y, lift=0.02, threshold=0.1):
    mask = x < threshold
    y[mask] = y[mask] + (lift * (1 - (x[mask] / threshold)))
    return y
