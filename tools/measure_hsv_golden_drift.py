"""HSV 골든 픽스처가 이 플랫폼에서 얼마나 흔들리는지 함수별로 잰다.

**왜 있는가**: `tests/test_population_fit_look_golden.py`의
`HSV_MAX_LSB_DRIFT`/`HSV_MAX_DRIFTING_PIXELS`는 추측이 아니라 실측값이다.
픽스처는 macOS ARM에서 생성됐는데 CI는 Linux x86_64라
`cv2.cvtColor(BGR2HSV)` 왕복의 최하위 비트가 실제로 갈린다(라이브러리
버전 문제가 아니라 플랫폼 차이). 2026-09-06에 그 허용치를 정하려고
CI 로그에 숫자를 찍는 임시 테스트(`tests/test_zz_temp_hsv_drift_probe.py`,
브랜치 `ci/regen-hsv-fixture`)를 잠깐 올렸다가, 측정이 끝나 지웠다.

같은 측정은 반드시 또 필요해진다 - 러너 아키텍처가 바뀌거나, opencv/
numpy를 올리거나, 픽스처를 다시 생성할 때. 그때 임시 테스트를 CI에
다시 올리는 대신 이걸 그 환경에서 직접 돌린다.

허용치를 고칠 때는 두 값을 같이 본다: `max`(최대 편차)만 넓히면 회귀
민감도가 통째로 떨어지므로, 몇 픽셀이나 흔들리는지(`gt0`)를 같이 묶어
"드물게, 1~2 LSB만" 이라는 조건으로 만든다.

    python3 -m tools.measure_hsv_golden_drift
"""
import importlib
import platform
import sys

import numpy as np


def main():
    import cv2

    from tests.test_population_fit_look_golden import (
        HSV_GOLDEN_FIXTURE, HSV_ROUND_TRIP_FUNCTIONS, make_test_image,
    )

    print(f"platform={platform.platform()} python={platform.python_version()} "
          f"cv2={cv2.__version__} numpy={np.__version__}")
    worst_max, worst_pixels = 0, 0
    with np.load(HSV_GOLDEN_FIXTURE, allow_pickle=False) as fixture:
        for mod_name, fn_name in HSV_ROUND_TRIP_FUNCTIONS:
            out = getattr(importlib.import_module(mod_name), fn_name)(
                make_test_image()).astype(np.int16)
            diff = np.abs(out - fixture[fn_name].astype(np.int16))
            gt0 = int((diff > 0).sum())
            worst_max = max(worst_max, int(diff.max()))
            worst_pixels = max(worst_pixels, gt0)
            print(f"  {fn_name:36s} max={int(diff.max())} gt0={gt0} "
                  f"gt1={int((diff > 1).sum())} gt2={int((diff > 2).sum())} "
                  f"mean={diff.mean():.6f} n={diff.size}")
    print(f"\n최댓값: max={worst_max}, 흔들린 픽셀 최대={worst_pixels}")
    print("tests/test_population_fit_look_golden.py의 HSV_MAX_LSB_DRIFT/"
          "HSV_MAX_DRIFTING_PIXELS는 이 두 값 이상이어야 한다.")


if __name__ == "__main__":
    sys.exit(main())
